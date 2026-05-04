"""
Unit tests for scheduler/metrics.py — one test per metric function plus the
evaluate_metric dispatcher.

Each test:
  1. Inserts known rows directly (bypassing the HTTP API) via asyncpg.
  2. Opens a connection with SET LOCAL app.org_id so RLS allows reads.
  3. Calls the metric function and asserts the expected value.

Window is set to 24 hours for all tests unless stated otherwise.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import asyncpg
import pytest

from scheduler.metrics import (
    avg_order_value,
    dau,
    delivery_rate,
    evaluate_metric,
    event_count,
    order_count,
    revenue_total,
)

# ── helpers ────────────────────────────────────────────────────────────────────

async def _insert_order(
    pool: asyncpg.Pool,
    org_id: str,
    *,
    order_id: str,
    days_ago: float = 0,
    quantity: int = 1,
    price_per_unit: float = 10.0,
    delivered: bool | None = None,
) -> None:
    order_date = (datetime.now(timezone.utc) - timedelta(days=days_ago)).date()
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(f"SET LOCAL app.org_id = '{org_id}'")
            await conn.execute(
                """
                INSERT INTO orders
                    (org_id, order_id, order_date, quantity, price_per_unit, delivered)
                VALUES ($1, $2, $3, $4, $5, $6)
                ON CONFLICT (org_id, order_id) DO NOTHING
                """,
                org_id, order_id, order_date, quantity, price_per_unit, delivered,
            )


async def _insert_event(
    pool: asyncpg.Pool,
    org_id: str,
    *,
    event_name: str = "page_view",
    user_id: str | None = None,
    hours_ago: float = 0,
) -> None:
    received_at = datetime.now(timezone.utc) - timedelta(hours=hours_ago)
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(f"SET LOCAL app.org_id = '{org_id}'")
            await conn.execute(
                """
                INSERT INTO events (org_id, event_name, user_id, received_at)
                VALUES ($1, $2, $3, $4)
                """,
                org_id, event_name, user_id, received_at,
            )


async def _conn_for_org(pool: asyncpg.Pool, org_id: str) -> asyncpg.Connection:
    """Acquire a connection already scoped to org_id via RLS."""
    conn = await pool.acquire()
    await conn.execute(f"SET LOCAL app.org_id = '{org_id}'")
    return conn


# ── revenue_total ──────────────────────────────────────────────────────────────

class TestRevenueTotal:
    @pytest.mark.asyncio
    async def test_returns_sum_of_price_times_quantity(self, db_pool, org_a):
        await _insert_order(db_pool, org_a.org_id,
                            order_id="REV-1", quantity=2, price_per_unit=15.0)
        await _insert_order(db_pool, org_a.org_id,
                            order_id="REV-2", quantity=3, price_per_unit=10.0)

        async with db_pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(f"SET LOCAL app.org_id = '{org_a.org_id}'")
                val = await revenue_total(conn, org_a.org_id, 24)

        # 2*15 + 3*10 = 30 + 30 = 60
        assert val == pytest.approx(60.0)

    @pytest.mark.asyncio
    async def test_returns_none_when_no_orders(self, db_pool, org_a):
        async with db_pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(f"SET LOCAL app.org_id = '{org_a.org_id}'")
                val = await revenue_total(conn, org_a.org_id, 24)

        assert val is None

    @pytest.mark.asyncio
    async def test_excludes_old_orders(self, db_pool, org_a):
        """Orders older than the window must not count."""
        await _insert_order(db_pool, org_a.org_id,
                            order_id="REV-OLD", days_ago=3, quantity=100, price_per_unit=1.0)
        await _insert_order(db_pool, org_a.org_id,
                            order_id="REV-NEW", days_ago=0, quantity=1, price_per_unit=5.0)

        async with db_pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(f"SET LOCAL app.org_id = '{org_a.org_id}'")
                # 24-hour window excludes the 3-day-old order
                val = await revenue_total(conn, org_a.org_id, 24)

        assert val == pytest.approx(5.0)


# ── order_count ────────────────────────────────────────────────────────────────

class TestOrderCount:
    @pytest.mark.asyncio
    async def test_counts_orders_in_window(self, db_pool, org_a):
        for i in range(4):
            await _insert_order(db_pool, org_a.org_id, order_id=f"CNT-{i}")

        async with db_pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(f"SET LOCAL app.org_id = '{org_a.org_id}'")
                val = await order_count(conn, org_a.org_id, 24)

        assert val == pytest.approx(4.0)

    @pytest.mark.asyncio
    async def test_zero_count_returns_zero_not_none(self, db_pool, org_a):
        """COUNT(*) never returns NULL — should return 0.0 on empty table."""
        async with db_pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(f"SET LOCAL app.org_id = '{org_a.org_id}'")
                val = await order_count(conn, org_a.org_id, 24)

        assert val == pytest.approx(0.0)


# ── delivery_rate ──────────────────────────────────────────────────────────────

class TestDeliveryRate:
    @pytest.mark.asyncio
    async def test_half_delivered_returns_0_5(self, db_pool, org_a):
        await _insert_order(db_pool, org_a.org_id,
                            order_id="DEL-Y", delivered=True)
        await _insert_order(db_pool, org_a.org_id,
                            order_id="DEL-N", delivered=False)

        async with db_pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(f"SET LOCAL app.org_id = '{org_a.org_id}'")
                val = await delivery_rate(conn, org_a.org_id, 24)

        assert val == pytest.approx(0.5)

    @pytest.mark.asyncio
    async def test_all_delivered_returns_1(self, db_pool, org_a):
        await _insert_order(db_pool, org_a.org_id,
                            order_id="DEL-ALL-1", delivered=True)
        await _insert_order(db_pool, org_a.org_id,
                            order_id="DEL-ALL-2", delivered=True)

        async with db_pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(f"SET LOCAL app.org_id = '{org_a.org_id}'")
                val = await delivery_rate(conn, org_a.org_id, 24)

        assert val == pytest.approx(1.0)

    @pytest.mark.asyncio
    async def test_null_delivered_excluded_from_denominator(self, db_pool, org_a):
        """Rows with delivered=NULL must not count in either numerator or denominator."""
        await _insert_order(db_pool, org_a.org_id,
                            order_id="DEL-NULL", delivered=None)

        async with db_pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(f"SET LOCAL app.org_id = '{org_a.org_id}'")
                val = await delivery_rate(conn, org_a.org_id, 24)

        # NULLIF(COUNT WHERE NOT NULL, 0) → NULL → rate = None
        assert val is None

    @pytest.mark.asyncio
    async def test_no_orders_returns_none(self, db_pool, org_a):
        async with db_pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(f"SET LOCAL app.org_id = '{org_a.org_id}'")
                val = await delivery_rate(conn, org_a.org_id, 24)

        assert val is None


# ── avg_order_value ────────────────────────────────────────────────────────────

class TestAvgOrderValue:
    @pytest.mark.asyncio
    async def test_average_of_two_orders(self, db_pool, org_a):
        # order values: 1*10=10, 2*20=40  →  avg = 25
        await _insert_order(db_pool, org_a.org_id,
                            order_id="AOV-1", quantity=1, price_per_unit=10.0)
        await _insert_order(db_pool, org_a.org_id,
                            order_id="AOV-2", quantity=2, price_per_unit=20.0)

        async with db_pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(f"SET LOCAL app.org_id = '{org_a.org_id}'")
                val = await avg_order_value(conn, org_a.org_id, 24)

        assert val == pytest.approx(25.0)

    @pytest.mark.asyncio
    async def test_no_orders_returns_none(self, db_pool, org_a):
        async with db_pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(f"SET LOCAL app.org_id = '{org_a.org_id}'")
                val = await avg_order_value(conn, org_a.org_id, 24)

        assert val is None


# ── event_count ────────────────────────────────────────────────────────────────

class TestEventCount:
    @pytest.mark.asyncio
    async def test_counts_events_in_window(self, db_pool, org_a):
        for i in range(5):
            await _insert_event(db_pool, org_a.org_id,
                                event_name=f"ev_{i}", hours_ago=0)

        async with db_pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(f"SET LOCAL app.org_id = '{org_a.org_id}'")
                val = await event_count(conn, org_a.org_id, 24)

        assert val == pytest.approx(5.0)

    @pytest.mark.asyncio
    async def test_excludes_old_events(self, db_pool, org_a):
        """Events older than window_hours must not be counted."""
        await _insert_event(db_pool, org_a.org_id,
                            event_name="old_ev", hours_ago=48)
        await _insert_event(db_pool, org_a.org_id,
                            event_name="new_ev", hours_ago=1)

        async with db_pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(f"SET LOCAL app.org_id = '{org_a.org_id}'")
                val = await event_count(conn, org_a.org_id, 24)

        assert val == pytest.approx(1.0)

    @pytest.mark.asyncio
    async def test_zero_events_returns_zero(self, db_pool, org_a):
        async with db_pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(f"SET LOCAL app.org_id = '{org_a.org_id}'")
                val = await event_count(conn, org_a.org_id, 24)

        assert val == pytest.approx(0.0)


# ── dau ────────────────────────────────────────────────────────────────────────

class TestDau:
    @pytest.mark.asyncio
    async def test_distinct_users_counted(self, db_pool, org_a):
        # user-1 fires 3 events, user-2 fires 1 — DAU should be 2
        for _ in range(3):
            await _insert_event(db_pool, org_a.org_id, user_id="u1")
        await _insert_event(db_pool, org_a.org_id, user_id="u2")

        async with db_pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(f"SET LOCAL app.org_id = '{org_a.org_id}'")
                val = await dau(conn, org_a.org_id, 24)

        assert val == pytest.approx(2.0)

    @pytest.mark.asyncio
    async def test_anonymous_events_not_counted(self, db_pool, org_a):
        """Events without a user_id (anonymous) must not contribute to DAU."""
        await _insert_event(db_pool, org_a.org_id, user_id=None)
        await _insert_event(db_pool, org_a.org_id, user_id="real-user")

        async with db_pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(f"SET LOCAL app.org_id = '{org_a.org_id}'")
                val = await dau(conn, org_a.org_id, 24)

        assert val == pytest.approx(1.0)

    @pytest.mark.asyncio
    async def test_no_events_returns_zero(self, db_pool, org_a):
        async with db_pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(f"SET LOCAL app.org_id = '{org_a.org_id}'")
                val = await dau(conn, org_a.org_id, 24)

        assert val == pytest.approx(0.0)


# ── evaluate_metric dispatcher ─────────────────────────────────────────────────

class TestEvaluateMetric:
    @pytest.mark.asyncio
    async def test_known_metric_dispatches_correctly(self, db_pool, org_a):
        """evaluate_metric('order_count', ...) must return the same as order_count()."""
        for i in range(2):
            await _insert_order(db_pool, org_a.org_id, order_id=f"DISP-{i}")

        async with db_pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(f"SET LOCAL app.org_id = '{org_a.org_id}'")
                val = await evaluate_metric(conn, org_a.org_id, "order_count", 24)

        assert val == pytest.approx(2.0)

    @pytest.mark.asyncio
    async def test_unknown_metric_returns_none(self, db_pool, org_a):
        """An unregistered metric name must return None (treated as no_data)."""
        async with db_pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(f"SET LOCAL app.org_id = '{org_a.org_id}'")
                val = await evaluate_metric(conn, org_a.org_id, "totally_made_up", 24)

        assert val is None

    @pytest.mark.asyncio
    async def test_all_registered_metrics_callable(self, db_pool, org_a):
        """Every entry in METRIC_REGISTRY must be callable without crashing."""
        from scheduler.metrics import METRIC_REGISTRY
        async with db_pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(f"SET LOCAL app.org_id = '{org_a.org_id}'")
                for name in METRIC_REGISTRY:
                    val = await evaluate_metric(conn, org_a.org_id, name, 24)
                    # Must return a float or None — not raise
                    assert val is None or isinstance(val, float)
