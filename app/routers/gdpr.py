"""
GDPR / CCPA Compliance

GET    /api/gdpr/export/{user_id}   — data export (right of access)
DELETE /api/gdpr/forget/{user_id}   — erase all data (right to be forgotten)
GET    /api/gdpr/opt-outs           — list opted-out users
POST   /api/gdpr/opt-out            — opt a user out of tracking
DELETE /api/gdpr/opt-out/{user_id}  — re-enable tracking for a user
"""

from __future__ import annotations

import urllib.parse

import asyncpg
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.audit_log import log_action
from app.deps import get_org_db, require_admin

router = APIRouter()


class OptOutRequest(BaseModel):
    user_id: str


# ── Email → user_id resolution ────────────────────────────────────────────────

async def _resolve_uid(db: asyncpg.Connection, raw: str) -> str:
    """
    If `raw` looks like an email address, try to find the canonical user_id
    from events where traits->>'email' matches.  Falls back to `raw` unchanged.
    """
    if "@" not in raw:
        return raw
    canonical = await db.fetchval(
        """
        SELECT user_id FROM events
        WHERE  user_id IS NOT NULL
          AND  properties->>'email' = $1
        ORDER BY received_at DESC
        LIMIT 1
        """,
        raw,
    )
    return canonical if canonical else raw


# ── Data export (right of access) ─────────────────────────────────────────────

@router.get("/gdpr/export/{user_id:path}")
async def export_user_data(
    user_id:      str,
    db:           asyncpg.Connection = Depends(get_org_db),
    current_user: dict = Depends(require_admin),
):
    uid = urllib.parse.unquote(user_id)
    resolved_uid = await _resolve_uid(db, uid)

    events = await db.fetch(
        """
        SELECT event_name, user_id, anonymous_id, properties, received_at
        FROM events WHERE user_id = $1
        ORDER BY received_at DESC
        """,
        resolved_uid,
    )
    opted_out = await db.fetchval(
        "SELECT EXISTS(SELECT 1 FROM gdpr_opt_outs WHERE user_id = $1)", resolved_uid
    )

    await log_action(db, current_user["sub"], "gdpr.export",
                     resource_type="user", resource_id=resolved_uid)

    return {
        "user_id":        resolved_uid,
        "queried_as":     uid if uid != resolved_uid else None,
        "opted_out":      opted_out,
        "events": [
            {
                "event_name":   r["event_name"],
                "properties":   dict(r["properties"]),
                "received_at":  r["received_at"].isoformat(),
                "anonymous_id": r["anonymous_id"],
            }
            for r in events
        ],
        "total_events": len(events),
    }


# ── Right to be forgotten ─────────────────────────────────────────────────────

@router.delete("/gdpr/forget/{user_id:path}", status_code=200)
async def forget_user(
    user_id:      str,
    db:           asyncpg.Connection = Depends(get_org_db),
    current_user: dict = Depends(require_admin),
):
    uid = urllib.parse.unquote(user_id)
    uid = await _resolve_uid(db, uid)

    result = await db.execute("DELETE FROM events WHERE user_id = $1", uid)
    deleted_count = int(result.split()[-1]) if result else 0

    await db.execute("DELETE FROM gdpr_opt_outs WHERE user_id = $1", uid)

    await log_action(db, current_user["sub"], "gdpr.forget",
                     resource_type="user", resource_id=uid,
                     metadata={"events_deleted": deleted_count})

    return {"user_id": uid, "events_deleted": deleted_count, "forgotten": True}


# ── Opt-outs ──────────────────────────────────────────────────────────────────

@router.get("/gdpr/opt-outs")
async def list_opt_outs(
    db:           asyncpg.Connection = Depends(get_org_db),
    current_user: dict = Depends(require_admin),   # admin-only: contains PII (user IDs)
):
    rows = await db.fetch(
        "SELECT user_id, opted_out_at FROM gdpr_opt_outs ORDER BY opted_out_at DESC"
    )
    return [{"user_id": r["user_id"], "opted_out_at": r["opted_out_at"].isoformat()} for r in rows]


@router.post("/gdpr/opt-out", status_code=201)
async def opt_out(
    body:         OptOutRequest,
    db:           asyncpg.Connection = Depends(get_org_db),
    current_user: dict = Depends(require_admin),
):
    try:
        await db.execute(
            """
            INSERT INTO gdpr_opt_outs (org_id, user_id)
            VALUES (current_setting('app.org_id')::uuid, $1)
            ON CONFLICT DO NOTHING
            """,
            body.user_id,
        )
    except Exception as e:
        raise HTTPException(400, str(e))

    await log_action(db, current_user["sub"], "gdpr.opt_out",
                     resource_type="user", resource_id=body.user_id)
    return {"user_id": body.user_id, "opted_out": True}


@router.delete("/gdpr/opt-out/{user_id:path}", status_code=200)
async def remove_opt_out(
    user_id:      str,
    db:           asyncpg.Connection = Depends(get_org_db),
    current_user: dict = Depends(require_admin),
):
    uid = urllib.parse.unquote(user_id)
    result = await db.execute("DELETE FROM gdpr_opt_outs WHERE user_id = $1", uid)
    if result == "DELETE 0":
        raise HTTPException(404, "Opt-out not found")
    await log_action(db, current_user["sub"], "gdpr.opt_out_removed",
                     resource_type="user", resource_id=uid)
    return {"user_id": uid, "opted_out": False}
