from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import stripe
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from models import PLAN_ANNUAL, PLAN_LIFETIME, User

APP_URL = os.environ.get("APP_URL", "https://safetybuddy.app")

# One Stripe Price ID per product. Create these in the Stripe dashboard:
#   personal_annual / family_annual  → recurring, yearly interval
#   personal_lifetime / family_lifetime / api_renewal → one-time payment
PLAN_PRICES: dict[str, str | None] = {
    "personal_annual":   os.environ.get("STRIPE_PERSONAL_ANNUAL_PRICE_ID"),
    "family_annual":     os.environ.get("STRIPE_FAMILY_ANNUAL_PRICE_ID"),
    "personal_lifetime": os.environ.get("STRIPE_PERSONAL_LIFETIME_PRICE_ID"),
    "family_lifetime":   os.environ.get("STRIPE_FAMILY_LIFETIME_PRICE_ID"),
    "api_renewal":       os.environ.get("STRIPE_API_RENEWAL_PRICE_ID"),
}

VALID_PLAN_KEYS = set(PLAN_PRICES.keys())
_API_CHECKING_DAYS = 730  # 2 years


def _client() -> stripe.StripeClient:
    key = os.environ.get("STRIPE_SECRET_KEY", "")
    if not key:
        raise HTTPException(status_code=503, detail="Billing not configured")
    return stripe.StripeClient(key)


def plan_from_price_id(price_id: str) -> str | None:
    """Map a Stripe Price ID back to our internal plan key."""
    return next((k for k, v in PLAN_PRICES.items() if v and v == price_id), None)


async def create_checkout_session(user: User, db: AsyncSession, plan_key: str) -> str:
    """Return a Stripe Checkout URL for the given plan_key."""
    price_id = PLAN_PRICES.get(plan_key)
    if not price_id:
        raise HTTPException(status_code=503, detail=f"Price not configured for plan: {plan_key}")

    is_one_time = plan_key in PLAN_LIFETIME or plan_key == "api_renewal"
    mode = "payment" if is_one_time else "subscription"

    client = _client()
    try:
        customer_id = user.stripe_customer_id
        if not customer_id:
            customer = client.customers.create(
                params={"email": user.email, "metadata": {"user_id": user.id}}
            )
            user.stripe_customer_id = customer.id
            await db.commit()
            customer_id = customer.id

        session = client.checkout.sessions.create(
            params={
                "customer": customer_id,
                "mode": mode,
                "line_items": [{"price": price_id, "quantity": 1}],
                "success_url": f"{APP_URL}/billing/success?session_id={{CHECKOUT_SESSION_ID}}",
                "cancel_url": f"{APP_URL}/billing/cancel",
                # plan_key in metadata lets the webhook know which plan to activate
                "metadata": {"plan_key": plan_key, "user_id": user.id},
            }
        )
        return session.url
    except stripe.StripeError as exc:
        raise HTTPException(status_code=503, detail=f"Billing error: {exc.user_message or str(exc)}")


async def create_portal_session(user: User) -> str:
    if not user.stripe_customer_id:
        raise HTTPException(status_code=400, detail="No billing account found. Please upgrade first.")
    client = _client()
    try:
        session = client.billing_portal.sessions.create(
            params={"customer": user.stripe_customer_id, "return_url": f"{APP_URL}/account"}
        )
        return session.url
    except stripe.StripeError as exc:
        raise HTTPException(status_code=503, detail=f"Billing error: {exc.user_message or str(exc)}")


def handle_webhook(payload: bytes, sig_header: str) -> dict:
    secret = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
    if not secret:
        raise HTTPException(status_code=503, detail="Webhook secret not configured")
    try:
        return stripe.Webhook.construct_event(payload, sig_header, secret)
    except stripe.error.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid webhook signature")
    except Exception:
        raise HTTPException(status_code=400, detail="Malformed webhook payload")


def apply_event(event: dict) -> dict | None:
    """Return a dict of field updates to apply to the matching User, or None if no action."""
    event_type = event["type"]
    obj = event["data"]["object"]

    # --- One-time payments (lifetime + api_renewal) ---
    if event_type == "checkout.session.completed" and obj.get("mode") == "payment":
        meta = obj.get("metadata") or {}
        plan_key = meta.get("plan_key")
        user_id = meta.get("user_id")
        if not plan_key or not user_id:
            return None

        now = datetime.now(timezone.utc)
        expires = now + timedelta(days=_API_CHECKING_DAYS)

        if plan_key == "api_renewal":
            return {"user_id": user_id, "api_checking_expires_at": expires}
        if plan_key in PLAN_LIFETIME:
            return {
                "user_id": user_id,
                "plan": plan_key,
                "api_checking_expires_at": expires,
                "plan_expires_at": None,
            }
        return None

    # --- Subscription events (annual plans) ---
    customer_id = obj.get("customer")

    if event_type in ("customer.subscription.created", "customer.subscription.updated"):
        status = obj.get("status")
        if status not in ("active", "trialing"):
            return {"customer_id": customer_id, "plan": "free", "plan_expires_at": None}
        # Derive plan from the first line item price
        items = obj.get("items", {}).get("data", [])
        price_id = items[0]["price"]["id"] if items else None
        plan_key = plan_from_price_id(price_id) if price_id else None
        if not plan_key or plan_key not in PLAN_ANNUAL:
            return None
        period_end = obj.get("current_period_end")
        expires_at = (
            datetime.fromtimestamp(period_end, tz=timezone.utc) if period_end else None
        )
        return {"customer_id": customer_id, "plan": plan_key, "plan_expires_at": expires_at}

    if event_type in ("customer.subscription.deleted", "invoice.payment_failed"):
        return {"customer_id": customer_id, "plan": "free", "plan_expires_at": None}

    return None
