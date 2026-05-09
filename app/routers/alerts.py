"""
GET  /api/alerts        — list alert rules for the authenticated org.
POST /api/alerts        — create an alert rule.
DELETE /api/alerts/{id} — delete an alert rule.
"""

from __future__ import annotations

from urllib.parse import urlparse
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.deps import get_org_db

router = APIRouter()

_VALID_METRICS = {
    "revenue_total", "order_count", "delivery_rate",
    "avg_order_value", "event_count", "dau",
}
_VALID_CONDITIONS = {"below", "above", "no_data"}
_VALID_CHANNELS   = {"slack", "email"}

# Private/internal hostname blocklist (SSRF prevention for Slack destinations)
_BLOCKED_DESTINATION_HOSTS = {
    "localhost", "127.0.0.1", "::1", "0.0.0.0",
    "postgres", "app", "nginx", "auth", "scheduler", "frontend",
}


def _validate_destination(channel: str, destination: str) -> None:
    """
    SECURITY: Prevent SSRF via alert destinations.

    - email: must look like an email address (contains @)
    - slack: must be a public https:// URL, not an internal address
    """
    if channel == "email":
        if "@" not in destination or len(destination) < 5:
            raise HTTPException(422, "destination must be a valid email address")
        return

    if channel == "slack":
        try:
            parsed = urlparse(destination)
        except Exception:
            raise HTTPException(422, "destination is not a valid URL")

        if parsed.scheme != "https":
            raise HTTPException(422, "Slack destination must be an https:// URL")

        host = (parsed.hostname or "").lower()
        if not host:
            raise HTTPException(422, "destination URL has no hostname")

        if host in _BLOCKED_DESTINATION_HOSTS:
            raise HTTPException(422, f"destination hostname {host!r} is not allowed")

        if host.endswith((".local", ".internal")):
            raise HTTPException(422, f"destination hostname {host!r} is not allowed")

        import ipaddress
        try:
            addr = ipaddress.ip_address(host)
            if addr.is_private or addr.is_loopback:
                raise HTTPException(422, "destination must be a public URL")
        except ValueError:
            pass  # Not an IP — fine


class AlertRuleCreate(BaseModel):
    name: str
    metric: str
    condition: str
    threshold: float | None = None
    window_hours: int = 24
    channel: str
    destination: str


@router.get("/alerts")
async def list_alert_rules(db: asyncpg.Connection = Depends(get_org_db)):
    rows = await db.fetch(
        """
        SELECT id, name, metric, condition, threshold, window_hours,
               channel, destination, state, last_triggered_at, created_at
        FROM   alert_rules
        ORDER  BY created_at DESC
        """
    )
    return [dict(r) for r in rows]


@router.post("/alerts", status_code=201)
async def create_alert_rule(
    body: AlertRuleCreate,
    db: asyncpg.Connection = Depends(get_org_db),
):
    if body.metric not in _VALID_METRICS:
        raise HTTPException(422, f"unknown metric: {body.metric!r}")
    if body.condition not in _VALID_CONDITIONS:
        raise HTTPException(422, f"invalid condition: {body.condition!r}")
    if body.channel not in _VALID_CHANNELS:
        raise HTTPException(422, f"invalid channel: {body.channel!r}")
    if body.condition != "no_data" and body.threshold is None:
        raise HTTPException(422, "threshold required for 'below'/'above' conditions")
    # SECURITY: validate destination to prevent SSRF
    _validate_destination(body.channel, body.destination)

    row = await db.fetchrow(
        """
        INSERT INTO alert_rules
            (org_id, name, metric, condition, threshold, window_hours,
             channel, destination)
        VALUES
            (current_setting('app.org_id')::uuid,
             $1, $2, $3, $4, $5, $6, $7)
        RETURNING id, name, metric, condition, threshold, window_hours,
                  channel, destination, state, last_triggered_at, created_at
        """,
        body.name,
        body.metric,
        body.condition,
        body.threshold,
        body.window_hours,
        body.channel,
        body.destination,
    )
    return dict(row)


@router.delete("/alerts/{rule_id}", status_code=204)
async def delete_alert_rule(
    rule_id: UUID,
    db: asyncpg.Connection = Depends(get_org_db),
):
    result = await db.execute(
        "DELETE FROM alert_rules WHERE id = $1", rule_id
    )
    # result is e.g. "DELETE 1"; "DELETE 0" means not found (or belongs to another org)
    if result == "DELETE 0":
        raise HTTPException(status_code=404, detail="rule not found")
