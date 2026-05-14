"""Notification channel integrations: Slack, Teams, Discord, PagerDuty, Email."""

from __future__ import annotations

import logging
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

logger = logging.getLogger(__name__)


async def send_email(
    to: list[str],
    subject: str,
    body: str,
    html: bool = False,
) -> bool:
    """
    Send an email via SMTP.

    Config is read from environment variables:
      SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, SMTP_FROM

    Returns True on success, False on failure (never raises).
    """
    host     = os.environ.get("SMTP_HOST", "")
    port     = int(os.environ.get("SMTP_PORT", "587"))
    user     = os.environ.get("SMTP_USER", "")
    password = os.environ.get("SMTP_PASSWORD", "")
    from_    = os.environ.get("SMTP_FROM", user)

    if not host:
        logger.warning("SMTP_HOST not configured — email not sent")
        return False

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = from_
        msg["To"]      = ", ".join(to)

        part = MIMEText(body, "html" if html else "plain")
        msg.attach(part)

        with smtplib.SMTP(host, port, timeout=10) as smtp:
            smtp.ehlo()
            if smtp.has_extn("STARTTLS"):
                smtp.starttls()
                smtp.ehlo()
            if user and password:
                smtp.login(user, password)
            smtp.sendmail(from_, to, msg.as_string())
        return True
    except Exception as exc:  # pragma: no cover
        logger.error("Email send failed: %s", exc)
        return False
