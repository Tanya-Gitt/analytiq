"""
Path Analysis — discover the sequences of events users actually take.

GET /api/paths/events  — list distinct event names (for dropdown)
GET /api/paths         — top N event sequences starting from a given event
"""

from __future__ import annotations

import asyncpg
from fastapi import APIRouter, Depends, Query

from app.deps import get_org_db

router = APIRouter()


@router.get("/paths/events")
async def list_events(db: asyncpg.Connection = Depends(get_org_db)):
    """Return distinct event names seen in the last 30 days."""
    rows = await db.fetch(
        """
        SELECT DISTINCT event_name
        FROM   events
        WHERE  received_at > NOW() - INTERVAL '30 days'
        ORDER  BY event_name
        """
    )
    return [r["event_name"] for r in rows]


def _build_paths_query(steps: int) -> str:
    """
    Build a safe dynamic SQL query for path chains of length `steps` (2–5).
    steps is validated by FastAPI as int 2-5 — never raw user input in SQL.
    """
    # SELECT columns
    select_cols = ", ".join(f"e{i}.event_name AS step{i}" for i in range(1, steps + 1))

    # JOIN clauses (e1 is the anchor, e2..eN are successive steps)
    joins = "\n".join(
        f"JOIN ordered e{i} ON e{i}.user_id = e1.user_id AND e{i}.seq = e1.seq + {i - 1}"
        for i in range(2, steps + 1)
    )

    # GROUP BY / ORDER BY
    group_cols = ", ".join(f"step{i}" for i in range(1, steps + 1))

    return f"""
        WITH ordered AS (
            SELECT user_id, event_name,
                   ROW_NUMBER() OVER (PARTITION BY user_id ORDER BY received_at) AS seq
            FROM   events
            WHERE  user_id IS NOT NULL
              AND  received_at > NOW() - INTERVAL '30 days'
        ),
        chains AS (
            SELECT {select_cols}
            FROM   ordered e1
            {joins}
            WHERE  e1.event_name = $1
        )
        SELECT {group_cols}, COUNT(*) AS users
        FROM   chains
        GROUP  BY {group_cols}
        ORDER  BY users DESC
        LIMIT  $2
    """


@router.get("/paths")
async def get_paths(
    start_event: str,
    steps:       int = Query(3, ge=2, le=5),
    limit:       int = Query(10, ge=1, le=50),
    db:          asyncpg.Connection = Depends(get_org_db),
):
    """
    Return the top `limit` event sequences of length `steps` that begin with
    `start_event`.  Uses a window-function chain approach on the events table.
    """
    sql = _build_paths_query(steps)
    rows = await db.fetch(sql, start_event, limit)

    total_users = await db.fetchval(
        """
        SELECT COUNT(DISTINCT user_id)
        FROM   events
        WHERE  event_name = $1
          AND  received_at > NOW() - INTERVAL '30 days'
        """,
        start_event,
    )

    paths = []
    for row in rows:
        paths.append({
            "steps": [row[f"step{i}"] for i in range(1, steps + 1)],
            "users": row["users"],
        })

    return {
        "paths":       paths,
        "start_event": start_event,
        "total_users": total_users or 0,
        "steps":       steps,
    }
