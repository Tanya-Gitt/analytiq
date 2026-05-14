"""
Embedded Analytics / White-label

POST /api/embed/tokens           — create an embed token (admin)
GET  /api/embed/tokens           — list tokens for this org
DELETE /api/embed/tokens/{id}    — revoke a token
GET  /api/embed/public/{token}   — public endpoint: return widget data (no auth)
"""

from __future__ import annotations

import secrets
from datetime import datetime, timezone
from typing import Any

import asyncpg
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.audit_log import log_action
from app.database import get_pool
from app.deps import get_org_db, require_admin

router = APIRouter()


# ── Schemas ────────────────────────────────────────────────────────────────────

class EmbedTokenCreate(BaseModel):
    name:        str
    widget_type: str          # "events_chart" | "funnel" | "top_events"
    config:      dict[str, Any] = {}
    expires_days: int | None = None


# ── Admin: CRUD tokens ────────────────────────────────────────────────────────

@router.post("/embed/tokens", status_code=201)
async def create_embed_token(
    body:         EmbedTokenCreate,
    db:           asyncpg.Connection = Depends(get_org_db),
    current_user: dict = Depends(require_admin),
):
    token = secrets.token_urlsafe(32)

    expires_at = None
    if body.expires_days:
        from datetime import timedelta
        expires_at = datetime.now(timezone.utc) + timedelta(days=body.expires_days)

    import json
    row = await db.fetchrow(
        """
        INSERT INTO embed_tokens (org_id, token, name, widget_type, config, expires_at)
        VALUES (current_setting('app.org_id')::uuid, $1, $2, $3, $4::jsonb, $5)
        RETURNING id, token, name, widget_type, config, expires_at, created_at
        """,
        token, body.name, body.widget_type,
        json.dumps(body.config), expires_at,
    )
    await log_action(db, current_user["sub"], "embed.token_created",
                     resource_type="embed_token", resource_id=str(row["id"]))
    return {
        "id":          row["id"],
        "token":       row["token"],
        "name":        row["name"],
        "widget_type": row["widget_type"],
        "config":      dict(row["config"]) if row["config"] else {},
        "expires_at":  row["expires_at"].isoformat() if row["expires_at"] else None,
        "created_at":  row["created_at"].isoformat(),
    }


@router.get("/embed/tokens")
async def list_embed_tokens(
    db:           asyncpg.Connection = Depends(get_org_db),
    current_user: dict = Depends(require_admin),
):
    rows = await db.fetch(
        """
        SELECT id, name, widget_type, config, expires_at, created_at,
               LEFT(token, 8) || '...' AS token_prefix
        FROM embed_tokens
        ORDER BY created_at DESC
        """
    )
    return [
        {
            "id":           r["id"],
            "name":         r["name"],
            "widget_type":  r["widget_type"],
            "config":       dict(r["config"]) if r["config"] else {},
            "expires_at":   r["expires_at"].isoformat() if r["expires_at"] else None,
            "created_at":   r["created_at"].isoformat(),
            "token_prefix": r["token_prefix"],
        }
        for r in rows
    ]


@router.delete("/embed/tokens/{token_id}", status_code=200)
async def revoke_embed_token(
    token_id:     int,
    db:           asyncpg.Connection = Depends(get_org_db),
    current_user: dict = Depends(require_admin),
):
    result = await db.execute(
        "DELETE FROM embed_tokens WHERE id = $1", token_id
    )
    if result == "DELETE 0":
        raise HTTPException(404, "Token not found")
    await log_action(db, current_user["sub"], "embed.token_revoked",
                     resource_type="embed_token", resource_id=str(token_id))
    return {"revoked": True}


# ── Public widget endpoint (no JWT auth — embed token IS the credential) ──────

@router.get("/embed/public/{token}")
async def public_widget_data(
    token: str,
    pool:  asyncpg.Pool = Depends(get_pool),
):
    """
    Returns widget data for an embedded token.
    No JWT authentication required — the opaque embed token IS the credential.

    This endpoint uses get_pool (not get_org_db) so that callers without a
    Bearer token can access it.  RLS is still enforced: we look up the token's
    org_id and set app.org_id manually before any data queries.
    """
    # ── 1. Look up token (no org_id filter — token is globally unique) ─────────
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute("SET LOCAL ROLE app_role")
            row = await conn.fetchrow(
                """
                SELECT id, org_id, widget_type, config, expires_at
                FROM embed_tokens
                WHERE token = $1
                """,
                token,
            )

    if not row:
        raise HTTPException(404, "Invalid embed token")

    if row["expires_at"] and row["expires_at"].replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        raise HTTPException(410, "Embed token expired")

    org_id      = str(row["org_id"])
    cfg         = dict(row["config"]) if row["config"] else {}
    widget_type = row["widget_type"]
    data: dict[str, Any] = {}

    # ── 2. Fetch widget data with RLS scoped to the token's org ─────────────────
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute("SET LOCAL ROLE app_role")
            await conn.execute(f"SET LOCAL app.org_id = '{org_id}'")

            if widget_type == "events_chart":
                days = cfg.get("days", 7)
                # Clamp days to a safe range to prevent DoS via huge intervals
                days = max(1, min(int(days), 365))
                rows2 = await conn.fetch(
                    """
                    SELECT DATE(received_at) AS day, COUNT(*) AS cnt
                    FROM events
                    WHERE received_at >= NOW() - ($1 || ' days')::interval
                    GROUP BY 1 ORDER BY 1
                    """,
                    str(days),
                )
                data = {"series": [{"date": str(r["day"]), "events": r["cnt"]} for r in rows2]}

            elif widget_type == "top_events":
                limit = max(1, min(int(cfg.get("limit", 5)), 20))
                rows2 = await conn.fetch(
                    """
                    SELECT event_name, COUNT(*) AS cnt
                    FROM events
                    WHERE received_at >= NOW() - INTERVAL '7 days'
                    GROUP BY event_name ORDER BY cnt DESC LIMIT $1
                    """,
                    limit,
                )
                data = {"events": [{"name": r["event_name"], "count": r["cnt"]} for r in rows2]}

            elif widget_type == "funnel":
                steps = cfg.get("steps", [])
                step_counts = []
                for step in steps:
                    cnt = await conn.fetchval(
                        "SELECT COUNT(DISTINCT user_id) FROM events WHERE event_name = $1",
                        step,
                    ) or 0
                    step_counts.append({"step": step, "users": cnt})
                data = {"funnel": step_counts}

    return {
        "widget_type": widget_type,
        "config":      cfg,
        "data":        data,
    }
