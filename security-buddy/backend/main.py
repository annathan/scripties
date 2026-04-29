from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from check_url import check_url
from notify import send_guardian_email, send_guardian_sms

app = FastAPI(title="Safety Buddy Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["POST", "GET"],
    allow_headers=["*"],
)


class CheckUrlRequest(BaseModel):
    url: str
    page_title: str = ""


class NotifyRequest(BaseModel):
    guardian_email: str
    guardian_name: str = "there"
    user_name: str = "Your family member"
    url: str
    reason: str = ""
    risk_level: str = "unknown"
    proceeded: bool = False


class UrgentNotifyRequest(BaseModel):
    guardian_phone: str
    guardian_name: str = "there"
    user_name: str = "Your family member"
    url: str
    label: str
    timestamp: str = ""


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/check-url")
async def check_url_endpoint(req: CheckUrlRequest):
    result = await check_url(req.url, req.page_title)
    return result


@app.post("/notify")
async def notify_endpoint(req: NotifyRequest):
    await send_guardian_email(
        to_email=req.guardian_email,
        guardian_name=req.guardian_name,
        user_name=req.user_name,
        url=req.url,
        reason=req.reason,
        risk_level=req.risk_level,
        proceeded=req.proceeded,
    )
    return {"sent": True}


@app.post("/notify-urgent")
async def notify_urgent_endpoint(req: UrgentNotifyRequest):
    await send_guardian_sms(
        to_phone=req.guardian_phone,
        guardian_name=req.guardian_name,
        user_name=req.user_name,
        label=req.label,
    )
    return {"sent": True}
