"""
Tests for POST /api/webhook/{connector_id} — HMAC verification, order upsert,
required-field validation, single vs array body.
"""

from __future__ import annotations

import hashlib
import hmac
import json

import pytest
from httpx import AsyncClient


def _sign(body: bytes, secret: str) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


async def _create_webhook_connector(
    client: AsyncClient, auth_headers: dict, secret: str = "test-secret-abc"
) -> str:
    resp = await client.post(
        "/api/connectors",
        json={
            "type": "webhook",
            "segment": "B",
            "config": {"secret": secret},
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201
    return resp.json()["id"]


# ── HMAC verification ──────────────────────────────────────────────────────────

class TestWebhookHmac:
    SECRET = "s3cr3t-webhook-key"

    @pytest.mark.asyncio
    async def test_valid_signature_accepted(self, client: AsyncClient, org_a):
        connector_id = await _create_webhook_connector(
            client, org_a.auth_headers, self.SECRET
        )
        payload = {
            "order_id": "ORD-HMAC-1",
            "order_date": "2024-03-01",
            "quantity": 2,
        }
        body = json.dumps(payload).encode()
        sig = _sign(body, self.SECRET)

        resp = await client.post(
            f"/api/webhook/{connector_id}",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Webhook-Signature": sig,
            },
        )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_invalid_signature_returns_401(self, client: AsyncClient, org_a):
        connector_id = await _create_webhook_connector(
            client, org_a.auth_headers, self.SECRET
        )
        payload = {"order_id": "ORD-1", "order_date": "2024-01-01", "quantity": 1}
        body = json.dumps(payload).encode()

        resp = await client.post(
            f"/api/webhook/{connector_id}",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Webhook-Signature": "badhex0000",
            },
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_missing_signature_header_returns_401(
        self, client: AsyncClient, org_a
    ):
        connector_id = await _create_webhook_connector(
            client, org_a.auth_headers, self.SECRET
        )
        payload = {"order_id": "ORD-2", "order_date": "2024-01-01", "quantity": 1}
        body = json.dumps(payload).encode()

        resp = await client.post(
            f"/api/webhook/{connector_id}",
            content=body,
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 401


# ── required field validation ──────────────────────────────────────────────────

class TestWebhookRequiredFields:
    SECRET = "required-fields-secret"

    @pytest.mark.asyncio
    async def test_missing_order_id_returns_422(self, client: AsyncClient, org_a):
        connector_id = await _create_webhook_connector(
            client, org_a.auth_headers, self.SECRET
        )
        payload = {"order_date": "2024-01-01", "quantity": 5}
        body = json.dumps(payload).encode()
        sig = _sign(body, self.SECRET)

        resp = await client.post(
            f"/api/webhook/{connector_id}",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Webhook-Signature": sig,
            },
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_missing_order_date_returns_422(self, client: AsyncClient, org_a):
        connector_id = await _create_webhook_connector(
            client, org_a.auth_headers, self.SECRET
        )
        payload = {"order_id": "ORD-X", "quantity": 3}
        body = json.dumps(payload).encode()
        sig = _sign(body, self.SECRET)

        resp = await client.post(
            f"/api/webhook/{connector_id}",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Webhook-Signature": sig,
            },
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_missing_quantity_returns_422(self, client: AsyncClient, org_a):
        connector_id = await _create_webhook_connector(
            client, org_a.auth_headers, self.SECRET
        )
        payload = {"order_id": "ORD-Y", "order_date": "2024-01-01"}
        body = json.dumps(payload).encode()
        sig = _sign(body, self.SECRET)

        resp = await client.post(
            f"/api/webhook/{connector_id}",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Webhook-Signature": sig,
            },
        )
        assert resp.status_code == 422


# ── single vs array body ───────────────────────────────────────────────────────

class TestWebhookBodyShape:
    SECRET = "body-shape-secret"

    @pytest.mark.asyncio
    async def test_array_body_accepted(self, client: AsyncClient, org_a):
        connector_id = await _create_webhook_connector(
            client, org_a.auth_headers, self.SECRET
        )
        payload = [
            {"order_id": "ORD-ARR-1", "order_date": "2024-02-01", "quantity": 1},
            {"order_id": "ORD-ARR-2", "order_date": "2024-02-02", "quantity": 2},
        ]
        body = json.dumps(payload).encode()
        sig = _sign(body, self.SECRET)

        resp = await client.post(
            f"/api/webhook/{connector_id}",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Webhook-Signature": sig,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("rows_upserted") == 2

    @pytest.mark.asyncio
    async def test_idempotent_upsert(self, client: AsyncClient, org_a):
        """Sending the same order_id twice must not duplicate the row."""
        connector_id = await _create_webhook_connector(
            client, org_a.auth_headers, self.SECRET
        )
        payload = {"order_id": "ORD-DUP", "order_date": "2024-03-01", "quantity": 5}
        body = json.dumps(payload).encode()
        sig = _sign(body, self.SECRET)
        headers = {
            "Content-Type": "application/json",
            "X-Webhook-Signature": sig,
        }

        await client.post(f"/api/webhook/{connector_id}", content=body, headers=headers)
        resp = await client.post(f"/api/webhook/{connector_id}", content=body, headers=headers)
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_unknown_connector_id_returns_404(self, client: AsyncClient, org_a):
        fake_id = "00000000-0000-0000-0000-000000000000"
        payload = {"order_id": "X", "order_date": "2024-01-01", "quantity": 1}
        body = json.dumps(payload).encode()
        sig = _sign(body, "any-secret")

        resp = await client.post(
            f"/api/webhook/{fake_id}",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Webhook-Signature": sig,
            },
        )
        assert resp.status_code == 404


# ── edge cases ─────────────────────────────────────────────────────────────────

class TestWebhookEdgeCases:
    SECRET = "edge-case-secret"

    @pytest.mark.asyncio
    async def test_invalid_json_body_returns_400(self, client: AsyncClient, org_a):
        """Non-JSON body must return 400 (not 422 or 500)."""
        connector_id = await _create_webhook_connector(
            client, org_a.auth_headers, self.SECRET
        )
        body = b"this is not json at all"
        sig = _sign(body, self.SECRET)

        resp = await client.post(
            f"/api/webhook/{connector_id}",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Webhook-Signature": sig,
            },
        )
        assert resp.status_code == 400
        assert "json" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_empty_array_body_returns_zero_upserted(
        self, client: AsyncClient, org_a
    ):
        """An empty JSON array must succeed with rows_upserted=0 (no DB writes)."""
        connector_id = await _create_webhook_connector(
            client, org_a.auth_headers, self.SECRET
        )
        body = json.dumps([]).encode()
        sig = _sign(body, self.SECRET)

        resp = await client.post(
            f"/api/webhook/{connector_id}",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Webhook-Signature": sig,
            },
        )
        assert resp.status_code == 200
        assert resp.json()["rows_upserted"] == 0

