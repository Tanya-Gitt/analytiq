"""
User Profiles + Identity

GET /api/people              — paginated list of identified users with traits
GET /api/people/{user_id}    — single user: latest traits + event timeline
"""

from __future__ import annotations

import urllib.parse

import asyncpg
from fastapi import APIRouter, Depends, Query

from app.deps import get_org_db

router = APIRouter()


@router.get("/people")
async def list_people(
    q:      str | None = Query(None, description="Search user_id or trait value"),
    limit:  int        = Query(50,  ge=1, le=200),
    offset: int        = Query(0,   ge=0),
    db:     asyncpg.Connection = Depends(get_org_db),
):
    params: list = [limit, offset]
    search_clause = ""
    if q:
        params = [f"%{q}%", limit, offset]
        search_clause = (
            "AND (s.user_id ILIKE $1 OR COALESCE(t.traits, '{}')::text ILIKE $1)"
        )
        limit_idx, offset_idx = 2, 3
    else:
        limit_idx, offset_idx = 1, 2

    rows = await db.fetch(
        f"""
        WITH latest_traits AS (
            SELECT DISTINCT ON (user_id)
                user_id, properties AS traits
            FROM events
            WHERE user_id IS NOT NULL AND event_name = 'identify'
            ORDER BY user_id, received_at DESC
        ),
        user_stats AS (
            SELECT
                user_id,
                COUNT(*)                                              AS total_events,
                COUNT(*) FILTER (WHERE event_name != 'identify')      AS track_events,
                MIN(received_at)                                       AS first_seen,
                MAX(received_at)                                       AS last_seen
            FROM events
            WHERE user_id IS NOT NULL
            GROUP BY user_id
        )
        SELECT
            s.user_id,
            s.total_events,
            s.track_events,
            s.first_seen,
            s.last_seen,
            COALESCE(t.traits, '{{}}')::jsonb AS traits
        FROM user_stats s
        LEFT JOIN latest_traits t USING (user_id)
        WHERE 1=1 {search_clause}
        ORDER BY s.last_seen DESC
        LIMIT ${limit_idx} OFFSET ${offset_idx}
        """,
        *params,
    )

    total = await db.fetchval(
        "SELECT COUNT(DISTINCT user_id) FROM events WHERE user_id IS NOT NULL"
    )

    return {
        "users":  [_fmt(r) for r in rows],
        "total":  total,
        "limit":  limit,
        "offset": offset,
    }


@router.get("/people/{user_id:path}")
async def get_person(
    user_id: str,
    limit:   int = Query(50, ge=1, le=200),
    offset:  int = Query(0,  ge=0),
    db:      asyncpg.Connection = Depends(get_org_db),
):
    uid = urllib.parse.unquote(user_id)

    traits_row = await db.fetchrow(
        """
        SELECT properties FROM events
        WHERE user_id = $1 AND event_name = 'identify'
        ORDER BY received_at DESC LIMIT 1
        """,
        uid,
    )

    events = await db.fetch(
        """
        SELECT event_name, properties, received_at
        FROM events
        WHERE user_id = $1
        ORDER BY received_at DESC
        LIMIT $2 OFFSET $3
        """,
        uid, limit, offset,
    )

    total = await db.fetchval(
        "SELECT COUNT(*) FROM events WHERE user_id = $1", uid
    )

    return {
        "user_id":      uid,
        "traits":       dict(traits_row["properties"]) if traits_row else {},
        "total_events": total,
        "events": [
            {
                "name":        r["event_name"],
                "properties":  dict(r["properties"]),
                "received_at": r["received_at"].isoformat(),
            }
            for r in events
        ],
        "limit":  limit,
        "offset": offset,
    }


def _fmt(row: asyncpg.Record) -> dict:
    return {
        "user_id":      row["user_id"],
        "total_events": row["total_events"],
        "track_events": row["track_events"],
        "first_seen":   row["first_seen"].isoformat() if row["first_seen"] else None,
        "last_seen":    row["last_seen"].isoformat()  if row["last_seen"]  else None,
        "traits":       dict(row["traits"]) if row["traits"] else {},
    }
