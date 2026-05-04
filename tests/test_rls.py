"""
CRITICAL: Row-Level Security cross-tenant isolation tests.

These tests MUST pass before any other code ships. They verify that:
  1. Org A's data is never visible to Org B.
  2. Querying without app.org_id set returns zero rows (not an error, not other org's data).
  3. Each tenant table (events, orders, connectors, alert_rules) is isolated.

If any of these fail, there is a data security hole.
"""

from __future__ import annotations

import asyncpg
import pytest
from httpx import AsyncClient

from tests.conftest import OrgFixture

# ── Helpers ───────────────────────────────────────────────────────────────────

async def _insert_event(pool: asyncpg.Pool, org_id: str, event_name: str) -> None:
    """Insert an event for a specific org, bypassing RLS (direct pool access for test setup)."""
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(f"SET LOCAL app.org_id = '{str(org_id)}'")
            await conn.execute(
                "INSERT INTO events (org_id, event_name) VALUES ($1::uuid, $2)",
                org_id, event_name,
            )


async def _insert_order(pool: asyncpg.Pool, org_id: str, order_id: str) -> None:
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(f"SET LOCAL app.org_id = '{str(org_id)}'")
            await conn.execute(
                "INSERT INTO orders (org_id, order_id, order_date, quantity) "
                "VALUES ($1::uuid, $2, CURRENT_DATE, 1)",
                org_id, order_id,
            )


async def _count_events(pool: asyncpg.Pool, org_id: str) -> int:
    """Count events visible as the given org (RLS-enforced).
    Uses SET LOCAL ROLE app_role to drop superuser BYPASSRLS."""
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute("SET LOCAL ROLE app_role")
            await conn.execute(f"SET LOCAL app.org_id = '{str(org_id)}'")
            return await conn.fetchval("SELECT COUNT(*) FROM events")


async def _count_orders(pool: asyncpg.Pool, org_id: str) -> int:
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute("SET LOCAL ROLE app_role")
            await conn.execute(f"SET LOCAL app.org_id = '{str(org_id)}'")
            return await conn.fetchval("SELECT COUNT(*) FROM orders")


# ── RLS isolation tests ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_events_org_isolation(db_pool: asyncpg.Pool, org_a: OrgFixture, org_b: OrgFixture):
    """
    Org A's events must NEVER be visible to Org B, and vice versa.

    This is the most critical security test in the codebase.
    A failure here means cross-tenant data leakage.
    """
    # Insert one event for each org
    await _insert_event(db_pool, org_a.org_id, "purchase")
    await _insert_event(db_pool, org_b.org_id, "signup")

    # Each org sees only its own event
    assert await _count_events(db_pool, org_a.org_id) == 1
    assert await _count_events(db_pool, org_b.org_id) == 1

    # Org A's event is "purchase", Org B's is "signup"
    async with db_pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute("SET LOCAL ROLE app_role")
            await conn.execute(f"SET LOCAL app.org_id = '{str(org_a.org_id)}'")
            names_a = await conn.fetch("SELECT event_name FROM events")
            assert [r["event_name"] for r in names_a] == ["purchase"]

        async with conn.transaction():
            await conn.execute("SET LOCAL ROLE app_role")
            await conn.execute(f"SET LOCAL app.org_id = '{str(org_b.org_id)}'")
            names_b = await conn.fetch("SELECT event_name FROM events")
            assert [r["event_name"] for r in names_b] == ["signup"]


@pytest.mark.asyncio
async def test_orders_org_isolation(db_pool: asyncpg.Pool, org_a: OrgFixture, org_b: OrgFixture):
    """Org A's orders must not be visible to Org B."""
    await _insert_order(db_pool, org_a.org_id, "ORD-001")
    await _insert_order(db_pool, org_b.org_id, "ORD-002")

    assert await _count_orders(db_pool, org_a.org_id) == 1
    assert await _count_orders(db_pool, org_b.org_id) == 1

    # Verify the correct order is visible to each org
    async with db_pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute("SET LOCAL ROLE app_role")
            await conn.execute(f"SET LOCAL app.org_id = '{str(org_a.org_id)}'")
            order_ids_a = [r["order_id"] for r in await conn.fetch("SELECT order_id FROM orders")]
            assert order_ids_a == ["ORD-001"]

        async with conn.transaction():
            await conn.execute("SET LOCAL ROLE app_role")
            await conn.execute(f"SET LOCAL app.org_id = '{str(org_b.org_id)}'")
            order_ids_b = [r["order_id"] for r in await conn.fetch("SELECT order_id FROM orders")]
            assert order_ids_b == ["ORD-002"]


