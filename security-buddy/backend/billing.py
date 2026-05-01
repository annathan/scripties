from __future__ import annotations

import os

import stripe
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from models import User

APP_URL = os.environ.get("APP_URL", "https://safetybuddy.app")
PRO_PRICE_ID = os.environ.get("STRIPE_PRO_PRICE_ID", "")


def _client() -> stripe.StripeClient:
    key = os.environ.get("STRIPE_SECRET_KEY", "")
    if not key:
        raise HTTPException(status_code=503, detail="Billing not configured")
    return stripe.StripeClient(key)


async def create_checkout_session(user: User, db: AsyncSession) -> str:
    """Returns the Stripe Checkout URL for upgrading to Pro."""
    if not PRO_PRICE_ID:
        raise HTTPException(status_code=503, detail="Billing price not configured")

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
                "mode": "subscription",
                "line_items": [{"price": PRO_PRICE_ID, "quantity": 1}],
                "success_url": f"{APP_URL}/billing/success?session_id={{CHECKOUT_SESSION_ID}}",
                "cancel_url": f"{APP_URL}/billing/cancel",
                "metadata": {"user_id": user.id},
            }
        )
        return session.url
    except stripe.StripeError as e:
        raise HTTPException(status_code=503, detail=f"Billing service error: {e.user_message or str(e)}")


async def create_portal_session(user: User) -> str:
    """Returns the Stripe Customer Portal URL for managing the subscription."""
    if not user.stripe_customer_id:
        raise HTTPException(status_code=400, detail="No billing account found. Please upgrade first.")

    client = _client()
    try:
        session = client.billing_portal.sessions.create(
            params={
                "customer": user.stripe_customer_id,
                "return_url": f"{APP_URL}/account",
            }
        )
        return session.url
    except stripe.StripeError as e:
        raise HTTPException(status_code=503, detail=f"Billing service error: {e.user_message or str(e)}")


def handle_webhook(payload: bytes, sig_header: str) -> dict:
    """Verify and parse a Stripe webhook event."""
    secret = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
    if not secret:
        raise HTTPException(status_code=503, detail="Webhook secret not configured")

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, secret)
    except stripe.error.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid webhook signature")
    except Exception:
        raise HTTPException(status_code=400, detail="Malformed webhook payload")

    return event


_WEBHOOK_PLAN_MAP = {
    "customer.subscription.created": "pro",
    "customer.subscription.deleted": "free",
    "invoice.payment_failed": "free",
}


def plan_from_event(event: dict) -> tuple[str | None, str | None]:
    """Returns (stripe_customer_id, new_plan) or (None, None) if no action needed."""
    event_type = event["type"]
    obj = event["data"]["object"]

    if event_type == "customer.subscription.updated":
        status = obj.get("status")
        new_plan = "pro" if status == "active" else "free"
        return obj.get("customer"), new_plan

    if event_type in _WEBHOOK_PLAN_MAP:
        return obj.get("customer"), _WEBHOOK_PLAN_MAP[event_type]

    return None, None
