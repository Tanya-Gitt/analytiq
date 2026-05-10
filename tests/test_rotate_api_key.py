"""
Tests for POST /api/auth/rotate-api-key.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient


class TestRotateApiKey:

    @pytest.mark.asyncio
    async def test_rotate_returns_new_key(self, client: AsyncClient, org_a):
        """POST rotate-api-key returns a new api_key string."""
        resp = await client.post(
            "/api/auth/rotate-api-key",
            headers=org_a.auth_headers,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "api_key" in body
        assert isinstance(body["api_key"], str)
        assert len(body["api_key"]) == 48  # encode(gen_random_bytes(24), 'hex')

    @pytest.mark.asyncio
    async def test_rotate_changes_key(self, client: AsyncClient, org_a):
        """Each rotation returns a different key."""
        r1 = await client.post("/api/auth/rotate-api-key", headers=org_a.auth_headers)
        r2 = await client.post("/api/auth/rotate-api-key", headers=org_a.auth_headers)
        assert r1.json()["api_key"] != r2.json()["api_key"]

    @pytest.mark.asyncio
    async def test_rotate_no_auth_401(self, client: AsyncClient):
        resp = await client.post("/api/auth/rotate-api-key")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_me_reflects_new_key(self, client: AsyncClient, org_a):
        """After rotation, /me returns the new api_key."""
        rotate = await client.post(
            "/api/auth/rotate-api-key", headers=org_a.auth_headers
        )
        new_key = rotate.json()["api_key"]

        me = await client.get("/api/auth/me", headers=org_a.auth_headers)
        assert me.json()["api_key"] == new_key
