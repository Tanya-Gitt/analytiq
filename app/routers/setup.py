"""
GET /api/setup/status — lightweight SDK health check.
Returns the most recent ingest event for the org so the Setup page
can show a live "last event received" indicator.
"""

from __future__ import annotations

import asyncpg
from fastapi import APIRouter, Depends

from app.deps import get_org_db

router = APIRouter()


@router.get("/setup/status")
async def setup_status(db: asyncpg.Connection = Depends(get_org_db)):
    row = await db.fetchrow(
        """
        SELECT event_name, received_at
        FROM   events
        ORDER  BY received_at DESC
        LIMIT  1
        """
    )
    total = await db.fetchval("SELECT COUNT(*) FROM events")

    return {
        "last_event_at":   row["received_at"].isoformat() if row else None,
        "last_event_name": row["event_name"] if row else None,
        "total_events":    total,
    }