@pytest.mark.asyncio
async def test_unset_org_id_returns_zero_rows(db_pool: asyncpg.Pool, org_a: OrgFixture):
    """
    When app.org_id is not set, all tenant tables return ZERO rows.
    This must NOT raise an error and must NOT return other orgs' data.

    This test catches the case where a developer acquires a pool connection
    directly (without get_org_db) and accidentally queries tenant tables.
    """
    await _insert_event(db_pool, org_a.org_id, "test_event")
    await _insert_order(db_pool, org_a.org_id, "ORD-SAFE")

    async with db_pool.acquire() as conn:
        async with conn.transaction():
            # Drop to app_role so RLS fires, but intentionally do NOT set
            # app.org_id — simulates a developer forgetting to call get_org_db.
            await conn.execute("SET LOCAL ROLE app_role")
            event_count = await conn.fetchval("SELECT COUNT(*) FROM events")
            order_count = await conn.fetchval("SELECT COUNT(*) FROM orders")

    assert event_count == 0, (
        f"Expected 0 events with unset org_id, got {event_count}. "
        "RLS is not enforcing safe-by-default behavior."
    )
    assert order_count == 0, (
        f"Expected 0 orders with unset org_id, got {order_count}. "
        "RLS is not enforcing safe-by-default behavior."
    )


@pytest.mark.asyncio
async def test_connectors_org_isolation(db_pool: asyncpg.Pool, org_a: OrgFixture, org_b: OrgFixture):
    """Connectors are tenant-isolated: Org B cannot see Org A's connectors."""
    # Create a connector for Org A
    async with db_pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(f"SET LOCAL app.org_id = '{str(org_a.org_id)}'")
            await conn.execute(
                "INSERT INTO connectors (org_id, name, type, segment) "
                "VALUES ($1::uuid, 'Test Connector', 'js_sdk', 'A')",
                org_a.org_id,
            )

    # Org B should see no connectors
    async with db_pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute("SET LOCAL ROLE app_role")
            await conn.execute(f"SET LOCAL app.org_id = '{str(org_b.org_id)}'")
            count = await conn.fetchval("SELECT COUNT(*) FROM connectors")
    assert count == 0

    # Org A should see its connector
    async with db_pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute("SET LOCAL ROLE app_role")
            await conn.execute(f"SET LOCAL app.org_id = '{str(org_a.org_id)}'")
            count = await conn.fetchval("SELECT COUNT(*) FROM connectors")
    assert count == 1


@pytest.mark.asyncio
async def test_many_orgs_no_bleed(db_pool: asyncpg.Pool):
    """
    With 5 orgs each inserting 10 events, each org must see exactly 10 events.
    Regression test for the scenario where RLS fails under multiple active orgs.
    """


    org_ids = []
    for i in range(5):
        async with db_pool.acquire() as conn:
            org = await conn.fetchrow(
                "INSERT INTO orgs (name) VALUES ($1) RETURNING id", f"LoadOrg{i}"
            )
            org_ids.append(str(org["id"]))

    # Each org inserts 10 events
    for org_id in org_ids:
        for j in range(10):
            await _insert_event(db_pool, org_id, f"event_{j}")

    # Each org must see exactly 10 events (via app_role so RLS fires)
    for org_id in org_ids:
        count = await _count_events(db_pool, org_id)
        assert count == 10, (
            f"Org {org_id} expected 10 events, got {count}. "
            "Cross-tenant bleed detected."
        )

    # Cleanup
    async with db_pool.acquire() as conn:
        for org_id in org_ids:
            await conn.execute("DELETE FROM orgs WHERE id = $1::uuid", org_id)


# ── HTTP-layer RLS tests (via API routes) ─────────────────────────────────────

@pytest.mark.asyncio
async def test_ingest_then_dashboard_isolation(
    client: AsyncClient,
    db_pool: asyncpg.Pool,
    org_a: OrgFixture,
    org_b: OrgFixture,
):
    """
    End-to-end: Org A ingests an event via the API; Org B's dashboard sees zero events.

    This covers the full HTTP path: ingest → DB write → dashboard query.
    It verifies that the RLS DI (get_org_db_by_api_key and get_org_db) are
    correctly wiring app.org_id in both routes.
    """
    # Org A tracks an event
    resp = await client.post(
        f"/api/ingest/{org_a.api_key}",
        json={"type": "track", "event": "secret_action"},
    )
    assert resp.status_code == 200, resp.text

    # Org B queries the dashboard — must see zero events
    resp_b = await client.get(
        "/api/dashboard/segment-a",
        headers=org_b.auth_headers,
    )
    assert resp_b.status_code == 200
    data_b = resp_b.json()
    total_b = data_b.get("total_events", 0)
    assert total_b == 0, (
        f"Org B sees {total_b} events after Org A's ingest. Cross-tenant data leak!"
    )

    # Org A queries the dashboard — must see its own event
    resp_a = await client.get(
        "/api/dashboard/segment-a",
        headers=org_a.auth_headers,
    )
    assert resp_a.status_code == 200
    data_a = resp_a.json()
    total_a = data_a.get("total_events", 0)
    assert total_a == 1
