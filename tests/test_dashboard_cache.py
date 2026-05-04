"""
Tests for dashboard TTL cache.

Verifies:
  1. Second identical request is served from cache (no DB round-trip).
  2. Different days= values are cached independently.
  3. Different orgs are cached independently (no cross-tenant bleed).
  4. invalidate_org_cache() clears only the target org's entries.
  5. Cache is populated on first request and returned on second request.
  6. Sync completion invalidates the cache so fresh data appears immediately.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.routers.dashboard import _dashboard_cache, invalidate_org_cache
from tests.conftest import OrgFixture


@pytest.fixture(autouse=True)
def clear_cache():
    """Wipe the shared cache before every test to prevent inter-test pollution."""
    _dashboard_cache.clear()
    yield
    _dashboard_cache.clear()


class TestCachePopulation:
    @pytest.mark.asyncio
    async def test_cache_miss_on_first_request(
        self, client: AsyncClient, org_a: OrgFixture
    ):
        """First request always goes to DB; cache is empty beforehand."""
        assert len(_dashboard_cache) == 0
        resp = await client.get(
            "/api/dashboard/segment-a?days=7",
            headers=org_a.auth_headers,
        )
        assert resp.status_code == 200
        # Cache should now have exactly one entry.
        assert len(_dashboard_cache) == 1

    @pytest.mark.asyncio
    async def test_cache_hit_on_second_request(
        self, client: AsyncClient, org_a: OrgFixture
    ):
        """Second identical request is served from cache; cache size stays at 1."""
        await client.get("/api/dashboard/segment-a?days=7", headers=org_a.auth_headers)
        size_after_first = len(_dashboard_cache)

        resp = await client.get(
            "/api/dashboard/segment-a?days=7", headers=org_a.auth_headers
        )
        assert resp.status_code == 200
        # No new cache entries — served from cache.
        assert len(_dashboard_cache) == size_after_first

    @pytest.mark.asyncio
    async def test_different_days_cached_separately(
        self, client: AsyncClient, org_a: OrgFixture
    ):
        """days=7 and days=30 produce distinct cache keys."""
        await client.get("/api/dashboard/segment-a?days=7", headers=org_a.auth_headers)
        await client.get("/api/dashboard/segment-a?days=30", headers=org_a.auth_headers)
        # Two separate entries.
        assert len(_dashboard_cache) == 2

    @pytest.mark.asyncio
    async def test_segment_a_and_b_cached_separately(
        self, client: AsyncClient, org_a: OrgFixture
    ):
        """Segment A and Segment B have distinct cache keys."""
        await client.get("/api/dashboard/segment-a?days=7", headers=org_a.auth_headers)
        await client.get("/api/dashboard/segment-b?days=7", headers=org_a.auth_headers)
        assert len(_dashboard_cache) == 2


class TestCacheIsolation:
    @pytest.mark.asyncio
    async def test_different_orgs_cached_separately(
        self, client: AsyncClient, org_a: OrgFixture, org_b: OrgFixture
    ):
        """Org A and Org B never share a cache entry."""
        await client.get("/api/dashboard/segment-a", headers=org_a.auth_headers)
        await client.get("/api/dashboard/segment-a", headers=org_b.auth_headers)
        assert len(_dashboard_cache) == 2

    @pytest.mark.asyncio
    async def test_invalidate_only_clears_target_org(
        self, client: AsyncClient, org_a: OrgFixture, org_b: OrgFixture
    ):
        """invalidate_org_cache(org_a) must not evict org_b's entries."""
        await client.get("/api/dashboard/segment-a", headers=org_a.auth_headers)
        await client.get("/api/dashboard/segment-a", headers=org_b.auth_headers)
        assert len(_dashboard_cache) == 2

        invalidate_org_cache(org_a.org_id)

        # Org A's entry is gone; Org B's entry remains.
        remaining_keys = list(_dashboard_cache.keys())
        assert not any(k[0] == org_a.org_id for k in remaining_keys)
        assert any(k[0] == org_b.org_id for k in remaining_keys)

    @pytest.mark.asyncio
    async def test_invalidate_all_entries_for_org(
        self, client: AsyncClient, org_a: OrgFixture
    ):
        """invalidate_org_cache removes ALL (segment-a, segment-b, all days) for the org."""
        await client.get("/api/dashboard/segment-a?days=7", headers=org_a.auth_headers)
        await client.get("/api/dashboard/segment-a?days=30", headers=org_a.auth_headers)
        await client.get("/api/dashboard/segment-b?days=7", headers=org_a.auth_headers)
        assert len(_dashboard_cache) == 3

        invalidate_org_cache(org_a.org_id)

        assert len(_dashboard_cache) == 0


class TestCacheInvalidationOnSync:
    @pytest.mark.asyncio
    async def test_cache_cleared_after_successful_sync(
        self,
        client: AsyncClient,
        org_a: OrgFixture,
        db_pool,
    ):
        """
        After a successful sync_connector() call, the dashboard cache for that
        org is cleared so the next request reflects the newly imported data.
        """
        import base64

        from app.connectors.sync import sync_connector

        # Prime the cache with a dashboard response.
        resp = await client.get(
            "/api/dashboard/segment-a",
            headers=org_a.auth_headers,
        )
        assert resp.status_code == 200
        assert len(_dashboard_cache) == 1

        # Build a minimal csv_upload connector record (in-memory — no DB write needed).
        csv_content = b"order_id,order_date,quantity\nORD-SYNC-1,2024-01-01,1\n"
        b64 = base64.b64encode(csv_content).decode()

        # Insert a real connector row so sync_connector has a valid connector_id.
        # Pass config as a plain dict — the pool's JSONB codec handles encoding.
        async with db_pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(f"SET LOCAL app.org_id = '{org_a.org_id}'")
                connector_row = await conn.fetchrow(
                    """
                    INSERT INTO connectors (org_id, name, type, segment, config)
                    VALUES ($1, $2, $3, $4, $5)
                    RETURNING id, org_id, type, segment, config, status
                    """,
                    org_a.org_id,
                    "cache-test",
                    "csv_upload",
                    "B",
                    {
                        "pending_bytes_b64": b64,
                        "column_map": {},
                        "target_table": "orders",
                    },
                )

        await sync_connector(db_pool, connector_row)

        # Cache should now be empty for org_a — invalidated by the successful sync.
        remaining = [k for k in _dashboard_cache.keys() if k[0] == org_a.org_id]
        assert remaining == [], (
            f"Expected cache to be cleared after sync, but found: {remaining}"
        )
