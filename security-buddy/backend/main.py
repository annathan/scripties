from __future__ import annotations

import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv

load_dotenv()

from fastapi import Depends, Header, HTTPException, Request, status  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from pydantic import BaseModel, EmailStr, Field  # noqa: E402
from sqlalchemy import func, select  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

from auth import get_current_user, get_current_user_or_none, hash_password, verify_password
from billing import (
    VALID_PLAN_KEYS,
    apply_event,
    create_checkout_session,
    create_portal_session,
    verify_webhook,
)
from check_url import check_url
from database import get_db, init_db
from models import PLAN_LIFETIME, Guardian, User, WarningEvent
from notify import send_guardian_email, send_guardian_sms


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(title="Safety Buddy Backend", lifespan=lifespan)

_raw_origins = os.environ.get("ALLOWED_ORIGINS", "*")
allowed_origins = [o.strip() for o in _raw_origins.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
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
    password: str = Field(..., min_length=8)
    name: str = ""


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


@app.post("/auth/register", status_code=status.HTTP_201_CREATED)
async def register(req: RegisterRequest, db: AsyncSession = Depends(get_db)):
    existing = await db.execute(select(User).where(User.email == req.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Email already registered")
    user = User(email=req.email, password_hash=hash_password(req.password), name=req.name)
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
        "plan_tier": user.plan_tier,
        "plan_type": user.plan_type,
        "api_checking_active": user.api_checking_active,
        "api_checking_expires_at": (
            user.api_checking_expires_at.isoformat()
            if user.api_checking_expires_at else None
        ),
        "plan_expires_at": (
            user.plan_expires_at.isoformat()
            if user.plan_expires_at else None
        ),
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
    return [{"id": g.id, "name": g.name, "email": g.email, "phone": g.phone}
            for g in result.scalars().all()]


@app.post("/guardians", status_code=status.HTTP_201_CREATED)
async def add_guardian(
    req: GuardianIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(func.count(Guardian.id)).where(Guardian.user_id == user.id)
    )
    if result.scalar_one() >= user.guardian_limit:
        raise HTTPException(
            status_code=403,
            detail=f"Your plan supports {user.guardian_limit} guardian(s). Upgrade for more.",
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
    # Annual plans always use Claude. Lifetime plans use Claude within their 2-year window;
    # after that they fall back to Safe Browsing only. Unauthenticated users also get Claude
    # (free tier — fail open so the extension works without an account).
    use_claude = True if user is None else user.api_checking_active
    result = await check_url(req.url, req.page_title, use_claude=use_claude)

    if user and not result.get("safe", True):
        db.add(WarningEvent(
            user_id=user.id,
            url=req.url,
            verdict=False,
            risk_level=result.get("risk_level", "medium"),
            reason=result.get("reason", ""),
        ))
        await db.commit()

    return result


# ---------------------------------------------------------------------------
# Notify  (Pro plan only)
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
    for g in result.scalars().all():
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

    if req.proceeded:
        db.add(WarningEvent(
            user_id=user.id, url=req.url, verdict=False,
            risk_level=req.risk_level, reason=req.reason, proceeded=True,
        ))
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
    for g in result.scalars().all():
        if g.phone:
            await send_guardian_sms(
                to_phone=g.phone,
                guardian_name=g.name,
                user_name=user.name or "Your family member",
                label=req.label,
            )

    db.add(WarningEvent(
        user_id=user.id, url=req.url, verdict=False,
        risk_level="high", reason=f"Visited {req.label} page", label=req.label,
    ))
    await db.commit()
    return {"sent": True}


# ---------------------------------------------------------------------------
# Billing
# ---------------------------------------------------------------------------

class CheckoutRequest(BaseModel):
    plan_key: str


@app.post("/billing/checkout")
async def billing_checkout(
    req: CheckoutRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if req.plan_key not in VALID_PLAN_KEYS:
        raise HTTPException(status_code=400, detail=f"Invalid plan: {req.plan_key}")
    if req.plan_key == "api_renewal" and user.plan not in PLAN_LIFETIME:
        raise HTTPException(status_code=400, detail="API renewal is only for lifetime plan holders.")
    url = await create_checkout_session(user, db, req.plan_key)
    return {"url": url}


@app.post("/billing/portal")
async def billing_portal(user: User = Depends(get_current_user)):
    url = await create_portal_session(user)
    return {"url": url}


@app.post("/billing/webhook")
async def billing_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
    paddle_signature: str = Header(None, alias="paddle-signature"),
):
    # IMPORTANT: do not add body-consuming middleware upstream — it would break
    # signature verification (raw bytes required).
    payload = await request.body()
    verify_webhook(payload, paddle_signature or "")
    import json
    event = json.loads(payload)
    updates = apply_event(event)

    if updates:
        user_id = updates.pop("user_id", None)
        if not user_id:
            return {"received": True}

        result = await db.execute(select(User).where(User.id == user_id))
        user: User | None = result.scalar_one_or_none()

        if user:
            for field, value in updates.items():
                setattr(user, field, value)
            await db.commit()

    return {"received": True}
