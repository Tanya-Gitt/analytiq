"""
Dashboard API — returns chart-ready data for Segment A (events) and Segment B (orders).

GET /api/dashboard/segment-b?days=30
GET /api/dashboard/segment-a?days=30

Responses are flat dicts that map directly to the TypeScript types in
frontend/src/lib/api.ts.

Caching:
  All responses are cached in-process for 5 minutes, keyed by (org_id, endpoint, days).
  Cache is invalidated per-org when a connector sync completes successfully, so that
  users see fresh data after a CSV/sheet import without waiting up to 5 minutes.

  Implementation: cachetools.TTLCache (maxsize=200) — evicts LRU entries when full
  and auto-expires stale entries on access. Thread-safe wrapper not needed because
  asyncio runs in a single thread.
"""

from __future__ import annotations

import asyncpg
import cachetools
from fastapi import APIRouter, Depends, Query

from app.deps import get_org_db, get_org_id_from_jwt

router = APIRouter()

# ── Cache ─────────────────────────────────────────────────────────────────────

# keyed by (org_id: str, endpoint: str, days: int) → serialisable dict
# maxsize=200: 100 orgs × 2 segments × ~1 days-bucket each before LRU eviction
_dashboard_cache: cachetools.TTLCache = cachetools.TTLCache(maxsize=200, ttl=300)


def _cache_key(org_id: str, endpoint: str, days: int) -> tuple[str, str, int]:
    return (org_id, endpoint, days)


def invalidate_org_cache(org_id: str) -> None:
    """
    Drop all cached dashboard responses for org_id.

    Called by sync_connector() after a successful upsert so that the next
    dashboard request reflects the newly imported data immediately.
    """
    keys_to_delete = [k for k in list(_dashboard_cache.keys()) if k[0] == org_id]
    for k in keys_to_delete:
        _dashboard_cache.pop(k, None)


# ── Segment B: orders / revenue ───────────────────────────────────────────────

@router.get("/dashboard/segment-b")
async def dashboard_segment_b(
    days: int = Query(default=30, ge=1, le=365),
    org_id: str = Depends(get_org_id_from_jwt),
    db: asyncpg.Connection = Depends(get_org_db),
):
    """
    Returns:
      revenue_trend   — [{date, revenue}] per day
      top_channels    — [{channel, revenue}] top 10 by revenue
      delivery_rate   — float 0–1 or null (if no delivered data)
      total_orders    — int
      total_revenue   — float
    """
    key = _cache_key(org_id, "segment-b", days)
    if key in _dashboard_cache:
        return _dashboard_cache[key]

    # Revenue trend — one row per day in the window
    revenue_trend = await db.fetch(
        """
        SELECT order_date::text AS date,
               COALESCE(SUM(quantity * price_per_unit), 0)::float AS revenue
        FROM   orders
        WHERE  order_date >= CURRENT_DATE - ($1 || ' days')::interval
        GROUP  BY order_date
        ORDER  BY order_date
        """,
        str(days),
    )

    # Top channels by revenue
    top_channels = await db.fetch(
        """
        SELECT channel,
               COALESCE(SUM(quantity * price_per_unit), 0)::float AS revenue
        FROM   orders
        WHERE  channel IS NOT NULL
          AND  order_date >= CURRENT_DATE - ($1 || ' days')::interval
        GROUP  BY channel
        ORDER  BY revenue DESC
        LIMIT  10
        """,
        str(days),
    )

    # Totals
    totals = await db.fetchrow(
        """
        SELECT COUNT(*)::int                                          AS total_orders,
               COALESCE(SUM(quantity * price_per_unit), 0)::float    AS total_revenue
        FROM   orders
        WHERE  order_date >= CURRENT_DATE - ($1 || ' days')::interval
        """,
        str(days),
    )

    # Delivery rate — null if no delivered data
    delivery_rate: float | None = await db.fetchval(
        """
        SELECT (COUNT(*) FILTER (WHERE delivered = TRUE))::float /
               NULLIF(COUNT(*) FILTER (WHERE delivered IS NOT NULL), 0)
        FROM   orders
        WHERE  order_date >= CURRENT_DATE - ($1 || ' days')::interval
        """,
        str(days),
    )

    result = {
        "revenue_trend":  [dict(r) for r in revenue_trend],
        "top_channels":   [dict(r) for r in top_channels],
        "delivery_rate":  delivery_rate,                  # 0.0–1.0 or null
        "total_orders":   totals["total_orders"],
        "total_revenue":  totals["total_revenue"],
    }
    _dashboard_cache[key] = result
    return result


# ── Segment A: events / engagement ───────────────────────────────────────────

@router.get("/dashboard/segment-a")
async def dashboard_segment_a(
    days: int = Query(default=30, ge=1, le=365),
    org_id: str = Depends(get_org_id_from_jwt),
    db: asyncpg.Connection = Depends(get_org_db),
):
    """
    Returns:
      events_timeline — [{date, count}] per day
      top_events      — [{event_name, count}] top 10
      dau             — float or null (average DAU over the window)
      total_events    — int
    """
    key = _cache_key(org_id, "segment-a", days)
    if key in _dashboard_cache:
        return _dashboard_cache[key]

    # Events timeline — one row per day
    events_timeline = await db.fetch(
        """
        SELECT DATE(received_at)::text AS date,
               COUNT(*)::int           AS count
        FROM   events
        WHERE  received_at >= NOW() - ($1 || ' days')::interval
        GROUP  BY DATE(received_at)
        ORDER  BY date
        """,
        str(days),
    )

    # Top 10 event types
    top_events = await db.fetch(
        """
        SELECT event_name,
               COUNT(*)::int AS count
        FROM   events
        WHERE  received_at >= NOW() - ($1 || ' days')::interval
        GROUP  BY event_name
        ORDER  BY count DESC
        LIMIT  10
        """,
        str(days),
    )

    # Total events
    total_events: int = await db.fetchval(
        """
        SELECT COUNT(*)::int FROM events
        WHERE  received_at >= NOW() - ($1 || ' days')::interval
        """,
        str(days),
    ) or 0

    # DAU — average daily unique users over the window (null if no user_id data)
    dau: float | None = await db.fetchval(
        """
        SELECT AVG(daily_users)::float
        FROM (
            SELECT DATE(received_at) AS day,
                   COUNT(DISTINCT user_id)::float AS daily_users
            FROM   events
            WHERE  received_at >= NOW() - ($1 || ' days')::interval
              AND  user_id IS NOT NULL
            GROUP  BY DATE(received_at)
        ) sub
        """,
        str(days),
    )

    result = {
        "events_timeline": [dict(r) for r in events_timeline],
        "top_events":      [dict(r) for r in top_events],
        "dau":             dau,     # average DAU or null
        "total_events":    total_events,
    }
    _dashboard_cache[key] = result
    return result
