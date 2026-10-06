"""Outgoing email: Resend (production) or SMTP (development)."""
import base64
import json
import smtplib
import urllib.error
import urllib.request
from email.message import EmailMessage

from . import config

_FAKE = ("@example.com", "@example.co.za", "@localhost")


def _resend(to: str, subject: str, text: str, attachment) -> None:
    body = {"from": config.SMTP_FROM or f"{config.APP_NAME} <noreply@localhost>",
            "to": [to], "subject": subject, "text": text}
    if attachment:
        body["attachments"] = [{"filename": attachment[0],
                                "content": base64.b64encode(attachment[1]).decode()}]
    req = urllib.request.Request(
        "https://api.resend.com/emails", data=json.dumps(body).encode(), method="POST",
        headers={"Authorization": f"Bearer {config.RESEND_API_KEY}", "Content-Type": "application/json",
                 "User-Agent": f"{config.APP_NAME}/1.0"})
    try:
        urllib.request.urlopen(req, timeout=20).read()
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Resend {e.code}: {e.read()[:200]!r}") from None


def send(to: str, subject: str, text: str, attachment: tuple[str, bytes] | None = None) -> str:
    if not to or to.lower().endswith(_FAKE):
        return "not sent (placeholder address)"
    if config.RESEND_API_KEY:
        _resend(to, subject, text, attachment)
        return f"sent to {to}"
    if not config.SMTP_HOST or not config.SMTP_PASS:
        return "not sent (email is not set up yet)"
    msg = EmailMessage()
    msg["Subject"], msg["From"], msg["To"] = subject, config.SMTP_FROM, to
    msg.set_content(text)
    if attachment:
        msg.add_attachment(attachment[1], maintype="application", subtype="pdf", filename=attachment[0])
    with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=20) as s:
        s.starttls()
        s.login(config.SMTP_USER, config.SMTP_PASS)
        s.send_message(msg)
    return f"sent to {to}"
