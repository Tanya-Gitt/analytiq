"""
Discord webhook notifications.

Set DISCORD_WEBHOOK_URL env var or pass webhook_url directly.
"""

from __future__ import annotations

import logging
import os

import httpx

logger = logging.getLogger(__name__)

DEFAULT_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL", "")

# Severity → Discord embed colour (decimal)
COLOURS = {
    "critical": 0xE53E3E,
    "warning":  0xDD6B20,
    "info":     0x3182CE,
    "ok":       0x38A169,
}


async def send_discord_alert(
    title: str,
    message: str,
    webhook_url: str | None = None,
    severity: str = "critical",
    fields: list[dict[str, str]] | None = None,
) -> bool:
    """
    Send an embed to Discord.

    Returns True on success, False on failure (never raises).
    """
    url = webhook_url or DEFAULT_WEBHOOK_URL
    if not url:
        logger.warning("Discord webhook URL not configured")
        return False

    colour = COLOURS.get(severity, COLOURS["critical"])

    embed = {
        "title": title,
        "description": message,
        "color": colour,
        "fields": [
            {"name": f["name"], "value": f["value"], "inline": f.get("inline", True)}
            for f in (fields or [])
        ],
    }

    payload = {"embeds": [embed]}

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
        return True
    except Exception as exc:  # pragma: no cover
        logger.error("Discord alert failed: %s", exc)
        return False
