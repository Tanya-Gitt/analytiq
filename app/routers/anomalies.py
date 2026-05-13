"""
GET  /api/anomalies            — list recent anomaly events for the org
GET  /api/anomalies/baselines  — view learned baselines (per metric/dow/hour)
POST /api/anomalies/backfill   — trigger immediate baseline + detection run (admin)
"""

from __future__ import annotations

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query

from app.deps import get_org_db

router = APIRouter()


@router.get("/anomalies")
async def list_anomalies(
    limit:  int = Query(default=50, le=200),
    metric: str | None = Query(default=None),
    db:     asyncpg.Connection = Depends(get_org_db),
):
    """
    Return the most recent anomaly events for the authenticated org.
    Optionally filter by metric name.
    """
    if metric:
        rows = await db.fetch(
            """
            SELECT id, metric, value, baseline, std_dev, z_score,
                   direction, severity, detected_at::text
            FROM   anomaly_events
            WHERE  metric = $1
            ORDER  BY detected_at DESC
            LIMIT  $2
            """,
            metric, limit,
        )
    else:
        rows = await db.fetch(
            """
            SELECT id, metric, value, baseline, std_dev, z_score,
                   direction, severity, detected_at::text
            FROM   anomaly_events
            ORDER  BY detected_at DESC
            LIMIT  $1
            """,
            limit,
        )
    return [dict(r) for r in rows]


@router.get("/anomalies/baselines")
async def list_baselines(
    metric: str | None = Query(default=None),
    db:     asyncpg.Connection = Depends(get_org_db),
):
    """Return the learned DOW+hour baselines for the org (useful for debugging)."""
    if metric:
        rows = await db.fetch(
            """
            SELECT metric, dow, hour, mean, std_dev, sample_count,
                   computed_at::text
            FROM   anomaly_baselines
            WHERE  metric = $1
            ORDER  BY metric, dow, hour
            """,
            metric,
        )
    else:
        rows = await db.fetch(
            """
            SELECT metric, dow, hour, mean, std_dev, sample_count,
                   computed_at::text
            FROM   anomaly_baselines
            ORDER  BY metric, dow, hour
            """,
        )
    return [dict(r) for r in rows]


@router.get("/anomalies/summary")
async def anomaly_summary(db: asyncpg.Connection = Depends(get_org_db)):
    """
    High-level summary: count of anomalies in the last 24h / 7d, by severity.
    Used by the dashboard badge.
    """
    row = await db.fetchrow(
        """
        SELECT
            COUNT(*) FILTER (WHERE detected_at >= NOW() - INTERVAL '24 hours')     AS last_24h,
            COUNT(*) FILTER (WHERE detected_at >= NOW() - INTERVAL '7 days')       AS last_7d,
            COUNT(*) FILTER (WHERE severity = 'critical'
                               AND detected_at >= NOW() - INTERVAL '24 hours')     AS critical_24h,
            COUNT(*) FILTER (WHERE severity = 'warning'
                               AND detected_at >= NOW() - INTERVAL '24 hours')     AS warning_24h
        FROM anomaly_events
        """
    )
    return dict(row) if row else {"last_24h": 0, "last_7d": 0, "critical_24h": 0, "warning_24h": 0}
