from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base

if TYPE_CHECKING:
    pass

_utc = timezone.utc


def _now() -> datetime:
    return datetime.now(_utc)


def _uuid() -> str:
    return str(uuid.uuid4())


def _api_key() -> str:
    return secrets.token_urlsafe(32)


# Valid plan strings:
#   free
#   personal_annual   family_annual      (Stripe subscription, expires via plan_expires_at)
#   personal_lifetime family_lifetime    (one-time payment, never expires as software)
PLAN_ANNUAL = {"personal_annual", "family_annual"}
PLAN_LIFETIME = {"personal_lifetime", "family_lifetime"}
PLAN_FAMILY = {"family_annual", "family_lifetime"}


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    email: Mapped[str] = mapped_column(String, unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String, nullable=False)
    api_key: Mapped[str] = mapped_column(String, unique=True, nullable=False, default=_api_key, index=True)
    name: Mapped[str] = mapped_column(String, nullable=False, default="")
    plan: Mapped[str] = mapped_column(String, nullable=False, default="free")
    # Annual plans: set to Stripe subscription current_period_end; None = still active
    plan_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Lifetime plans: 2 years of Claude API checking included from purchase date
    api_checking_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    stripe_customer_id: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    guardians: Mapped[list[Guardian]] = relationship(
        "Guardian", back_populates="user", cascade="all, delete-orphan"
    )
    warning_events: Mapped[list[WarningEvent]] = relationship(
        "WarningEvent", back_populates="user", cascade="all, delete-orphan"
    )

    @property
    def is_pro(self) -> bool:
        if self.plan == "free":
            return False
        if self.plan in PLAN_ANNUAL:
            # Active while subscription is live (plan_expires_at not yet passed)
            return self.plan_expires_at is None or self.plan_expires_at > datetime.now(_utc)
        # Lifetime plans: software access never expires
        return self.plan in PLAN_LIFETIME

    @property
    def api_checking_active(self) -> bool:
        """Claude API URL checking. Annual: always active while subscribed.
        Lifetime: 2-year window from purchase; falls back to Safe Browsing only after."""
        if not self.is_pro:
            return False
        if self.plan in PLAN_ANNUAL:
            return True
        # Lifetime: check the 2-year API window
        return (
            self.api_checking_expires_at is None
            or self.api_checking_expires_at > datetime.now(_utc)
        )

    @property
    def guardian_limit(self) -> int:
        return 5 if self.plan in PLAN_FAMILY else 1

    @property
    def plan_tier(self) -> str:
        return "family" if self.plan in PLAN_FAMILY else "personal"

    @property
    def plan_type(self) -> str:
        if self.plan in PLAN_LIFETIME:
            return "lifetime"
        if self.plan in PLAN_ANNUAL:
            return "annual"
        return "free"


class Guardian(Base):
    __tablename__ = "guardians"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String, nullable=False, default="")
    email: Mapped[str] = mapped_column(String, nullable=False, default="")
    phone: Mapped[str] = mapped_column(String, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    user: Mapped[User] = relationship("User", back_populates="guardians")


class WarningEvent(Base):
    __tablename__ = "warning_events"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), nullable=False, index=True)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    verdict: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    risk_level: Mapped[str] = mapped_column(String, nullable=False, default="medium")
    reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    proceeded: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    label: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    user: Mapped[User] = relationship("User", back_populates="warning_events")
