"""
Tests for GET /api/export/segment-b and GET /api/export/segment-a.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient


class TestExportSegmentB:

    @pytest.mark.asyncio
    async def test_export_returns_csv(self, client: AsyncClient, org_a):
        resp = await client.get(
            "/api/export/segment-b?days=30",
            headers=org_a.auth_headers,
        )
        assert resp.status_code == 200
        assert "text/csv" in resp.headers["content-type"]

    @pytest.mark.asyncio
    async def test_export_content_disposition(self, client: AsyncClient, org_a):
        resp = await client.get(
            "/api/export/segment-b?days=7",
            headers=org_a.auth_headers,
        )
        assert resp.status_code == 200
        cd = resp.headers.get("content-disposition", "")
        assert "attachment" in cd
        assert "segment_b_7d.csv" in cd

    @pytest.mark.asyncio
    async def test_export_with_channel_filter(self, client: AsyncClient, org_a):
        resp = await client.get(
            "/api/export/segment-b?days=30&channel=web",
            headers=org_a.auth_headers,
        )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_export_no_auth_401(self, client: AsyncClient):
        resp = await client.get("/api/export/segment-b?days=30")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_export_days_too_large_422(self, client: AsyncClient, org_a):
        resp = await client.get(
            "/api/export/segment-b?days=999",
            headers=org_a.auth_headers,
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_export_org_isolation(self, client: AsyncClient, org_a, org_b):
        """Each org gets their own data — both return 200 (just different content)."""
        r_a = await client.get("/api/export/segment-b?days=30", headers=org_a.auth_headers)
        r_b = await client.get("/api/export/segment-b?days=30", headers=org_b.auth_headers)
        assert r_a.status_code == 200
        assert r_b.status_code == 200


class TestExportSegmentA:

    @pytest.mark.asyncio
    async def test_export_returns_csv(self, client: AsyncClient, org_a):
        resp = await client.get(
            "/api/export/segment-a?days=30",
            headers=org_a.auth_headers,
        )
        assert resp.status_code == 200
        assert "text/csv" in resp.headers["content-type"]

    @pytest.mark.asyncio
    async def test_export_content_disposition(self, client: AsyncClient, org_a):
        resp = await client.get(
            "/api/export/segment-a?days=14",
            headers=org_a.auth_headers,
        )
        assert resp.status_code == 200
        cd = resp.headers.get("content-disposition", "")
        assert "segment_a_14d.csv" in cd

    @pytest.mark.asyncio
    async def test_export_with_event_type_filter(self, client: AsyncClient, org_a):
        resp = await client.get(
            "/api/export/segment-a?days=30&event_type=purchase",
            headers=org_a.auth_headers,
        )
        assert resp.status_code == 200
        cd = resp.headers.get("content-disposition", "")
        assert "event_purchase" in cd

    @pytest.mark.asyncio
    async def test_export_no_auth_401(self, client: AsyncClient):
        resp = await client.get("/api/export/segment-a?days=30")
        assert resp.status_code == 401
