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


def _cache_key(org_id: str, endpoint: str, days: int, **extras: str | None) -> tuple:
    return (org_id, endpoint, days) + tuple(sorted(extras.items()))


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
    channel: str | None = Query(default=None),
    org_id: str = Depends(get_org_id_from_jwt),
    db: asyncpg.Connection = Depends(get_org_db),
):
    """
    Returns:
      revenue_trend        — [{date, revenue}] per day
      top_channels         — [{channel, revenue}] top 10 by revenue
      delivery_rate        — float 0–1 or null
      total_orders         — int
      total_revenue        — float
      prev_total_orders    — int  (prior period, same length)
      prev_total_revenue   — float
      available_channels   — list[str]
    """
    key = _cache_key(org_id, "segment-b", days, channel=channel or "")
    if key in _dashboard_cache:
        return _dashboard_cache[key]

    # Build optional channel filter fragment
    ch_filter = "AND channel = $2" if channel else ""
    params_trend = [str(days), channel] if channel else [str(days)]

    # Revenue trend
    revenue_trend = await db.fetch(
        f"""
        SELECT order_date::text AS date,
               COALESCE(SUM(quantity * price_per_unit), 0)::float AS revenue
        FROM   orders
        WHERE  order_date >= CURRENT_DATE - ($1 || ' days')::interval
          {ch_filter}
        GROUP  BY order_date
        ORDER  BY order_date
        """,
        *params_trend,
    )

    # Top channels by revenue (ignore channel filter here — always show all)
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

    # Current period totals
    totals = await db.fetchrow(
        f"""
        SELECT COUNT(*)::int                                          AS total_orders,
               COALESCE(SUM(quantity * price_per_unit), 0)::float    AS total_revenue
        FROM   orders
        WHERE  order_date >= CURRENT_DATE - ($1 || ' days')::interval
          {ch_filter}
        """,
        *params_trend,
    )

    # Previous period totals (same window length, shifted back)
    prev_params = [str(days), str(days * 2)] + ([channel] if channel else [])
    prev_ch_filter = f"AND channel = ${3 if channel else 'X'}" if channel else ""
    prev_totals = await db.fetchrow(
        f"""
        SELECT COUNT(*)::int                                          AS total_orders,
               COALESCE(SUM(quantity * price_per_unit), 0)::float    AS total_revenue
        FROM   orders
        WHERE  order_date >= CURRENT_DATE - ($2 || ' days')::interval
          AND  order_date <  CURRENT_DATE - ($1 || ' days')::interval
          {'AND channel = $3' if channel else ''}
        """,
        *prev_params,
    )

    # Delivery rate
    delivery_rate: float | None = await db.fetchval(
        f"""
        SELECT (COUNT(*) FILTER (WHERE delivered = TRUE))::float /
               NULLIF(COUNT(*) FILTER (WHERE delivered IS NOT NULL), 0)
        FROM   orders
        WHERE  order_date >= CURRENT_DATE - ($1 || ' days')::interval
          {ch_filter}
        """,
        *params_trend,
    )

    # Available channels for filter dropdown
    channels_rows = await db.fetch(
        """
        SELECT DISTINCT channel FROM orders
        WHERE  channel IS NOT NULL
        ORDER  BY channel
        """
    )

    # Top products by revenue
    top_products = await db.fetch(
        f"""
        SELECT product_name,
               COALESCE(SUM(quantity * price_per_unit), 0)::float AS revenue,
               SUM(quantity)::int                                  AS units_sold
        FROM   orders
        WHERE  product_name IS NOT NULL
          AND  order_date >= CURRENT_DATE - ($1 || ' days')::interval
          {ch_filter}
        GROUP  BY product_name
        ORDER  BY revenue DESC
        LIMIT  8
        """,
        *params_trend,
    )

    # AOV trend (average order value per day)
    aov_trend = await db.fetch(
        f"""
        SELECT order_date::text AS date,
               AVG(quantity * price_per_unit)::float AS aov
        FROM   orders
        WHERE  order_date >= CURRENT_DATE - ($1 || ' days')::interval
          {ch_filter}
        GROUP  BY order_date
        ORDER  BY order_date
        """,
        *params_trend,
    )

    # Revenue by region
    revenue_by_region = await db.fetch(
        f"""
        SELECT region,
               COALESCE(SUM(quantity * price_per_unit), 0)::float AS revenue
        FROM   orders
        WHERE  region IS NOT NULL
          AND  order_date >= CURRENT_DATE - ($1 || ' days')::interval
          {ch_filter}
        GROUP  BY region
        ORDER  BY revenue DESC
        LIMIT  8
        """,
        *params_trend,
    )

    result = {
        "revenue_trend":       [dict(r) for r in revenue_trend],
        "top_channels":        [dict(r) for r in top_channels],
        "top_products":        [dict(r) for r in top_products],
        "aov_trend":           [dict(r) for r in aov_trend],
        "revenue_by_region":   [dict(r) for r in revenue_by_region],
        "delivery_rate":       delivery_rate,
        "total_orders":        totals["total_orders"],
        "total_revenue":       totals["total_revenue"],
        "prev_total_orders":   prev_totals["total_orders"],
        "prev_total_revenue":  prev_totals["total_revenue"],
        "available_channels":  [r["channel"] for r in channels_rows],
    }
    _dashboard_cache[key] = result
    return result


