from __future__ import annotations

import os

import stripe
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from models import User

stripe.api_key = os.environ.get("STRIPE_SECRET_KEY", "")

PRO_PRICE_ID = os.environ.get("STRIPE_PRO_PRICE_ID", "")
APP_URL = os.environ.get("APP_URL", "https://safetybuddy.app")


async def create_checkout_session(user: User, db: AsyncSession) -> str:
    """Returns the Stripe Checkout URL for upgrading to Pro."""
    if not stripe.api_key:
        raise HTTPException(status_code=503, detail="Billing not configured")

    # Create or reuse the Stripe customer
    customer_id = user.stripe_customer_id
    if not customer_id:
        customer = stripe.Customer.create(email=user.email, metadata={"user_id": user.id})
        user.stripe_customer_id = customer.id
        await db.commit()
        customer_id = customer.id

    session = stripe.checkout.Session.create(
        customer=customer_id,
        mode="subscription",
        line_items=[{"price": PRO_PRICE_ID, "quantity": 1}],
        success_url=f"{APP_URL}/billing/success?session_id={{CHECKOUT_SESSION_ID}}",
        cancel_url=f"{APP_URL}/billing/cancel",
        metadata={"user_id": user.id},
    )
    return session.url


async def create_portal_session(user: User) -> str:
    """Returns the Stripe Customer Portal URL for managing the subscription."""
    if not stripe.api_key or not user.stripe_customer_id:
        raise HTTPException(status_code=503, detail="Billing not configured")

    session = stripe.billing_portal.Session.create(
        customer=user.stripe_customer_id,
        return_url=f"{APP_URL}/account",
    )
    return session.url


def handle_webhook(payload: bytes, sig_header: str) -> dict:
    """Verify and parse a Stripe webhook event."""
    secret = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
    if not secret:
        raise HTTPException(status_code=503, detail="Webhook secret not configured")

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, secret)
    except stripe.error.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid webhook signature")

    return event


WEBHOOK_PLAN_MAP = {
    "customer.subscription.created": "pro",
    "customer.subscription.updated": None,  # handled specially below
    "customer.subscription.deleted": "free",
    "invoice.payment_failed": "free",
}


def plan_from_event(event: dict) -> tuple[str | None, str | None]:
    """
    Returns (stripe_customer_id, new_plan) or (None, None) if no action needed.
    """
    event_type = event["type"]
    obj = event["data"]["object"]

    if event_type == "customer.subscription.updated":
        status = obj.get("status")
        new_plan = "pro" if status == "active" else "free"
        return obj.get("customer"), new_plan

    if event_type in WEBHOOK_PLAN_MAP:
        new_plan = WEBHOOK_PLAN_MAP[event_type]
        return obj.get("customer"), new_plan

    return None, None
