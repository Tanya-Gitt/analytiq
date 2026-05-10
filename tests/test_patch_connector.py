"""
Tests for PATCH /api/connectors/{id} — partial update endpoint.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient


class TestPatchConnector:
    """Tests for PATCH /api/connectors/{id}."""

    async def _create(self, client: AsyncClient, headers: dict) -> str:
        resp = await client.post(
            "/api/connectors",
            json={
                "type": "sheets_csv",
                "segment": "B",
                "config": {
                    "url": "https://x.com",
                    "target_table": "orders",
                    "column_map": {
                        "OrderID": "order_id",
                        "Date": "order_date",
                        "Qty": "quantity",
                    },
                },
            },
            headers=headers,
        )
        assert resp.status_code == 201, resp.text
        return resp.json()["id"]

    @pytest.mark.asyncio
    async def test_patch_name(self, client: AsyncClient, org_a):
        cid = await self._create(client, org_a.auth_headers)
        resp = await client.patch(
            f"/api/connectors/{cid}",
            json={"name": "Renamed connector"},
            headers=org_a.auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "Renamed connector"

    @pytest.mark.asyncio
    async def test_patch_sync_interval(self, client: AsyncClient, org_a):
        cid = await self._create(client, org_a.auth_headers)
        resp = await client.patch(
            f"/api/connectors/{cid}",
            json={"sync_interval_minutes": 15},
            headers=org_a.auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["sync_interval_minutes"] == 15

    @pytest.mark.asyncio
    async def test_patch_status_paused(self, client: AsyncClient, org_a):
        cid = await self._create(client, org_a.auth_headers)
        resp = await client.patch(
            f"/api/connectors/{cid}",
            json={"status": "paused"},
            headers=org_a.auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "paused"

    @pytest.mark.asyncio
    async def test_patch_empty_body_422(self, client: AsyncClient, org_a):
        cid = await self._create(client, org_a.auth_headers)
        resp = await client.patch(
            f"/api/connectors/{cid}",
            json={},
            headers=org_a.auth_headers,
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_patch_invalid_status_422(self, client: AsyncClient, org_a):
        cid = await self._create(client, org_a.auth_headers)
        resp = await client.patch(
            f"/api/connectors/{cid}",
            json={"status": "invalid_status"},
            headers=org_a.auth_headers,
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_patch_interval_below_one_422(self, client: AsyncClient, org_a):
        cid = await self._create(client, org_a.auth_headers)
        resp = await client.patch(
            f"/api/connectors/{cid}",
            json={"sync_interval_minutes": 0},
            headers=org_a.auth_headers,
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_patch_org_isolation(self, client: AsyncClient, org_a, org_b):
        """org_b cannot patch org_a's connector — RLS returns 404."""
        cid = await self._create(client, org_a.auth_headers)
        resp = await client.patch(
            f"/api/connectors/{cid}",
            json={"name": "Hacked"},
            headers=org_b.auth_headers,
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_patch_no_auth_401(self, client: AsyncClient, org_a):
        cid = await self._create(client, org_a.auth_headers)
        resp = await client.patch(f"/api/connectors/{cid}", json={"name": "X"})
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_patch_nonexistent_404(self, client: AsyncClient, org_a):
        import uuid
        resp = await client.patch(
            f"/api/connectors/{uuid.uuid4()}",
            json={"name": "Ghost"},
            headers=org_a.auth_headers,
        )
        assert resp.status_code == 404
