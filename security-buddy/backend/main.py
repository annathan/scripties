from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import Depends, Header, HTTPException, Request, status
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth import get_current_user, get_current_user_or_none, hash_password, verify_password
from billing import create_checkout_session, create_portal_session, handle_webhook, plan_from_event
from check_url import check_url
from database import get_db, init_db
from models import Guardian, User, WarningEvent
from notify import send_guardian_email, send_guardian_sms


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(title="Safety Buddy Backend", lifespan=lifespan)

allowed_origins = os.environ.get("ALLOWED_ORIGINS", "*").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_methods=["POST", "GET", "PUT", "DELETE"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@app.get("/health")
async def health():
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    name: str = ""


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


@app.post("/auth/register", status_code=status.HTTP_201_CREATED)
async def register(req: RegisterRequest, db: AsyncSession = Depends(get_db)):
    existing = await db.execute(select(User).where(User.email == req.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Email already registered")

    user = User(
        email=req.email,
        password_hash=hash_password(req.password),
        name=req.name,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return {"api_key": user.api_key, "plan": user.plan, "name": user.name, "email": user.email}


@app.post("/auth/login")
async def login(req: LoginRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == req.email))
    user = result.scalar_one_or_none()
    if not user or not verify_password(req.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    return {"api_key": user.api_key, "plan": user.plan, "name": user.name, "email": user.email}


# ---------------------------------------------------------------------------
# Account
# ---------------------------------------------------------------------------

@app.get("/account/me")
async def get_me(user: User = Depends(get_current_user)):
    return {
        "email": user.email,
        "name": user.name,
        "plan": user.plan,
        "guardian_limit": user.guardian_limit,
    }


# ---------------------------------------------------------------------------
# Guardians
# ---------------------------------------------------------------------------

class GuardianIn(BaseModel):
    name: str = ""
    email: str = ""
    phone: str = ""


@app.get("/guardians")
async def list_guardians(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Guardian).where(Guardian.user_id == user.id))
    guardians = result.scalars().all()
    return [{"id": g.id, "name": g.name, "email": g.email, "phone": g.phone} for g in guardians]


@app.post("/guardians", status_code=status.HTTP_201_CREATED)
async def add_guardian(
    req: GuardianIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Guardian).where(Guardian.user_id == user.id))
    current_count = len(result.scalars().all())
    if current_count >= user.guardian_limit:
        raise HTTPException(
            status_code=403,
            detail=f"Free plan supports {user.guardian_limit} guardian. Upgrade to Pro for up to 5.",
        )
    guardian = Guardian(user_id=user.id, name=req.name, email=req.email, phone=req.phone)
    db.add(guardian)
    await db.commit()
    await db.refresh(guardian)
    return {"id": guardian.id, "name": guardian.name, "email": guardian.email, "phone": guardian.phone}


@app.delete("/guardians/{guardian_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_guardian(
    guardian_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Guardian).where(Guardian.id == guardian_id, Guardian.user_id == user.id)
    )
    guardian = result.scalar_one_or_none()
    if not guardian:
        raise HTTPException(status_code=404, detail="Guardian not found")
    await db.delete(guardian)
    await db.commit()


# ---------------------------------------------------------------------------
# URL check  (fail-open: unauthenticated requests still get a verdict)
# ---------------------------------------------------------------------------

class CheckUrlRequest(BaseModel):
    url: str
    page_title: str = ""


@app.post("/check-url")
async def check_url_endpoint(
    req: CheckUrlRequest,
    user: User | None = Depends(get_current_user_or_none),
    db: AsyncSession = Depends(get_db),
):
    result = await check_url(req.url, req.page_title)

    # Log the event so Pro users get digest emails
    if user and not result.get("safe", True):
        event = WarningEvent(
            user_id=user.id,
            url=req.url,
            verdict=result.get("safe", True),
            risk_level=result.get("risk_level", "medium"),
            reason=result.get("reason", ""),
        )
        db.add(event)
        await db.commit()

    return result


# ---------------------------------------------------------------------------
# Notify  (email + SMS gated by plan)
# ---------------------------------------------------------------------------

class NotifyRequest(BaseModel):
    url: str
    reason: str = ""
    risk_level: str = "unknown"
    proceeded: bool = False


class UrgentNotifyRequest(BaseModel):
    url: str
    label: str
    timestamp: str = ""


@app.post("/notify")
async def notify_endpoint(
    req: NotifyRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not user.is_pro:
        return {"sent": False, "reason": "upgrade_required"}

    result = await db.execute(select(Guardian).where(Guardian.user_id == user.id))
    guardians = result.scalars().all()

    for g in guardians:
        if g.email:
            await send_guardian_email(
                to_email=g.email,
                guardian_name=g.name,
                user_name=user.name or "Your family member",
                url=req.url,
                reason=req.reason,
                risk_level=req.risk_level,
                proceeded=req.proceeded,
            )

    # Log proceeded events
    if req.proceeded:
        event = WarningEvent(
            user_id=user.id,
            url=req.url,
            verdict=False,
            risk_level=req.risk_level,
            reason=req.reason,
            proceeded=True,
        )
        db.add(event)
        await db.commit()

    return {"sent": True}


@app.post("/notify-urgent")
async def notify_urgent_endpoint(
    req: UrgentNotifyRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not user.is_pro:
        return {"sent": False, "reason": "upgrade_required"}

    result = await db.execute(select(Guardian).where(Guardian.user_id == user.id))
    guardians = result.scalars().all()

    for g in guardians:
        if g.phone:
            await send_guardian_sms(
                to_phone=g.phone,
                guardian_name=g.name,
                user_name=user.name or "Your family member",
                label=req.label,
            )

    # Always log financial danger events
    event = WarningEvent(
        user_id=user.id,
        url=req.url,
        verdict=False,
        risk_level="high",
        reason=f"Visited {req.label} page",
        label=req.label,
    )
    db.add(event)
    await db.commit()

    return {"sent": True}


# ---------------------------------------------------------------------------
# Billing
# ---------------------------------------------------------------------------

@app.post("/billing/checkout")
async def billing_checkout(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    url = await create_checkout_session(user, db)
    return {"url": url}


@app.post("/billing/portal")
async def billing_portal(user: User = Depends(get_current_user)):
    url = await create_portal_session(user)
    return {"url": url}


@app.post("/billing/webhook")
async def billing_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
    stripe_signature: str = Header(None, alias="stripe-signature"),
):
    payload = await request.body()
    event = handle_webhook(payload, stripe_signature or "")

    customer_id, new_plan = plan_from_event(event)
    if customer_id and new_plan:
        result = await db.execute(select(User).where(User.stripe_customer_id == customer_id))
        user = result.scalar_one_or_none()
        if user:
            user.plan = new_plan
            await db.commit()

    return {"received": True}
