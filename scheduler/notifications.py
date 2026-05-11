"""
Shared notification helpers used by both alert_evaluator and digest.

  _send_email_sync(to_addr, subject, body, html_body=None)
  _send_slack(webhook_url, text)
  send_email(to_addr, subject, body, html_body=None)   ← async wrapper

Environment variables consumed:
  SMTP_HOST   required to enable email (default: skip silently)
  SMTP_PORT   default 587
  SMTP_USER   for STARTTLS auth
  SMTP_PASS
  SMTP_FROM   defaults to SMTP_USER
"""

from __future__ import annotations

import asyncio
import logging
import os
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import httpx

logger = logging.getLogger(__name__)


# ── Email ─────────────────────────────────────────────────────────────────────

def _send_email_sync(
    to_addr: str,
    subject: str,
    body: str,
    html_body: str | None = None,
) -> None:
    """Send email via SMTP. Runs in a thread executor (smtplib is sync)."""
    smtp_host = os.environ.get("SMTP_HOST", "")
    if not smtp_host:
        logger.info("SMTP_HOST not set — skipping email to %s", to_addr)
        return

    smtp_port = int(os.environ.get("SMTP_PORT", "587"))
    smtp_user = os.environ.get("SMTP_USER", "")
    smtp_pass = os.environ.get("SMTP_PASS", "")
    smtp_from = os.environ.get("SMTP_FROM", smtp_user)

    if html_body:
        msg: MIMEMultipart | MIMEText = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = smtp_from
        msg["To"] = to_addr
        msg.attach(MIMEText(body, "plain"))
        msg.attach(MIMEText(html_body, "html"))
    else:
        from email.message import EmailMessage
        plain = EmailMessage()
        plain["Subject"] = subject
        plain["From"] = smtp_from
        plain["To"] = to_addr
        plain.set_content(body)
        msg = plain  # type: ignore[assignment]

    context = ssl.create_default_context()
    try:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=15) as smtp:
            smtp.ehlo()
            smtp.starttls(context=context)
            if smtp_user:
                smtp.login(smtp_user, smtp_pass)
            smtp.send_message(msg)
        logger.info("Email sent to %s: %s", to_addr, subject)
    except Exception:  # noqa: BLE001
        logger.exception("Failed to send email to %s", to_addr)


async def send_email(
    to_addr: str,
    subject: str,
    body: str,
    html_body: str | None = None,
) -> None:
    """Async wrapper: runs _send_email_sync in the default thread executor."""
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(
        None, _send_email_sync, to_addr, subject, body, html_body
    )


# ── Slack ─────────────────────────────────────────────────────────────────────

async def send_slack(webhook_url: str, text: str) -> None:
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(webhook_url, json={"text": text})
            if resp.status_code != 200:
                logger.warning(
                    "Slack webhook returned %d: %s", resp.status_code, resp.text[:200]
                )
    except Exception:  # noqa: BLE001
        logger.exception("Failed to send Slack notification")
