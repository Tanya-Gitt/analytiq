"""
Churn Prediction

GET /api/churn/summary  — aggregate counts by risk level
GET /api/churn          — users with risk scores, sorted by days inactive
"""

from __future__ import annotations

import asyncpg
from fastapi import APIRouter, Depends, Query

from app.deps import get_org_db

router = APIRouter()

_LEVELS = ("healthy", "warning", "at_risk", "critical")


def _risk_level(days: float) -> str:
    if days > 30:
        return "critical"
    if days > 14:
        return "at_risk"
    if days > 7:
        return "warning"
    return "healthy"


def _risk_score(days: float, events_30d: int) -> int:
    """0 = safe, 100 = churned. Based on inactivity minus recent activity bonus."""
    base   = min(90, int(days * 2.5))
    bonus  = min(10, int(events_30d / 2))
    return max(0, base - bonus)


@router.get("/churn/summary")
async def churn_summary(db: asyncpg.Connection = Depends(get_org_db)):
    row = await db.fetchrow(
        """
        WITH activity AS (
            SELECT
                user_id,
                EXTRACT(EPOCH FROM (NOW() - MAX(received_at))) / 86400 AS days_inactive
            FROM events
            WHERE user_id IS NOT NULL
            GROUP BY user_id
        )
        SELECT
            COUNT(*) FILTER (WHERE days_inactive <= 7)                         AS healthy,
            COUNT(*) FILTER (WHERE days_inactive > 7  AND days_inactive <= 14) AS warning,
            COUNT(*) FILTER (WHERE days_inactive > 14 AND days_inactive <= 30) AS at_risk,
            COUNT(*) FILTER (WHERE days_inactive > 30)                         AS critical,
            COUNT(*)                                                            AS total
        FROM activity
        """,
    )
    return {k: (row[k] or 0) for k in ("healthy", "warning", "at_risk", "critical", "total")}


@router.get("/churn")
async def list_churn(
    risk:   str | None = Query(None, description="Filter: healthy|warning|at_risk|critical"),
    limit:  int        = Query(100, ge=1, le=500),
    offset: int        = Query(0,   ge=0),
    db:     asyncpg.Connection = Depends(get_org_db),
):
    if risk and risk not in _LEVELS:
        from fastapi import HTTPException
        raise HTTPException(400, f"risk must be one of {_LEVELS}")

    # Build SQL-level risk filter so LIMIT doesn't cut off e.g. healthy users
    # when sorting by days_inactive DESC.
    risk_clause = ""
    if risk == "healthy":
        risk_clause = "AND a.days_inactive <= 7"
    elif risk == "warning":
        risk_clause = "AND a.days_inactive > 7  AND a.days_inactive <= 14"
    elif risk == "at_risk":
        risk_clause = "AND a.days_inactive > 14 AND a.days_inactive <= 30"
    elif risk == "critical":
        risk_clause = "AND a.days_inactive > 30"

    rows = await db.fetch(
        f"""
        WITH latest_traits AS (
            SELECT DISTINCT ON (user_id)
                user_id, properties AS traits
            FROM events
            WHERE user_id IS NOT NULL AND event_name = 'identify'
            ORDER BY user_id, received_at DESC
        ),
        activity AS (
            SELECT
                e.user_id,
                MAX(e.received_at)                                                   AS last_seen,
                COUNT(*) FILTER (WHERE e.received_at > NOW() - INTERVAL '7 days')   AS events_7d,
                COUNT(*) FILTER (WHERE e.received_at > NOW() - INTERVAL '30 days')  AS events_30d,
                EXTRACT(EPOCH FROM (NOW() - MAX(e.received_at))) / 86400             AS days_inactive
            FROM events e
            WHERE e.user_id IS NOT NULL
            GROUP BY e.user_id
        )
        SELECT
            a.user_id,
            a.last_seen,
            a.events_7d::int   AS events_7d,
            a.events_30d::int  AS events_30d,
            a.days_inactive,
            COALESCE(t.traits, '{{}}')::jsonb AS traits
        FROM activity a
        LEFT JOIN latest_traits t USING (user_id)
        WHERE 1=1 {risk_clause}
        ORDER BY a.days_inactive DESC
        LIMIT $1 OFFSET $2
        """,
        limit, offset,
    )

    return [
        {
            "user_id":       r["user_id"],
            "last_seen":     r["last_seen"].isoformat() if r["last_seen"] else None,
            "events_7d":     r["events_7d"],
            "events_30d":    r["events_30d"],
            "days_inactive": round(float(r["days_inactive"]), 1),
            "risk_level":    _risk_level(float(r["days_inactive"])),
            "risk_score":    _risk_score(float(r["days_inactive"]), r["events_30d"]),
            "traits":        dict(r["traits"]) if r["traits"] else {},
        }
        for r in rows
    ]
