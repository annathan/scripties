from __future__ import annotations

import asyncio
import logging
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from html import escape as _he

logger = logging.getLogger(__name__)


def _build_email(
    guardian_name: str,
    user_name: str,
    url: str,
    reason: str,
    risk_level: str,
    proceeded: bool,
) -> tuple[str, str, str]:
    action = "visited (after ignoring a warning)" if proceeded else "tried to visit"
    risk_label = {"low": "low", "medium": "some", "high": "serious"}.get(risk_level, "some")
    subject = f"Safety Buddy: {user_name} {action} a website that looks risky"

    # All user-supplied strings are HTML-escaped before interpolation.
    g = _he(guardian_name)
    u = _he(user_name)
    r = _he(reason)
    safe_url = _he(url)

    html = f"""
    <html><body style="font-family:sans-serif;font-size:18px;line-height:1.6;color:#222;max-width:600px;margin:auto;padding:24px;">
      <p>Hi {g},</p>
      <p><strong>{u}</strong> {action} a website that looked like it might have {risk_label} risk.</p>
      <table style="background:#fff8e1;border-radius:8px;padding:16px 20px;margin:20px 0;width:100%;">
        <tr><td style="padding:4px 8px"><strong>Website:</strong></td><td style="word-break:break-all">{safe_url}</td></tr>
        <tr><td style="padding:4px 8px"><strong>What Safety Buddy noticed:</strong></td><td>{r}</td></tr>
        <tr><td style="padding:4px 8px"><strong>Did they continue?</strong></td><td>{"Yes" if proceeded else "No — they went back to safety"}</td></tr>
      </table>
      <p>{"You may want to give them a quick call to check in." if proceeded else "They went back to safety, so no action is needed right now."}</p>
      <p style="font-size:13px;color:#888;">To stop receiving these messages, open Safety Buddy in your browser and remove the guardian email.</p>
      <p>Safety Buddy 🛡️</p>
    </body></html>
    """

    plain = (
        f"Hi {guardian_name},\n\n"
        f"{user_name} {action} a website that looked like it might have {risk_label} risk.\n\n"
        f"Website: {url}\n"
        f"What Safety Buddy noticed: {reason}\n"
        f"Did they continue? {'Yes' if proceeded else 'No — they went back to safety'}\n\n"
        f"{'You may want to give them a quick call.' if proceeded else 'No action needed right now.'}\n\n"
        "Safety Buddy"
    )
    return subject, html, plain


def _smtp_send(to_email: str, subject: str, html: str, plain: str) -> None:
    smtp_host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.environ.get("SMTP_PORT", "587"))
    smtp_user = os.environ["SMTP_USER"]
    smtp_pass = os.environ["SMTP_PASS"]
    from_email = os.environ.get("FROM_EMAIL", smtp_user)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"Safety Buddy <{from_email}>"
    msg["To"] = to_email
    msg.attach(MIMEText(plain, "plain"))
    msg.attach(MIMEText(html, "html"))

    try:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=15) as smtp:
            smtp.starttls()
            smtp.login(smtp_user, smtp_pass)
            smtp.sendmail(from_email, to_email, msg.as_string())
    except smtplib.SMTPAuthenticationError:
        logger.error("SMTP authentication failed — check SMTP_USER / SMTP_PASS in .env")
        raise
    except smtplib.SMTPException as exc:
        logger.error("SMTP send failed to %s: %s", to_email, exc)
        raise


async def send_guardian_email(
    to_email: str,
    guardian_name: str,
    user_name: str,
    url: str,
    reason: str,
    risk_level: str,
    proceeded: bool,
) -> None:
    if not os.environ.get("SMTP_USER"):
        return  # email not configured — skip silently

    subject, html, plain = _build_email(
        guardian_name, user_name, url, reason, risk_level, proceeded
    )
    try:
        await asyncio.to_thread(_smtp_send, to_email, subject, html, plain)
    except Exception as exc:
        logger.warning("Email notification failed for %s: %s", to_email, exc)


async def send_guardian_sms(
    to_phone: str,
    guardian_name: str,
    user_name: str,
    label: str,
) -> None:
    sid = os.environ.get("TWILIO_ACCOUNT_SID")
    token = os.environ.get("TWILIO_AUTH_TOKEN")
    from_number = os.environ.get("TWILIO_FROM_NUMBER")

    if not (sid and token and from_number):
        return  # SMS not configured — skip silently

    from twilio.rest import Client as TwilioClient

    body = (
        f"Safety Buddy: {user_name} is on a {label} page right now. "
        "Gift card and money transfer requests are a common scam. "
        "Call them if something seems off."
    )

    def _send() -> None:
        try:
            TwilioClient(sid, token).messages.create(
                body=body,
                from_=from_number,
                to=to_phone,
            )
        except Exception as exc:
            logger.warning("SMS notification failed for %s: %s", to_phone, exc)

    await asyncio.to_thread(_send)
