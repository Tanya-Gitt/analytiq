"""
Tiered Storage

GET  /api/storage/stats    — hot vs archived event counts + size estimates
POST /api/storage/archive  — move events older than N days to archived_events
GET  /api/storage/archived — query archived events (paginated)
"""

from __future__ import annotations

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.audit_log import log_action
from app.deps import get_org_db, require_admin

router = APIRouter()


class ArchiveRequest(BaseModel):
    older_than_days: int = Field(90, ge=7, le=3650, description="Archive events older than N days")


@router.get("/storage/stats")
async def storage_stats(db: asyncpg.Connection = Depends(get_org_db)):
    hot      = await db.fetchval("SELECT COUNT(*) FROM events") or 0
    archived = await db.fetchval("SELECT COUNT(*) FROM archived_events") or 0
    oldest_hot = await db.fetchval("SELECT MIN(received_at) FROM events")
    oldest_archive = await db.fetchval("SELECT MIN(received_at) FROM archived_events")

    return {
        "hot_events":      hot,
        "archived_events": archived,
        "total_events":    hot + archived,
        "oldest_hot":      oldest_hot.isoformat() if oldest_hot else None,
        "oldest_archived": oldest_archive.isoformat() if oldest_archive else None,
        "estimated_hot_mb":      round(hot * 0.0005, 1),
        "estimated_archive_mb":  round(archived * 0.0002, 1),
    }


@router.post("/storage/archive")
async def archive_events(
    body:         ArchiveRequest,
    db:           asyncpg.Connection = Depends(get_org_db),
    current_user: dict = Depends(require_admin),
):
    """Move events older than N days from events → archived_events."""
    result = await db.fetchrow(
        """
        WITH moved AS (
            DELETE FROM events
            WHERE received_at < NOW() - ($1 || ' days')::interval
            RETURNING org_id, event_name, user_id, anonymous_id, properties, received_at
        ),
        inserted AS (
            INSERT INTO archived_events (org_id, event_name, user_id, anonymous_id, properties, received_at)
            SELECT org_id, event_name, user_id, anonymous_id, properties, received_at FROM moved
            RETURNING 1
        )
        SELECT COUNT(*) AS moved FROM inserted
        """,
        str(body.older_than_days),
    )

    moved_count = result["moved"] if result else 0

    await log_action(db, current_user["sub"], "storage.archive",
                     resource_type="events",
                     metadata={"older_than_days": body.older_than_days,
                               "events_archived": moved_count})

    return {
        "events_archived":  moved_count,
        "older_than_days":  body.older_than_days,
    }


@router.get("/storage/archived")
async def list_archived(
    user_id:    str | None = Query(None),
    event_name: str | None = Query(None),
    limit:      int        = Query(100, ge=1, le=500),
    offset:     int        = Query(0,   ge=0),
    db:         asyncpg.Connection = Depends(get_org_db),
):
    params: list = []
    clauses: list[str] = []
    if user_id:
        params.append(user_id)
        clauses.append(f"user_id = ${len(params)}")
    if event_name:
        params.append(f"%{event_name}%")
        clauses.append(f"event_name ILIKE ${len(params)}")
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    params += [limit, offset]

    rows = await db.fetch(
        f"""
        SELECT event_name, user_id, properties, received_at, archived_at
        FROM archived_events
        {where}
        ORDER BY received_at DESC
        LIMIT ${len(params)-1} OFFSET ${len(params)}
        """,
        *params,
    )

    return [
        {
            "event_name":  r["event_name"],
            "user_id":     r["user_id"],
            "properties":  dict(r["properties"]),
            "received_at": r["received_at"].isoformat(),
            "archived_at": r["archived_at"].isoformat(),
        }
        for r in rows
    ]
