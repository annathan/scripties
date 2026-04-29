from __future__ import annotations

import asyncio
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText


def _build_email_html(
    guardian_name: str,
    user_name: str,
    url: str,
    reason: str,
    risk_level: str,
    proceeded: bool,
) -> tuple[str, str]:
    action = "tried to visit" if not proceeded else "visited (after choosing to continue)"
    risk_label = {"low": "low", "medium": "some", "high": "serious"}.get(risk_level, "some")

    subject = f"Safety Buddy: {user_name} {action} a website that looks risky"

    html = f"""
    <html><body style="font-family:sans-serif;font-size:18px;line-height:1.6;color:#222;max-width:600px;margin:auto;padding:24px;">
      <p>Hi {guardian_name},</p>
      <p>
        Safety Buddy wanted to let you know that <strong>{user_name}</strong> {action} a website
        that looked like it might have {risk_label} risk.
      </p>
      <table style="background:#fff8e1;border-radius:8px;padding:16px 20px;margin:20px 0;width:100%;">
        <tr><td><strong>Website:</strong></td><td style="word-break:break-all;">{url}</td></tr>
        <tr><td><strong>What Safety Buddy noticed:</strong></td><td>{reason}</td></tr>
        <tr><td><strong>Did they continue?</strong></td><td>{"Yes" if proceeded else "No — they went back to safety"}</td></tr>
      </table>
      <p>
        {"You may want to give them a quick call to check in." if proceeded else "They went back to safety, so you don't need to do anything right now."}
      </p>
      <p>
        This message was sent automatically by Safety Buddy.<br>
        <span style="font-size:14px;color:#888;">
          To stop receiving these messages, open Safety Buddy in your browser and clear the guardian email field.
        </span>
      </p>
      <p>Take care,<br><strong>Safety Buddy 🛡️</strong></p>
    </body></html>
    """

    plain = (
        f"Hi {guardian_name},\n\n"
        f"Safety Buddy wanted to let you know that {user_name} {action} a website "
        f"that looked like it might have {risk_label} risk.\n\n"
        f"Website: {url}\n"
        f"What Safety Buddy noticed: {reason}\n"
        f"Did they continue? {'Yes' if proceeded else 'No — they went back to safety'}\n\n"
        f"{'You may want to give them a quick call.' if proceeded else 'They went back to safety, so you don\\'t need to do anything right now.'}\n\n"
        f"Safety Buddy 🛡️\n"
        f"(To stop receiving these messages, open Safety Buddy and clear the guardian email field.)"
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

    with smtplib.SMTP(smtp_host, smtp_port) as smtp:
        smtp.starttls()
        smtp.login(smtp_user, smtp_pass)
        smtp.sendmail(from_email, to_email, msg.as_string())


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

    subject, html, plain = _build_email_html(
        guardian_name, user_name, url, reason, risk_level, proceeded
    )
    await asyncio.to_thread(_smtp_send, to_email, subject, html, plain)


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

    from twilio.rest import Client as TwilioClient  # imported here so twilio is optional

    message_body = (
        f"Safety Buddy: {user_name} is on a {label} page right now. "
        f"Gift card and money transfer requests are a common scam. "
        f"Call them if something seems off."
    )

    def _send():
        TwilioClient(sid, token).messages.create(
            body=message_body,
            from_=from_number,
            to=to_phone,
        )

    await asyncio.to_thread(_send)
