"""
Self-Monitoring Dashboard

GET /api/system/health      — platform health (DB, queue, ingest lag)
GET /api/system/stats       — event volume, error rates (last 24h)
GET /api/system/errors      — recent ingest errors log
GET /api/system/throughput  — events/minute series (last 60 min)
"""

from __future__ import annotations

import time
from datetime import datetime, timezone

import asyncpg
from fastapi import APIRouter, Depends

from app.database import get_pool
from app.deps import get_org_db

router = APIRouter()


# ── Unauthenticated DB wake-up ping ───────────────────────────────────────────

@router.get("/system/ping")
async def ping_db(pool: asyncpg.Pool = Depends(get_pool)):
    """No auth required. Wakes Neon DB from serverless sleep so subsequent
    authenticated requests don't time out waiting for a connection."""
    conn = await pool.acquire()
    try:
        await conn.execute("SELECT 1")
    finally:
        await pool.release(conn)
    return {"ok": True}


# ── Health check ──────────────────────────────────────────────────────────────

@router.get("/system/health")
async def system_health(db: asyncpg.Connection = Depends(get_org_db)):
    """
    Returns an overall platform health summary: database latency,
    event ingestion lag, and queue depth (if tracked).
    """
    # Measure DB round-trip
    t0 = time.monotonic()
    await db.fetchval("SELECT 1")
    db_latency_ms = round((time.monotonic() - t0) * 1000, 1)

    # Most recent event received
    newest = await db.fetchval(
        "SELECT MAX(received_at) FROM events"
    )
    ingest_lag_s = None
    if newest:
        ingest_lag_s = round(
            (datetime.now(timezone.utc) - newest.replace(tzinfo=timezone.utc)).total_seconds(), 1
        )

    # Total events and errors last 24h
    total_24h = await db.fetchval(
        """
        SELECT COUNT(*) FROM events
        WHERE received_at >= NOW() - INTERVAL '24 hours'
        """
    ) or 0

    status = "ok"
    if db_latency_ms > 500:
        status = "degraded"
    if db_latency_ms > 2000:
        status = "critical"

    return {
        "status":          status,
        "db_latency_ms":   db_latency_ms,
        "ingest_lag_s":    ingest_lag_s,
        "events_24h":      total_24h,
        "checked_at":      datetime.now(timezone.utc).isoformat(),
    }


# ── Event stats ───────────────────────────────────────────────────────────────

@router.get("/system/stats")
async def system_stats(db: asyncpg.Connection = Depends(get_org_db)):
    """24-hour event volume and top event types."""
    rows = await db.fetch(
        """
        SELECT
            COUNT(*)                                          AS total,
            COUNT(*) FILTER (WHERE received_at >= NOW() - INTERVAL '1 hour')  AS last_hour,
            COUNT(*) FILTER (WHERE received_at >= NOW() - INTERVAL '1 day')   AS last_day,
            COUNT(*) FILTER (WHERE received_at >= NOW() - INTERVAL '7 days')  AS last_week
        FROM events
        """
    )

    top_events = await db.fetch(
        """
        SELECT event_name, COUNT(*) AS cnt
        FROM events
        WHERE received_at >= NOW() - INTERVAL '24 hours'
        GROUP BY event_name
        ORDER BY cnt DESC
        LIMIT 10
        """
    )

    row = rows[0] if rows else {}
    return {
        "total_all_time":  row.get("total", 0),
        "last_hour":       row.get("last_hour", 0),
        "last_day":        row.get("last_day", 0),
        "last_week":       row.get("last_week", 0),
        "top_events_24h":  [
            {"event_name": r["event_name"], "count": r["cnt"]}
            for r in top_events
        ],
    }


# ── Throughput series ─────────────────────────────────────────────────────────

@router.get("/system/throughput")
async def system_throughput(db: asyncpg.Connection = Depends(get_org_db)):
    """Events per 5-minute bucket for the last 2 hours."""
    rows = await db.fetch(
        """
        SELECT
            date_trunc('minute', received_at) -
              INTERVAL '1 minute' * (EXTRACT(MINUTE FROM received_at)::int % 5) AS bucket,
            COUNT(*) AS cnt
        FROM events
        WHERE received_at >= NOW() - INTERVAL '2 hours'
        GROUP BY 1
        ORDER BY 1
        """
    )
    return [
        {"time": r["bucket"].isoformat(), "events": r["cnt"]}
        for r in rows
    ]


# ── Error log ─────────────────────────────────────────────────────────────────

@router.get("/system/errors")
async def system_errors(db: asyncpg.Connection = Depends(get_org_db)):
    """
    Returns recent schema violations as a proxy for ingest errors.
    Real error logging could also come from a dedicated errors table.
    """
    rows = await db.fetch(
        """
        SELECT event_name, violation_type, sample_payload, occurred_at
        FROM schema_violations
        ORDER BY occurred_at DESC
        LIMIT 50
        """
    )
    return [
        {
            "event_name":     r["event_name"],
            "violation_type": r["violation_type"],
            "payload":        dict(r["sample_payload"]) if r["sample_payload"] else {},
            "occurred_at":    r["occurred_at"].isoformat(),
        }
        for r in rows
    ]
