"""
Metric evaluation registry for alert rules.

Each metric function receives (conn, org_id, window_hours) and returns
a float | None. None means "no data" — triggers no_data alert rules.

SQL uses make_interval(hours => $2) so the window is parameterized
without string interpolation (no SQL injection risk).
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Coroutine

import asyncpg

logger = logging.getLogger(__name__)

MetricFn = Callable[
    [asyncpg.Connection, str, int],
    Coroutine[Any, Any, float | None],
]


# ── metric implementations ────────────────────────────────────────────────────

async def revenue_total(
    conn: asyncpg.Connection, org_id: str, window_hours: int
) -> float | None:
    """Sum of (price_per_unit * quantity) for orders in the window."""
    row = await conn.fetchrow(
        """
        SELECT SUM(price_per_unit * quantity)::float AS val
        FROM   orders
        WHERE  org_id    = $1
          AND  order_date >= (NOW() - make_interval(hours => $2))::date
        """,
        org_id,
        window_hours,
    )
    return row["val"] if row else None


async def order_count(
    conn: asyncpg.Connection, org_id: str, window_hours: int
) -> float | None:
    """Number of distinct orders in the window."""
    row = await conn.fetchrow(
        """
        SELECT COUNT(*)::float AS val
        FROM   orders
        WHERE  org_id    = $1
          AND  order_date >= (NOW() - make_interval(hours => $2))::date
        """,
        org_id,
        window_hours,
    )
    return row["val"] if row else None


async def delivery_rate(
    conn: asyncpg.Connection, org_id: str, window_hours: int
) -> float | None:
    """
    Fraction of orders with delivered=TRUE in the window.
    Returns None if no orders have a non-null delivered flag.
    """
    row = await conn.fetchrow(
        """
        SELECT
            COUNT(*) FILTER (WHERE delivered = TRUE)::float /
            NULLIF(COUNT(*) FILTER (WHERE delivered IS NOT NULL), 0) AS val
        FROM   orders
        WHERE  org_id    = $1
          AND  order_date >= (NOW() - make_interval(hours => $2))::date
        """,
        org_id,
        window_hours,
    )
    return row["val"] if row else None


async def avg_order_value(
    conn: asyncpg.Connection, org_id: str, window_hours: int
) -> float | None:
    """Average (price_per_unit * quantity) per order in the window."""
    row = await conn.fetchrow(
        """
        SELECT AVG(price_per_unit * quantity)::float AS val
        FROM   orders
        WHERE  org_id    = $1
          AND  order_date >= (NOW() - make_interval(hours => $2))::date
        """,
        org_id,
        window_hours,
    )
    return row["val"] if row else None


async def event_count(
    conn: asyncpg.Connection, org_id: str, window_hours: int
) -> float | None:
    """Total events received in the window (Segment A)."""
    row = await conn.fetchrow(
        """
        SELECT COUNT(*)::float AS val
        FROM   events
        WHERE  org_id      = $1
          AND  received_at >= NOW() - make_interval(hours => $2)
        """,
        org_id,
        window_hours,
    )
    return row["val"] if row else None


async def dau(
    conn: asyncpg.Connection, org_id: str, window_hours: int
) -> float | None:
    """
    Daily Active Users — distinct user_ids seen in the window.
    Counts only non-null user_id (identified users).
    """
    row = await conn.fetchrow(
        """
        SELECT COUNT(DISTINCT user_id)::float AS val
        FROM   events
        WHERE  org_id      = $1
          AND  received_at >= NOW() - make_interval(hours => $2)
          AND  user_id IS NOT NULL
        """,
        org_id,
        window_hours,
    )
    return row["val"] if row else None


# ── registry ──────────────────────────────────────────────────────────────────

METRIC_REGISTRY: dict[str, MetricFn] = {
    "revenue_total":   revenue_total,
    "order_count":     order_count,
    "delivery_rate":   delivery_rate,
    "avg_order_value": avg_order_value,
    "event_count":     event_count,
    "dau":             dau,
}


async def evaluate_metric(
    conn: asyncpg.Connection,
    org_id: str,
    metric: str,
    window_hours: int,
) -> float | None:
    """
    Evaluate a named metric for an org. Returns None for unknown metrics
    (treated as no_data by the alert evaluator).
    """
    fn = METRIC_REGISTRY.get(metric)
    if fn is None:
        logger.warning("Unknown metric %r for org %s", metric, org_id)
        return None
    return await fn(conn, org_id, window_hours)
