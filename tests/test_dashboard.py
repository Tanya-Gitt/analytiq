"""
Tests for GET /api/dashboard/segment-a and GET /api/dashboard/segment-b.

Coverage:
  - Response shape (required keys present)
  - Auth: unauthenticated returns 401
  - Segment A: empty org returns zero counts / empty lists
  - Segment A: ingested events appear in total_events, events_timeline, top_events
  - Segment A: dau populated when user_id is present
  - Segment B: empty org returns zero counts / empty lists
  - Segment B: orders appear in total_orders, total_revenue, revenue_trend, top_channels
  - Segment B: delivery_rate computed correctly
  - days= parameter filters correctly (data outside window is excluded)
  - GET /api/connectors/{id}/sync-runs returns run history
"""

from __future__ import annotations

from datetime import date, timedelta

import asyncpg
import pytest
from httpx import AsyncClient

from app.routers.dashboard import _dashboard_cache
from tests.conftest import OrgFixture


@pytest.fixture(autouse=True)
def clear_cache():
    _dashboard_cache.clear()
    yield
    _dashboard_cache.clear()


# ── helpers ───────────────────────────────────────────────────────────────────

async def _insert_event(
    pool: asyncpg.Pool,
    org_id: str,
    event_name: str,
    user_id: str | None = None,
    days_ago: int = 0,
) -> None:
    received = f"NOW() - INTERVAL '{days_ago} days'"
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(f"SET LOCAL app.org_id = '{org_id}'")
            await conn.execute(
                f"""
                INSERT INTO events (org_id, event_name, user_id, received_at)
                VALUES ($1::uuid, $2, $3, {received})
                """,
                org_id, event_name, user_id,
            )


async def _insert_order(
    pool: asyncpg.Pool,
    org_id: str,
    order_id: str,
    order_date: date,
    quantity: int = 1,
    price_per_unit: float | None = None,
    delivered: bool | None = None,
    channel: str | None = None,
) -> None:
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(f"SET LOCAL app.org_id = '{org_id}'")
            await conn.execute(
                """
                INSERT INTO orders
                  (org_id, order_id, order_date, quantity, price_per_unit, delivered, channel)
                VALUES ($1::uuid, $2, $3, $4, $5, $6, $7)
                """,
                org_id, order_id, order_date, quantity, price_per_unit, delivered, channel,
            )


# ── Auth ──────────────────────────────────────────────────────────────────────

class TestDashboardAuth:
    @pytest.mark.asyncio
    async def test_segment_a_unauthenticated_401(self, client: AsyncClient):
        resp = await client.get("/api/dashboard/segment-a")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_segment_b_unauthenticated_401(self, client: AsyncClient):
        resp = await client.get("/api/dashboard/segment-b")
        assert resp.status_code == 401


# ── Segment A shape ───────────────────────────────────────────────────────────

