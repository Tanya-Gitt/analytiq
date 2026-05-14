"""
Microsoft Teams webhook notifications.

Uses the Incoming Webhook connector URL format:
  https://outlook.office.com/webhook/<tenant>/IncomingWebhook/...

Set TEAMS_WEBHOOK_URL env var or pass webhook_url directly.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx

logger = logging.getLogger(__name__)

DEFAULT_WEBHOOK_URL = os.environ.get("TEAMS_WEBHOOK_URL", "")


async def send_teams_alert(
    title: str,
    message: str,
    webhook_url: str | None = None,
    color: str = "FF0000",
    facts: list[dict[str, str]] | None = None,
) -> bool:
    """
    Send an alert card to Microsoft Teams.

    Returns True on success, False on failure (never raises).
    """
    url = webhook_url or DEFAULT_WEBHOOK_URL
    if not url:
        logger.warning("Teams webhook URL not configured")
        return False

    card: dict[str, Any] = {
        "@type": "MessageCard",
        "@context": "https://schema.org/extensions",
        "themeColor": color,
        "summary": title,
        "sections": [
            {
                "activityTitle": title,
                "activityText": message,
                "facts": facts or [],
                "markdown": True,
            }
        ],
    }

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(url, json=card)
            resp.raise_for_status()
        return True
    except Exception as exc:  # pragma: no cover
        logger.error("Teams alert failed: %s", exc)
        return False