# ── Segment A: events / engagement ───────────────────────────────────────────

@router.get("/dashboard/segment-a")
async def dashboard_segment_a(
    days: int = Query(default=30, ge=1, le=365),
    event_type: str | None = Query(default=None),
    org_id: str = Depends(get_org_id_from_jwt),
    db: asyncpg.Connection = Depends(get_org_db),
):
    """
    Returns:
      events_timeline      — [{date, count}] per day
      top_events           — [{event_name, count}] top 10
      dau                  — float or null
      total_events         — int
      prev_total_events    — int  (prior period, same length)
      available_event_types — list[str]
    """
    key = _cache_key(org_id, "segment-a", days, event_type=event_type or "")
    if key in _dashboard_cache:
        return _dashboard_cache[key]

    et_filter = "AND event_name = $2" if event_type else ""
    params = [str(days), event_type] if event_type else [str(days)]

    # Events timeline
    events_timeline = await db.fetch(
        f"""
        SELECT DATE(received_at)::text AS date,
               COUNT(*)::int           AS count
        FROM   events
        WHERE  received_at >= NOW() - ($1 || ' days')::interval
          {et_filter}
        GROUP  BY DATE(received_at)
        ORDER  BY date
        """,
        *params,
    )

    # Top 10 event types (always unfiltered — shows relative ranking)
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

    # Current period total
    total_events: int = await db.fetchval(
        f"""
        SELECT COUNT(*)::int FROM events
        WHERE  received_at >= NOW() - ($1 || ' days')::interval
          {et_filter}
        """,
        *params,
    ) or 0

    # Previous period total
    prev_params = [str(days), str(days * 2)] + ([event_type] if event_type else [])
    prev_total_events: int = await db.fetchval(
        f"""
        SELECT COUNT(*)::int FROM events
        WHERE  received_at >= NOW() - ($2 || ' days')::interval
          AND  received_at <  NOW() - ($1 || ' days')::interval
          {'AND event_name = $3' if event_type else ''}
        """,
        *prev_params,
    ) or 0

    # DAU
    dau: float | None = await db.fetchval(
        f"""
        SELECT AVG(daily_users)::float
        FROM (
            SELECT DATE(received_at) AS day,
                   COUNT(DISTINCT user_id)::float AS daily_users
            FROM   events
            WHERE  received_at >= NOW() - ($1 || ' days')::interval
              AND  user_id IS NOT NULL
              {et_filter}
            GROUP  BY DATE(received_at)
        ) sub
        """,
        *params,
    )

    # Available event types for filter dropdown
    et_rows = await db.fetch(
        """
        SELECT DISTINCT event_name FROM events
        WHERE  event_name IS NOT NULL
        ORDER  BY event_name
        """
    )

    # Conversion funnel — counts for standard funnel steps (if data exists)
    funnel_steps = ["page_view", "product_viewed", "add_to_cart", "checkout_started", "purchase_completed"]
    funnel_rows = await db.fetch(
        """
        SELECT event_name, COUNT(DISTINCT user_id)::int AS users
        FROM   events
        WHERE  received_at  >= NOW() - ($1 || ' days')::interval
          AND  user_id IS NOT NULL
          AND  event_name = ANY($2::text[])
        GROUP  BY event_name
        """,
        str(days),
        funnel_steps,
    )
    # Build ordered funnel preserving step order, fill 0 for missing steps
    funnel_map = {r["event_name"]: r["users"] for r in funnel_rows}
    funnel = [
        {"step": step, "users": funnel_map.get(step, 0)}
        for step in funnel_steps
    ]

    # New vs returning users per day
    new_vs_returning = await db.fetch(
        f"""
        SELECT
            DATE(received_at)::text AS date,
            COUNT(DISTINCT CASE WHEN first_seen = DATE(received_at) THEN user_id END)::int AS new_users,
            COUNT(DISTINCT CASE WHEN first_seen < DATE(received_at)  THEN user_id END)::int AS returning_users
        FROM (
            SELECT user_id,
                   DATE(received_at) AS day,
                   received_at,
                   MIN(DATE(received_at)) OVER (PARTITION BY user_id) AS first_seen
            FROM   events
            WHERE  received_at >= NOW() - ($1 || ' days')::interval
              AND  user_id IS NOT NULL
              {et_filter}
        ) sub
        GROUP  BY DATE(received_at)
        ORDER  BY date
        """,
        *params,
    )

    result = {
        "events_timeline":      [dict(r) for r in events_timeline],
        "top_events":           [dict(r) for r in top_events],
        "funnel":               funnel,
        "new_vs_returning":     [dict(r) for r in new_vs_returning],
        "dau":                  dau,
        "total_events":         total_events,
        "prev_total_events":    prev_total_events,
        "available_event_types": [r["event_name"] for r in et_rows],
    }
    _dashboard_cache[key] = result
    return result