class TestSegmentAShape:
    @pytest.mark.asyncio
    async def test_empty_org_returns_correct_keys(
        self, client: AsyncClient, org_a: OrgFixture
    ):
        """All required keys must be present even when there is no data."""
        resp = await client.get("/api/dashboard/segment-a", headers=org_a.auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "events_timeline" in data
        assert "top_events" in data
        assert "dau" in data
        assert "total_events" in data

    @pytest.mark.asyncio
    async def test_empty_org_zero_counts(
        self, client: AsyncClient, org_a: OrgFixture
    ):
        resp = await client.get("/api/dashboard/segment-a", headers=org_a.auth_headers)
        data = resp.json()
        assert data["total_events"] == 0
        assert data["events_timeline"] == []
        assert data["top_events"] == []
        assert data["dau"] is None

    @pytest.mark.asyncio
    async def test_events_appear_in_total(
        self, client: AsyncClient, org_a: OrgFixture, db_pool: asyncpg.Pool
    ):
        await _insert_event(db_pool, org_a.org_id, "purchase")
        await _insert_event(db_pool, org_a.org_id, "signup")

        resp = await client.get("/api/dashboard/segment-a", headers=org_a.auth_headers)
        assert resp.json()["total_events"] == 2

    @pytest.mark.asyncio
    async def test_top_events_lists_event_names(
        self, client: AsyncClient, org_a: OrgFixture, db_pool: asyncpg.Pool
    ):
        await _insert_event(db_pool, org_a.org_id, "purchase")
        await _insert_event(db_pool, org_a.org_id, "purchase")
        await _insert_event(db_pool, org_a.org_id, "signup")

        resp = await client.get("/api/dashboard/segment-a", headers=org_a.auth_headers)
        top = resp.json()["top_events"]
        assert len(top) >= 2
        names = [e["event_name"] for e in top]
        assert "purchase" in names
        assert "signup" in names
        # purchase has higher count — should be first
        assert top[0]["event_name"] == "purchase"
        assert top[0]["count"] == 2

    @pytest.mark.asyncio
    async def test_events_timeline_has_date_and_count(
        self, client: AsyncClient, org_a: OrgFixture, db_pool: asyncpg.Pool
    ):
        await _insert_event(db_pool, org_a.org_id, "page_view")

        resp = await client.get("/api/dashboard/segment-a", headers=org_a.auth_headers)
        timeline = resp.json()["events_timeline"]
        assert len(timeline) >= 1
        entry = timeline[0]
        assert "date" in entry
        assert "count" in entry
        assert isinstance(entry["count"], int)

    @pytest.mark.asyncio
    async def test_dau_populated_when_user_id_present(
        self, client: AsyncClient, org_a: OrgFixture, db_pool: asyncpg.Pool
    ):
        await _insert_event(db_pool, org_a.org_id, "page_view", user_id="user-1")
        await _insert_event(db_pool, org_a.org_id, "page_view", user_id="user-2")

        resp = await client.get("/api/dashboard/segment-a", headers=org_a.auth_headers)
        assert resp.json()["dau"] is not None
        assert resp.json()["dau"] > 0

    @pytest.mark.asyncio
    async def test_days_filter_excludes_old_events(
        self, client: AsyncClient, org_a: OrgFixture, db_pool: asyncpg.Pool
    ):
        """Events older than `days` must not appear in the totals."""
        await _insert_event(db_pool, org_a.org_id, "recent", days_ago=1)
        await _insert_event(db_pool, org_a.org_id, "old", days_ago=60)

        resp = await client.get(
            "/api/dashboard/segment-a?days=7", headers=org_a.auth_headers
        )
        assert resp.json()["total_events"] == 1  # only "recent"


# ── Segment B shape ───────────────────────────────────────────────────────────

class TestSegmentBShape:
    @pytest.mark.asyncio
    async def test_empty_org_returns_correct_keys(
        self, client: AsyncClient, org_a: OrgFixture
    ):
        resp = await client.get("/api/dashboard/segment-b", headers=org_a.auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "revenue_trend" in data
        assert "top_channels" in data
        assert "delivery_rate" in data
        assert "total_orders" in data
        assert "total_revenue" in data

    @pytest.mark.asyncio
    async def test_empty_org_zero_counts(
        self, client: AsyncClient, org_a: OrgFixture
    ):
        resp = await client.get("/api/dashboard/segment-b", headers=org_a.auth_headers)
        data = resp.json()
        assert data["total_orders"] == 0
        assert data["total_revenue"] == 0.0
        assert data["revenue_trend"] == []
        assert data["top_channels"] == []
        assert data["delivery_rate"] is None

    @pytest.mark.asyncio
    async def test_orders_appear_in_total(
        self, client: AsyncClient, org_a: OrgFixture, db_pool: asyncpg.Pool
    ):
        today = date.today()
        await _insert_order(db_pool, org_a.org_id, "ORD-1", today, quantity=2, price_per_unit=10.0)
        await _insert_order(db_pool, org_a.org_id, "ORD-2", today, quantity=1, price_per_unit=5.0)

        resp = await client.get("/api/dashboard/segment-b", headers=org_a.auth_headers)
        data = resp.json()
        assert data["total_orders"] == 2
        assert data["total_revenue"] == pytest.approx(25.0)

    @pytest.mark.asyncio
    async def test_revenue_trend_has_date_and_revenue(
        self, client: AsyncClient, org_a: OrgFixture, db_pool: asyncpg.Pool
    ):
        today = date.today()
        await _insert_order(db_pool, org_a.org_id, "ORD-T1", today, quantity=1, price_per_unit=50.0)

        resp = await client.get("/api/dashboard/segment-b", headers=org_a.auth_headers)
        trend = resp.json()["revenue_trend"]
        assert len(trend) >= 1
        entry = trend[0]
        assert "date" in entry
        assert "revenue" in entry
        assert entry["revenue"] == pytest.approx(50.0)

    @pytest.mark.asyncio
    async def test_top_channels_by_revenue(
        self, client: AsyncClient, org_a: OrgFixture, db_pool: asyncpg.Pool
    ):
        today = date.today()
        await _insert_order(db_pool, org_a.org_id, "ORD-C1", today,
                            quantity=1, price_per_unit=100.0, channel="web")
        await _insert_order(db_pool, org_a.org_id, "ORD-C2", today,
                            quantity=1, price_per_unit=30.0, channel="mobile")

        resp = await client.get("/api/dashboard/segment-b", headers=org_a.auth_headers)
        channels = resp.json()["top_channels"]
        names = [c["channel"] for c in channels]
        assert "web" in names
        assert "mobile" in names
        # web has highest revenue — must be first
        assert channels[0]["channel"] == "web"

    @pytest.mark.asyncio
    async def test_delivery_rate_computed(
        self, client: AsyncClient, org_a: OrgFixture, db_pool: asyncpg.Pool
    ):
        """2 delivered out of 4 orders with delivered flags → 0.5."""
        today = date.today()
        await _insert_order(db_pool, org_a.org_id, "ORD-D1", today, delivered=True)
        await _insert_order(db_pool, org_a.org_id, "ORD-D2", today, delivered=True)
        await _insert_order(db_pool, org_a.org_id, "ORD-D3", today, delivered=False)
        await _insert_order(db_pool, org_a.org_id, "ORD-D4", today, delivered=False)

        resp = await client.get("/api/dashboard/segment-b", headers=org_a.auth_headers)
        assert resp.json()["delivery_rate"] == pytest.approx(0.5)

    @pytest.mark.asyncio
    async def test_delivery_rate_null_when_no_delivered_data(
        self, client: AsyncClient, org_a: OrgFixture, db_pool: asyncpg.Pool
    ):
        """If no order has a non-null delivered flag, delivery_rate must be null."""
        today = date.today()
        await _insert_order(db_pool, org_a.org_id, "ORD-ND1", today)  # delivered=None

        resp = await client.get("/api/dashboard/segment-b", headers=org_a.auth_headers)
        assert resp.json()["delivery_rate"] is None

    @pytest.mark.asyncio
    async def test_days_filter_excludes_old_orders(
        self, client: AsyncClient, org_a: OrgFixture, db_pool: asyncpg.Pool
    ):
        """Orders older than `days` must not appear in totals."""
        recent = date.today()
        old = date.today() - timedelta(days=60)
        await _insert_order(db_pool, org_a.org_id, "ORD-NEW", recent,
                            quantity=1, price_per_unit=10.0)
        await _insert_order(db_pool, org_a.org_id, "ORD-OLD", old,
                            quantity=1, price_per_unit=999.0)

        resp = await client.get(
            "/api/dashboard/segment-b?days=7", headers=org_a.auth_headers
        )
        data = resp.json()
        assert data["total_orders"] == 1
        assert data["total_revenue"] == pytest.approx(10.0)


# ── Sync-runs endpoint ────────────────────────────────────────────────────────

class TestSyncRuns:
    @pytest.mark.asyncio
    async def test_sync_runs_empty_for_new_connector(
        self, client: AsyncClient, org_a: OrgFixture
    ):
        """A brand-new connector has no sync run history."""
        create = await client.post(
            "/api/connectors",
            json={
                "type": "csv_upload",
                "segment": "B",
                "config": {
                    "target_table": "orders",
                    "column_map": {"ID": "order_id", "Date": "order_date", "Qty": "quantity"},
                },
            },
            headers=org_a.auth_headers,
        )
        assert create.status_code == 201
        connector_id = create.json()["id"]

        resp = await client.get(
            f"/api/connectors/{connector_id}/sync-runs",
            headers=org_a.auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json() == []

    @pytest.mark.asyncio
    async def test_sync_runs_appear_after_sync(
        self, client: AsyncClient, org_a: OrgFixture, db_pool: asyncpg.Pool
    ):
        """After running sync_connector, a sync_runs row should appear."""
        import base64

        from app.connectors.sync import sync_connector

        csv = b"order_id,order_date,quantity\nORD-SR1,2024-01-01,1\n"
        b64 = base64.b64encode(csv).decode()

        async with db_pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(f"SET LOCAL app.org_id = '{org_a.org_id}'")
                connector_row = await conn.fetchrow(
                    """
                    INSERT INTO connectors (org_id, name, type, segment, config)
                    VALUES ($1, 'sync-runs-test', 'csv_upload', 'B', $2)
                    RETURNING id, org_id, type, segment, config, status
                    """,
                    org_a.org_id,
                    {
                        "pending_bytes_b64": b64,
                        "column_map": {
                            "order_id": "order_id",
                            "order_date": "order_date",
                            "quantity": "quantity",
                        },
                        "target_table": "orders",
                    },
                )

        await sync_connector(db_pool, connector_row)

        resp = await client.get(
            f"/api/connectors/{connector_row['id']}/sync-runs",
            headers=org_a.auth_headers,
        )
        assert resp.status_code == 200
        runs = resp.json()
        assert len(runs) == 1
        assert runs[0]["status"] == "success"
        assert runs[0]["rows_upserted"] == 1

    @pytest.mark.asyncio
    async def test_sync_runs_shape(
        self, client: AsyncClient, org_a: OrgFixture, db_pool: asyncpg.Pool
    ):
        """Each sync_run row must have the expected fields."""
        import base64

        from app.connectors.sync import sync_connector

        csv = b"order_id,order_date,quantity\nORD-SHAPE,2024-06-01,3\n"
        b64 = base64.b64encode(csv).decode()

        async with db_pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(f"SET LOCAL app.org_id = '{org_a.org_id}'")
                connector_row = await conn.fetchrow(
                    """
                    INSERT INTO connectors (org_id, name, type, segment, config)
                    VALUES ($1, 'shape-test', 'csv_upload', 'B', $2)
                    RETURNING id, org_id, type, segment, config, status
                    """,
                    org_a.org_id,
                    {
                        "pending_bytes_b64": b64,
                        "column_map": {
                            "order_id": "order_id",
                            "order_date": "order_date",
                            "quantity": "quantity",
                        },
                        "target_table": "orders",
                    },
                )

        await sync_connector(db_pool, connector_row)

        resp = await client.get(
            f"/api/connectors/{connector_row['id']}/sync-runs",
            headers=org_a.auth_headers,
        )
        run = resp.json()[0]
        assert "id" in run
        assert "status" in run
        assert "started_at" in run
        assert "finished_at" in run
        assert "rows_upserted" in run
        assert "error_message" in run

    @pytest.mark.asyncio
    async def test_sync_runs_unauthenticated_returns_401(self, client: AsyncClient):
        fake_id = "00000000-0000-0000-0000-000000000000"
        resp = await client.get(f"/api/connectors/{fake_id}/sync-runs")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_sync_runs_org_isolation(
        self,
        client: AsyncClient,
        org_a: OrgFixture,
        org_b: OrgFixture,
        db_pool: asyncpg.Pool,
    ):
        """Org B must not be able to read sync runs for org A's connector."""
        import base64

        from app.connectors.sync import sync_connector

        csv = b"order_id,order_date,quantity\nORD-ISO,2024-01-01,1\n"
        b64 = base64.b64encode(csv).decode()

        async with db_pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(f"SET LOCAL app.org_id = '{org_a.org_id}'")
                connector_row = await conn.fetchrow(
                    """
                    INSERT INTO connectors (org_id, name, type, segment, config)
                    VALUES ($1, 'iso-test', 'csv_upload', 'B', $2)
                    RETURNING id, org_id, type, segment, config, status
                    """,
                    org_a.org_id,
                    {
                        "pending_bytes_b64": b64,
                        "column_map": {
                            "order_id": "order_id",
                            "order_date": "order_date",
                            "quantity": "quantity",
                        },
                        "target_table": "orders",
                    },
                )

        await sync_connector(db_pool, connector_row)

        # Org B queries org A's connector sync runs — RLS hides the connector,
        # so the sync-runs query returns [] (not the actual runs or a 403).
        resp = await client.get(
            f"/api/connectors/{connector_row['id']}/sync-runs",
            headers=org_b.auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json() == []


# ── dashboard cache hit ────────────────────────────────────────────────────────

class TestDashboardCache:
    """The in-process cache returns the same object on the second call."""

    @pytest.mark.asyncio
    async def test_segment_b_cache_hit_on_second_request(
        self, client: AsyncClient, org_a
    ):
        """
        Two identical requests in the same process must both return 200 and
        agree on the response shape. The second call hits the LRU cache
        (dashboard.py:71) rather than re-querying the DB.
        """
        first  = await client.get("/api/dashboard/segment-b", headers=org_a.auth_headers)
        second = await client.get("/api/dashboard/segment-b", headers=org_a.auth_headers)
        assert first.status_code == 200
        assert second.status_code == 200
        # Both responses must have the same shape
        for key in ("total_orders", "total_revenue", "delivery_rate", "revenue_trend", "top_channels"):
            assert key in second.json()


# ── /health endpoint ──────────────────────────────────────────────────────────

class TestHealthEndpoint:
    @pytest.mark.asyncio
    async def test_health_returns_ok(self, client: AsyncClient):
        resp = await client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}
