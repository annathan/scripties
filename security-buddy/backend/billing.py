from __future__ import annotations

import hashlib
import hmac
import os
import time
from datetime import datetime, timedelta, timezone

import httpx
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from models import PLAN_ANNUAL, PLAN_LIFETIME, User

# Use sandbox while PADDLE_SANDBOX=true; flip to production when ready
_SANDBOX = os.environ.get("PADDLE_SANDBOX", "true").lower() == "true"
PADDLE_API_BASE = (
    "https://sandbox-api.paddle.com" if _SANDBOX else "https://api.paddle.com"
)
PADDLE_PORTAL_URL = "https://customer.paddle.com"

APP_URL = os.environ.get("APP_URL", "https://safetybuddy.app")

# Create one Price in the Paddle dashboard for each product:
#   annual prices → recurring, yearly billing interval
#   lifetime / api_renewal prices → one-time charge
PLAN_PRICES: dict[str, str | None] = {
    "personal_annual":   os.environ.get("PADDLE_PERSONAL_ANNUAL_PRICE_ID"),
    "family_annual":     os.environ.get("PADDLE_FAMILY_ANNUAL_PRICE_ID"),
    "personal_lifetime": os.environ.get("PADDLE_PERSONAL_LIFETIME_PRICE_ID"),
    "family_lifetime":   os.environ.get("PADDLE_FAMILY_LIFETIME_PRICE_ID"),
    "api_renewal":       os.environ.get("PADDLE_API_RENEWAL_PRICE_ID"),
}

VALID_PLAN_KEYS = set(PLAN_PRICES.keys())
_API_CHECKING_DAYS = 730  # 2-year Claude API window for lifetime plans
_WEBHOOK_MAX_AGE_SECS = 300  # reject webhooks older than 5 minutes


def _auth_headers() -> dict[str, str]:
    key = os.environ.get("PADDLE_API_KEY", "")
    if not key:
        raise HTTPException(status_code=503, detail="Billing not configured")
    return {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}


def plan_from_price_id(price_id: str) -> str | None:
    """Map a Paddle Price ID back to our internal plan key."""
    return next((k for k, v in PLAN_PRICES.items() if v and v == price_id), None)


async def _get_or_create_customer(user: User, db: AsyncSession) -> str:
    """Return the Paddle customer ID, creating one via the API if not yet stored."""
    if user.paddle_customer_id:
        return user.paddle_customer_id

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                f"{PADDLE_API_BASE}/customers",
                headers=_auth_headers(),
                json={"email": user.email, "name": user.name or user.email},
            )
            resp.raise_for_status()
            customer_id: str = resp.json()["data"]["id"]
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=503, detail=f"Billing error: {exc.response.text}")
    except httpx.RequestError as exc:
        raise HTTPException(status_code=503, detail=f"Billing unreachable: {exc}")

    user.paddle_customer_id = customer_id
    await db.commit()
    return customer_id


async def create_checkout_session(user: User, db: AsyncSession, plan_key: str) -> str:
    """Return a Paddle-hosted checkout URL for the requested plan."""
    price_id = PLAN_PRICES.get(plan_key)
    if not price_id:
        raise HTTPException(status_code=503, detail=f"Price not configured: {plan_key}")

    customer_id = await _get_or_create_customer(user, db)

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                f"{PADDLE_API_BASE}/transactions",
                headers=_auth_headers(),
                json={
                    "items": [{"price_id": price_id, "quantity": 1}],
                    "customer_id": customer_id,
                    "checkout": {"url": f"{APP_URL}/billing/success"},
                    # custom_data is echoed back in all related webhook events
                    "custom_data": {"plan_key": plan_key, "user_id": user.id},
                },
            )
            resp.raise_for_status()
            return resp.json()["data"]["checkout"]["url"]
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=503, detail=f"Billing error: {exc.response.text}")
    except httpx.RequestError as exc:
        raise HTTPException(status_code=503, detail=f"Billing unreachable: {exc}")


