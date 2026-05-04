"""
Tests for POST /api/ingest/{org_api_key} — event ingest, auth, rate limiting,
and CORS enforcement.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

# ── happy path ─────────────────────────────────────────────────────────────────

class TestIngestHappyPath:
    @pytest.mark.asyncio
    async def test_valid_event_accepted(self, client: AsyncClient, org_a):
        resp = await client.post(
            f"/api/ingest/{org_a.api_key}",
            json={
                "type": "track",
                "event": "purchase",
                "userId": "user-123",
                "properties": {"sku": "PROD-1", "price": 29.99},
            },
        )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_event_persisted_to_db(self, client: AsyncClient, org_a, db_pool):
        resp = await client.post(
            f"/api/ingest/{org_a.api_key}",
            json={"type": "track", "event": "signup", "userId": "u-persist"},
        )
        assert resp.status_code == 200

        # Verify row exists in DB with correct org isolation
        async with db_pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(f"SET LOCAL app.org_id = '{str(org_a.org_id)}'")
                count = await conn.fetchval(
                    "SELECT COUNT(*) FROM events WHERE event_name = 'signup' AND user_id = 'u-persist'"
                )
        assert count == 1

    @pytest.mark.asyncio
    async def test_anonymous_event_no_user_id(self, client: AsyncClient, org_a):
        """Events without userId should still be accepted (anonymous_id path)."""
        resp = await client.post(
            f"/api/ingest/{org_a.api_key}",
            json={
                "type": "page",
                "anonymousId": "anon-abc",
                "properties": {"url": "https://example.com/home"},
            },
        )
        assert resp.status_code == 200


# ── auth failures ──────────────────────────────────────────────────────────────

class TestIngestAuth:
    @pytest.mark.asyncio
    async def test_unknown_api_key_returns_404(self, client: AsyncClient):
        resp = await client.post(
            "/api/ingest/totally-unknown-key-xyz",
            json={"type": "track", "event": "test"},
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_missing_event_type_returns_422(self, client: AsyncClient, org_a):
        """'type' is a required Pydantic field — FastAPI returns 422 when absent."""
        resp = await client.post(
            f"/api/ingest/{org_a.api_key}",
            json={"event": "no_type_here"},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_invalid_event_type_returns_400(self, client: AsyncClient, org_a):
        """type values other than track/identify/page must return 400."""
        resp = await client.post(
            f"/api/ingest/{org_a.api_key}",
            json={"type": "alias", "event": "something"},
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_track_without_event_field_returns_400(
        self, client: AsyncClient, org_a
    ):
        """type='track' requires the 'event' field — missing it must return 400."""
        resp = await client.post(
            f"/api/ingest/{org_a.api_key}",
            json={"type": "track", "userId": "u-1"},  # no 'event'
        )
        assert resp.status_code == 400


# ── rate limiting ──────────────────────────────────────────────────────────────

class TestIngestRateLimit:
    @pytest.mark.asyncio
    async def test_100_requests_succeed(self, client: AsyncClient, org_a):
        """First 100 requests within a second should all pass."""
        resps = []
        for i in range(100):
            r = await client.post(
                f"/api/ingest/{org_a.api_key}",
                json={"type": "track", "event": f"ev_{i}"},
            )
            resps.append(r.status_code)
        assert all(s == 200 for s in resps), f"Some requests failed: {set(resps)}"

    @pytest.mark.asyncio
    async def test_101st_request_returns_429(
        self, client: AsyncClient, org_b, db_pool
    ):
        """
        After exhausting the burst bucket (100 tokens), the next request must
        get 429.

        We seed the rate_limits table with 0 tokens (last_refill_at = NOW)
        to avoid the flakiness of burning 100 real HTTP requests — those take
        >1s total, which would refill the Postgres-backed bucket.
        """
        # Use tokens=-100 so even a 1-second gap before the check cannot
        # refill the bucket to ≥1 (would need 1.01s at 100/s to recover).
        async with db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO rate_limits (org_id, tokens, last_refill_at)
                VALUES ($1::uuid, -100.0, NOW())
                ON CONFLICT (org_id) DO UPDATE
                  SET tokens = -100.0, last_refill_at = NOW()
                """,
                org_b.org_id,
            )

        resp = await client.post(
            f"/api/ingest/{org_b.api_key}",
            json={"type": "track", "event": "overflow"},
        )
        assert resp.status_code == 429
        # Retry-After header must be present
        assert "Retry-After" in resp.headers

    @pytest.mark.asyncio
    async def test_rate_limit_per_org_not_global(self, client: AsyncClient, org_a, org_b):
        """
        Exhausting org_b's bucket must NOT affect org_a.
        """
        for i in range(100):
            await client.post(
                f"/api/ingest/{org_b.api_key}",
                json={"type": "track", "event": f"b_{i}"},
            )

        # org_a's bucket is untouched — one request must still succeed
        resp = await client.post(
            f"/api/ingest/{org_a.api_key}",
            json={"type": "track", "event": "a_should_work"},
        )
        assert resp.status_code == 200


# ── CORS ───────────────────────────────────────────────────────────────────────

class TestIngestCors:
    @pytest.mark.asyncio
    async def test_no_origin_header_accepted(self, client: AsyncClient, org_a):
        """Server-to-server calls without Origin should always work."""
        resp = await client.post(
            f"/api/ingest/{org_a.api_key}",
            json={"type": "track", "event": "server_side"},
        )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_origin_blocked_without_js_sdk_connector(
        self, client: AsyncClient, org_a
    ):
        """
        If no js_sdk connector is configured, browser requests (with Origin)
        should be rejected with 403.
        """
        resp = await client.post(
            f"/api/ingest/{org_a.api_key}",
            json={"type": "track", "event": "browser"},
            headers={"Origin": "https://example.com"},
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_origin_allowed_when_in_allowed_origins(
        self, client: AsyncClient, org_a
    ):
        """After creating a js_sdk connector with allowed_origins, the origin passes."""
        await client.post(
            "/api/connectors",
            json={
                "type": "js_sdk",
                "segment": "A",
                "config": {"allowed_origins": ["https://myapp.com"]},
            },
            headers=org_a.auth_headers,
        )

        resp = await client.post(
            f"/api/ingest/{org_a.api_key}",
            json={"type": "page", "anonymousId": "anon-1"},
            headers={"Origin": "https://myapp.com"},
        )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_unlisted_origin_rejected(self, client: AsyncClient, org_a):
        """Origin not in allowed_origins must get 403."""
        await client.post(
            "/api/connectors",
            json={
                "type": "js_sdk",
                "segment": "A",
                "config": {"allowed_origins": ["https://myapp.com"]},
            },
            headers=org_a.auth_headers,
        )

        resp = await client.post(
            f"/api/ingest/{org_a.api_key}",
            json={"type": "page", "anonymousId": "anon-2"},
            headers={"Origin": "https://evil.com"},
        )
        assert resp.status_code == 403
