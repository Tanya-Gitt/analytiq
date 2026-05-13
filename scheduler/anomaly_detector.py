"""
Statistical anomaly detector.

Runs hourly (wired into scheduler/main.py).

Algorithm
─────────
For each org × metric:

  1. Pull 28 days of hourly bucket values from Postgres (GROUP BY hour bucket).
  2. Group by (day_of_week, hour_of_day) → compute mean + std_dev for that
     seasonal slot. This gives a "DOW-adjusted baseline" — Monday 14:00 has
     its own expected value that differs from Saturday 14:00. Simple but highly
     effective for weekly-seasonal SaaS metrics.
  3. Upsert the (mean, std_dev, sample_count) into anomaly_baselines.
  4. Get the value for the most recently completed hour.
  5. Look up baseline for that slot. If std_dev == 0 or sample_count < 4, skip.
  6. Compute z-score = (value − mean) / std_dev.
  7. If |z| ≥ 3.0 and this slot hasn't fired within the last 6 hours: insert
     an anomaly_event row (severity: warning=3–4σ, critical=>4σ).

Metrics tracked
───────────────
  event_count_hourly  — events received in an hour (Segment A)
  dau_hourly          — distinct user_ids per hour
  revenue_hourly      — sum(price_per_unit * quantity) per hour (Segment B)
  order_count_hourly  — orders per hour (Segment B)

No external dependencies — all math done in pure Python / Postgres SQL.
"""

from __future__ import annotations

import logging
import math
from datetime import datetime, timezone

import asyncpg

logger = logging.getLogger(__name__)

# ── constants ────────────────────────────────────────────────────────────────

_LOOKBACK_DAYS   = 28       # history window for baseline computation
_MIN_SAMPLES     = 4        # need ≥ N same-slot samples before firing
_SIGMA_WARNING   = 3.0      # z-score threshold for 'warning'
_SIGMA_CRITICAL  = 4.0      # z-score threshold for 'critical'
_COOLDOWN_HOURS  = 6        # suppress repeated anomaly for same org+metric


# ── SQL: pull hourly buckets ──────────────────────────────────────────────────

_SQL_EVENTS_HOURLY = """
SELECT
    EXTRACT(dow  FROM date_trunc('hour', received_at))::int AS dow,
    EXTRACT(hour FROM date_trunc('hour', received_at))::int AS hour,
    COUNT(*)::double precision                              AS val
FROM   events
WHERE  org_id      = $1
  AND  received_at >= NOW() - make_interval(days => $2)
  AND  received_at <  date_trunc('hour', NOW())   -- only completed hours
GROUP  BY 1, 2
ORDER  BY 1, 2
"""

_SQL_DAU_HOURLY = """
SELECT
    EXTRACT(dow  FROM date_trunc('hour', received_at))::int AS dow,
    EXTRACT(hour FROM date_trunc('hour', received_at))::int AS hour,
    COUNT(DISTINCT user_id)::double precision               AS val
FROM   events
WHERE  org_id      = $1
  AND  received_at >= NOW() - make_interval(days => $2)
  AND  received_at <  date_trunc('hour', NOW())
  AND  user_id IS NOT NULL
GROUP  BY 1, 2
ORDER  BY 1, 2
"""

_SQL_REVENUE_HOURLY = """
SELECT
    EXTRACT(dow  FROM o.order_date)::int             AS dow,
    0::int                                           AS hour,   -- daily granularity
    SUM(o.price_per_unit * o.quantity)::double precision AS val
FROM   orders o
WHERE  o.org_id    = $1
  AND  o.order_date >= (NOW() - make_interval(days => $2))::date
  AND  o.order_date <  NOW()::date
GROUP  BY 1, 2
ORDER  BY 1, 2
"""

_SQL_ORDER_COUNT_HOURLY = """
SELECT
    EXTRACT(dow FROM o.order_date)::int AS dow,
    0::int                              AS hour,
    COUNT(*)::double precision          AS val
FROM   orders o
WHERE  o.org_id    = $1
  AND  o.order_date >= (NOW() - make_interval(days => $2))::date
  AND  o.order_date <  NOW()::date
GROUP  BY 1, 2
ORDER  BY 1, 2
"""

_SQL_CURRENT_EVENTS = """
SELECT COUNT(*)::double precision AS val
FROM   events
WHERE  org_id      = $1
  AND  received_at >= date_trunc('hour', NOW() - interval '1 hour')
  AND  received_at <  date_trunc('hour', NOW())
"""

_SQL_CURRENT_DAU = """
SELECT COUNT(DISTINCT user_id)::double precision AS val
FROM   events
WHERE  org_id      = $1
  AND  received_at >= date_trunc('hour', NOW() - interval '1 hour')
  AND  received_at <  date_trunc('hour', NOW())
  AND  user_id IS NOT NULL
"""

_SQL_CURRENT_REVENUE = """
SELECT COALESCE(SUM(price_per_unit * quantity), 0)::double precision AS val
FROM   orders
WHERE  org_id    = $1
  AND  order_date = (NOW() - interval '1 day')::date
"""

_SQL_CURRENT_ORDER_COUNT = """
SELECT COUNT(*)::double precision AS val
FROM   orders
WHERE  org_id    = $1
  AND  order_date = (NOW() - interval '1 day')::date
"""

METRICS: dict[str, dict] = {
    "event_count_hourly":  {"history": _SQL_EVENTS_HOURLY,      "current": _SQL_CURRENT_EVENTS},
    "dau_hourly":          {"history": _SQL_DAU_HOURLY,          "current": _SQL_CURRENT_DAU},
    "revenue_daily":       {"history": _SQL_REVENUE_HOURLY,      "current": _SQL_CURRENT_REVENUE},
    "order_count_daily":   {"history": _SQL_ORDER_COUNT_HOURLY,  "current": _SQL_CURRENT_ORDER_COUNT},
}


