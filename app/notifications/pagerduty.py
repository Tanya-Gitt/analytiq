"""
PagerDuty Events API v2 integration.

Set PAGERDUTY_ROUTING_KEY env var or pass routing_key directly.
Documentation: https://developer.pagerduty.com/docs/events-api-v2/trigger-events/
"""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx

logger = logging.getLogger(__name__)

EVENTS_URL = "https://events.pagerduty.com/v2/enqueue"
DEFAULT_ROUTING_KEY = os.environ.get("PAGERDUTY_ROUTING_KEY", "")


async def trigger_incident(
    summary: str,
    source: str = "analytiq",
    severity: str = "critical",
    routing_key: str | None = None,
    dedup_key: str | None = None,
    custom_details: dict[str, Any] | None = None,
) -> str | None:
    """
    Trigger a PagerDuty incident.

    severity: critical | error | warning | info
    Returns the dedup_key (for later resolve) or None on failure.
    """
    key = routing_key or DEFAULT_ROUTING_KEY
    if not key:
        logger.warning("PagerDuty routing key not configured")
        return None

    payload: dict[str, Any] = {
        "routing_key": key,
        "event_action": "trigger",
        "payload": {
            "summary": summary,
            "source": source,
            "severity": severity,
            "custom_details": custom_details or {},
        },
    }
    if dedup_key:
        payload["dedup_key"] = dedup_key

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(EVENTS_URL, json=payload)
            resp.raise_for_status()
            data = resp.json()
            return data.get("dedup_key") or dedup_key
    except Exception as exc:  # pragma: no cover
        logger.error("PagerDuty trigger failed: %s", exc)
        return None


async def resolve_incident(
    dedup_key: str,
    routing_key: str | None = None,
) -> bool:
    """Resolve a previously triggered incident by dedup_key."""
    key = routing_key or DEFAULT_ROUTING_KEY
    if not key:
        return False

    payload = {
        "routing_key": key,
        "dedup_key": dedup_key,
        "event_action": "resolve",
    }

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(EVENTS_URL, json=payload)
            resp.raise_for_status()
        return True
    except Exception as exc:  # pragma: no cover
        logger.error("PagerDuty resolve failed: %s", exc)
        return False