async def create_portal_session(user: User) -> str:
    """Return the Paddle customer portal URL.

    Unlike Stripe, Paddle does not issue pre-authenticated portal sessions via
    the API. The customer logs in to the self-serve portal with their email.
    """
    if not user.paddle_customer_id:
        raise HTTPException(status_code=400, detail="No billing account found. Please upgrade first.")
    return PADDLE_PORTAL_URL


def verify_webhook(payload: bytes, sig_header: str) -> None:
    """Verify the Paddle-Signature header and raise 400 if invalid.

    Paddle signature format:  ts=<unix_timestamp>;h1=<hmac_sha256_hex>
    Signed payload:           <timestamp>:<raw_body>
    """
    secret = os.environ.get("PADDLE_WEBHOOK_SECRET", "")
    if not secret:
        raise HTTPException(status_code=503, detail="Webhook secret not configured")

    try:
        parts = dict(part.split("=", 1) for part in sig_header.split(";"))
        ts = parts["ts"]
        h1 = parts["h1"]
    except (KeyError, ValueError):
        raise HTTPException(status_code=400, detail="Malformed Paddle-Signature header")

    try:
        age = abs(time.time() - int(ts))
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid webhook timestamp")
    if age > _WEBHOOK_MAX_AGE_SECS:
        raise HTTPException(status_code=400, detail="Webhook timestamp too old")

    signed_payload = f"{ts}:{payload.decode()}"
    expected = hmac.new(
        secret.encode(),
        signed_payload.encode(),
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(expected, h1):
        raise HTTPException(status_code=400, detail="Invalid webhook signature")


def apply_event(event: dict) -> dict | None:
    """Parse a Paddle webhook event and return field updates for the matching User.

    Returns a dict that always contains either 'user_id' (preferred, from
    custom_data) to identify the user. Returns None when no action is needed.
    """
    event_type = event.get("event_type", "")
    data = event.get("data", {})
    custom = data.get("custom_data") or {}
    user_id = custom.get("user_id")

    now = datetime.now(timezone.utc)

    # ------------------------------------------------------------------
    # One-time payments  (lifetime licences + API renewal)
    # Skip if this transaction is part of a subscription (handled below).
    # ------------------------------------------------------------------
    if event_type == "transaction.completed" and not data.get("subscription_id"):
        plan_key = custom.get("plan_key")
        if not plan_key or not user_id:
            return None

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

    # ------------------------------------------------------------------
    # Subscription created (annual plans)
    # ------------------------------------------------------------------
    if event_type == "subscription.created":
        plan_key = custom.get("plan_key")
        if not plan_key or not user_id or plan_key not in PLAN_ANNUAL:
            return None
        next_billed = data.get("next_billed_at")
        expires_at = _parse_iso(next_billed)
        return {"user_id": user_id, "plan": plan_key, "plan_expires_at": expires_at}

    # ------------------------------------------------------------------
    # Subscription updated (renewal, plan change, pause/resume)
    # ------------------------------------------------------------------
    if event_type == "subscription.updated":
        if not user_id:
            return None
        status = data.get("status")
        if status in ("canceled", "paused"):
            return {"user_id": user_id, "plan": "free", "plan_expires_at": None}
        if status in ("active", "trialing"):
            items = data.get("items", [])
            price_id = items[0]["price"]["id"] if items else None
            plan_key = plan_from_price_id(price_id) if price_id else custom.get("plan_key")
            if not plan_key:
                return None
            next_billed = data.get("next_billed_at")
            return {
                "user_id": user_id,
                "plan": plan_key,
                "plan_expires_at": _parse_iso(next_billed),
            }
        return None

    # ------------------------------------------------------------------
    # Subscription canceled / payment failed
    # ------------------------------------------------------------------
    if event_type in ("subscription.canceled", "transaction.payment_failed"):
        if user_id:
            return {"user_id": user_id, "plan": "free", "plan_expires_at": None}

    return None


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))