# ── statistics helpers ────────────────────────────────────────────────────────

def _mean_std(values: list[float]) -> tuple[float, float]:
    """Return (mean, population_std_dev) for a list of floats."""
    n = len(values)
    if n == 0:
        return 0.0, 0.0
    m = sum(values) / n
    variance = sum((v - m) ** 2 for v in values) / n
    return m, math.sqrt(variance)


# ── main entry point ──────────────────────────────────────────────────────────

async def run_anomaly_detection(pool: asyncpg.Pool) -> None:
    """
    Called once per hour by the scheduler.
    Processes all orgs; each org is handled in its own connection/transaction.
    """
    # Fetch all org IDs (cross-tenant, no RLS needed)
    async with pool.acquire() as conn:
        org_rows = await conn.fetch("SELECT id::text FROM orgs ORDER BY id")

    org_ids = [r["id"] for r in org_rows]
    logger.info("Anomaly detector: processing %d orgs", len(org_ids))

    for org_id in org_ids:
        try:
            await _process_org(pool, org_id)
        except Exception:
            logger.exception("Anomaly detector failed for org %s", org_id)


async def _process_org(pool: asyncpg.Pool, org_id: str) -> None:
    async with pool.acquire() as conn:
        for metric_name, sqls in METRICS.items():
            try:
                await _process_metric(conn, org_id, metric_name, sqls)
            except Exception:
                logger.exception(
                    "Anomaly detector: error on org=%s metric=%s", org_id, metric_name
                )


async def _process_metric(
    conn: asyncpg.Connection,
    org_id: str,
    metric_name: str,
    sqls: dict,
) -> None:
    # 1. Fetch historical hourly buckets
    history_rows = await conn.fetch(sqls["history"], org_id, _LOOKBACK_DAYS)
    if not history_rows:
        return  # no data for this org

    # 2. Build {(dow, hour) → [values]} map
    slot_values: dict[tuple[int, int], list[float]] = {}
    for row in history_rows:
        key = (int(row["dow"]), int(row["hour"]))
        slot_values.setdefault(key, []).append(float(row["val"]))

    # 3. Compute and upsert baselines
    async with conn.transaction():
        await conn.execute("SET LOCAL ROLE app_role")
        await conn.execute(f"SET LOCAL app.org_id = '{org_id}'")

        for (dow, hour), vals in slot_values.items():
            mean, std_dev = _mean_std(vals)
            await conn.execute(
                """
                INSERT INTO anomaly_baselines
                    (org_id, metric, dow, hour, mean, std_dev, sample_count, computed_at)
                VALUES ($1::uuid, $2, $3, $4, $5, $6, $7, NOW())
                ON CONFLICT (org_id, metric, dow, hour) DO UPDATE
                  SET mean         = EXCLUDED.mean,
                      std_dev      = EXCLUDED.std_dev,
                      sample_count = EXCLUDED.sample_count,
                      computed_at  = NOW()
                """,
                org_id, metric_name, dow, hour, mean, std_dev, len(vals),
            )

    # 4. Get the current period's value
    current_row = await conn.fetchrow(sqls["current"], org_id)
    if current_row is None:
        return
    current_val = float(current_row["val"] or 0)

    # 5. Get the current slot's baseline
    now_utc = datetime.now(tz=timezone.utc)
    current_dow  = int(now_utc.strftime("%w"))   # 0=Sun…6=Sat
    current_hour = now_utc.hour

    async with conn.transaction():
        await conn.execute("SET LOCAL ROLE app_role")
        await conn.execute(f"SET LOCAL app.org_id = '{org_id}'")

        baseline_row = await conn.fetchrow(
            """
            SELECT mean, std_dev, sample_count
            FROM   anomaly_baselines
            WHERE  org_id = $1::uuid
              AND  metric = $2
              AND  dow    = $3
              AND  hour   = $4
            """,
            org_id, metric_name, current_dow, current_hour,
        )
        if baseline_row is None:
            return

        mean        = float(baseline_row["mean"])
        std_dev     = float(baseline_row["std_dev"])
        sample_count = int(baseline_row["sample_count"])

        # 6. Skip if not enough history or std_dev too small to be meaningful
        if sample_count < _MIN_SAMPLES or std_dev < 0.5:
            return

        z_score = (current_val - mean) / std_dev
        abs_z   = abs(z_score)

        if abs_z < _SIGMA_WARNING:
            return  # normal

        # 7. Suppress if we already fired for this org+metric recently
        recent = await conn.fetchval(
            """
            SELECT COUNT(*)
            FROM   anomaly_events
            WHERE  org_id      = $1::uuid
              AND  metric      = $2
              AND  detected_at >= NOW() - make_interval(hours => $3)
            """,
            org_id, metric_name, _COOLDOWN_HOURS,
        )
        if recent and int(recent) > 0:
            return  # cooldown active

        severity  = "critical" if abs_z >= _SIGMA_CRITICAL else "warning"
        direction = "high" if z_score > 0 else "low"

        await conn.execute(
            """
            INSERT INTO anomaly_events
                (org_id, metric, value, baseline, std_dev, z_score, direction, severity, detected_at)
            VALUES ($1::uuid, $2, $3, $4, $5, $6, $7, $8, NOW())
            """,
            org_id, metric_name, current_val, mean, std_dev,
            round(z_score, 3), direction, severity,
        )
        logger.warning(
            "ANOMALY org=%s metric=%s val=%.1f baseline=%.1f z=%.2f severity=%s",
            org_id, metric_name, current_val, mean, z_score, severity,
        )
