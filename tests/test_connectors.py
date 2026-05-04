"""
Tests for POST /api/connectors — column_map validation, sanitize_column_name,
connector creation, and POST /api/connectors/{id}/upload-csv.
"""

from __future__ import annotations

import io

import pytest
from httpx import AsyncClient

# ── column_map validation ──────────────────────────────────────────────────────

class TestColumnMapValidation:
    """Validation at connector creation time (not sync time)."""

    @pytest.mark.asyncio
    async def test_csv_upload_missing_required_column_422(
        self, client: AsyncClient, org_a
    ):
        """order_id, order_date, quantity are required for orders target."""
        resp = await client.post(
            "/api/connectors",
            json={
                "type": "csv_upload",
                "segment": "B",
                "config": {
                    "target_table": "orders",
                    "column_map": {
                        # missing order_date and quantity
                        "OrderID": "order_id",
                    },
                },
            },
            headers=org_a.auth_headers,
        )
        assert resp.status_code == 422
        body = resp.json()
        assert "order_date" in str(body) or "quantity" in str(body)

    @pytest.mark.asyncio
    async def test_csv_upload_all_required_columns_201(
        self, client: AsyncClient, org_a
    ):
        resp = await client.post(
            "/api/connectors",
            json={
                "type": "csv_upload",
                "segment": "B",
                "config": {
                    "target_table": "orders",
                    "column_map": {
                        "OrderID":   "order_id",
                        "Date":      "order_date",
                        "Units":     "quantity",
                        "UnitPrice": "price_per_unit",
                    },
                },
            },
            headers=org_a.auth_headers,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["type"] == "csv_upload"
        assert "id" in data

    @pytest.mark.asyncio
    async def test_custom_rows_bypass_required_column_check(
        self, client: AsyncClient, org_a
    ):
        """custom_rows target (Segment A) does not require orders columns."""
        resp = await client.post(
            "/api/connectors",
            json={
                "type": "csv_upload",
                "segment": "A",
                "config": {
                    "target_table": "custom_rows",
                    "column_map": {
                        "event":  "event_name",
                        "userid": "user_id",
                    },
                },
            },
            headers=org_a.auth_headers,
        )
        assert resp.status_code == 201

    @pytest.mark.asyncio
    async def test_sheets_csv_connector_validated_same_way(
        self, client: AsyncClient, org_a
    ):
        """sheets_csv type also validates column_map at creation."""
        resp = await client.post(
            "/api/connectors",
            json={
                "type": "sheets_csv",
                "segment": "B",
                "config": {
                    "url": "https://example.com/export.csv",
                    "target_table": "orders",
                    "column_map": {
                        "ID":    "order_id",
                        # missing order_date and quantity
                    },
                },
            },
            headers=org_a.auth_headers,
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_unauthenticated_rejected(self, client: AsyncClient):
        resp = await client.post(
            "/api/connectors",
            json={
                "type": "csv_upload",
                "segment": "B",
                "config": {"target_table": "orders", "column_map": {}},
            },
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_invalid_type_returns_422(self, client: AsyncClient, org_a):
        """Unknown connector type must be rejected with 422."""
        resp = await client.post(
            "/api/connectors",
            json={
                "type": "ftp_server",   # not a valid type
                "segment": "B",
                "config": {},
            },
            headers=org_a.auth_headers,
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_invalid_segment_returns_422(self, client: AsyncClient, org_a):
        """Segment must be 'A' or 'B' — anything else returns 422."""
        resp = await client.post(
            "/api/connectors",
            json={
                "type": "csv_upload",
                "segment": "C",  # invalid
                "config": {},
            },
            headers=org_a.auth_headers,
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_unsafe_csv_header_name_returns_422(
        self, client: AsyncClient, org_a
    ):
        """A column_map key that sanitizes to an empty string must return 422."""
        resp = await client.post(
            "/api/connectors",
            json={
                "type": "csv_upload",
                "segment": "B",
                "config": {
                    "target_table": "orders",
                    "column_map": {
                        "!@#$%": "order_id",   # all special chars → empty after sanitization
                        "Date":  "order_date",
                        "Qty":   "quantity",
                    },
                },
            },
            headers=org_a.auth_headers,
        )
        assert resp.status_code == 422


# ── sanitize_column_name ───────────────────────────────────────────────────────

class TestSanitizeColumnName:
    """Unit tests for the sanitizer — import directly to avoid HTTP overhead."""

    def _sanitize(self, name: str) -> str:
        from app.routers.connectors import sanitize_column_name
        return sanitize_column_name(name)

    def test_clean_name_unchanged(self):
        assert self._sanitize("order_id") == "order_id"

    def test_spaces_replaced_with_underscore(self):
        assert self._sanitize("Order ID") == "Order_ID"

    def test_special_chars_stripped(self):
        assert self._sanitize("price-per-unit!") == "price_per_unit_"

    def test_leading_digit_prefixed(self):
        assert self._sanitize("1stColumn") == "col_1stColumn"[:63]

    def test_truncated_to_63_chars(self):
        long_name = "a" * 100
        result = self._sanitize(long_name)
        assert len(result) <= 63

    def test_empty_raises(self):
        import pytest
        with pytest.raises(ValueError):
            self._sanitize("")

    def test_only_special_chars_raises(self):
        import pytest
        with pytest.raises(ValueError):
            self._sanitize("!@#$%")


# ── upload-csv endpoint ───────────────────────────────────────────────────────

class TestUploadCsv:
    """Tests for POST /api/connectors/{id}/upload-csv."""

    _CSV_CONTENT = (
        b"OrderID,Date,Units,UnitPrice\n"
        b"ORD-1,2024-01-01,2,9.99\n"
        b"ORD-2,2024-01-02,1,19.99\n"
    )

    async def _create_csv_upload_connector(
        self, client: AsyncClient, headers: dict
    ) -> str:
        resp = await client.post(
            "/api/connectors",
            json={
                "type": "csv_upload",
                "segment": "B",
                "config": {
                    "target_table": "orders",
                    "column_map": {
                        "OrderID":   "order_id",
                        "Date":      "order_date",
                        "Units":     "quantity",
                        "UnitPrice": "price_per_unit",
                    },
                },
            },
            headers=headers,
        )
        assert resp.status_code == 201
        return resp.json()["id"]

    @pytest.mark.asyncio
    async def test_upload_csv_returns_202(self, client: AsyncClient, org_a):
        connector_id = await self._create_csv_upload_connector(
            client, org_a.auth_headers
        )
        resp = await client.post(
            f"/api/connectors/{connector_id}/upload-csv",
            files={"file": ("orders.csv", io.BytesIO(self._CSV_CONTENT), "text/csv")},
            headers=org_a.auth_headers,
        )
        assert resp.status_code == 202
        data = resp.json()
        assert data["ok"] is True
        assert "sync" in data["message"].lower()

    @pytest.mark.asyncio
    async def test_upload_csv_wrong_type_returns_422(
        self, client: AsyncClient, org_a
    ):
        """Only csv_upload connectors accept file uploads."""
        # Create a webhook connector instead
        resp = await client.post(
            "/api/connectors",
            json={
                "type": "webhook",
                "segment": "B",
                "config": {"secret": "test-sec"},
            },
            headers=org_a.auth_headers,
        )
        assert resp.status_code == 201
        webhook_id = resp.json()["id"]

        upload_resp = await client.post(
            f"/api/connectors/{webhook_id}/upload-csv",
            files={"file": ("data.csv", io.BytesIO(self._CSV_CONTENT), "text/csv")},
            headers=org_a.auth_headers,
        )
        assert upload_resp.status_code == 422
        assert "csv_upload" in upload_resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_upload_csv_empty_file_returns_422(
        self, client: AsyncClient, org_a
    ):
        connector_id = await self._create_csv_upload_connector(
            client, org_a.auth_headers
        )
        resp = await client.post(
            f"/api/connectors/{connector_id}/upload-csv",
            files={"file": ("empty.csv", io.BytesIO(b""), "text/csv")},
            headers=org_a.auth_headers,
        )
        assert resp.status_code == 422
        assert "empty" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_upload_csv_unknown_connector_returns_404(
        self, client: AsyncClient, org_a
    ):
        fake_id = "00000000-0000-0000-0000-000000000099"
        resp = await client.post(
            f"/api/connectors/{fake_id}/upload-csv",
            files={"file": ("data.csv", io.BytesIO(self._CSV_CONTENT), "text/csv")},
            headers=org_a.auth_headers,
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_upload_csv_unauthenticated_returns_401(
        self, client: AsyncClient, org_a
    ):
        connector_id = await self._create_csv_upload_connector(
            client, org_a.auth_headers
        )
        resp = await client.post(
            f"/api/connectors/{connector_id}/upload-csv",
            files={"file": ("data.csv", io.BytesIO(self._CSV_CONTENT), "text/csv")},
            # no auth headers
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_upload_csv_org_isolation(
        self, client: AsyncClient, org_a, org_b
    ):
        """org_b cannot upload a CSV to org_a's connector."""
        connector_id = await self._create_csv_upload_connector(
            client, org_a.auth_headers
        )
        resp = await client.post(
            f"/api/connectors/{connector_id}/upload-csv",
            files={"file": ("data.csv", io.BytesIO(self._CSV_CONTENT), "text/csv")},
            headers=org_b.auth_headers,
        )
        assert resp.status_code == 404  # RLS hides it as not found


# ── connector isolation ────────────────────────────────────────────────────────

class TestConnectorOrgIsolation:
    """Connectors created by one org must not be visible to another."""

    @pytest.mark.asyncio
    async def test_list_connectors_only_own_org(
        self, client: AsyncClient, org_a, org_b
    ):
        # Create connector for org_a
        create_resp = await client.post(
            "/api/connectors",
            json={
                "type": "csv_upload",
                "segment": "B",
                "config": {
                    "target_table": "orders",
                    "column_map": {
                        "ID":   "order_id",
                        "Date": "order_date",
                        "Qty":  "quantity",
                    },
                },
            },
            headers=org_a.auth_headers,
        )
        assert create_resp.status_code == 201
        connector_id = create_resp.json()["id"]

        # Org B should not see org A's connector
        list_resp = await client.get("/api/connectors", headers=org_b.auth_headers)
        assert list_resp.status_code == 200
        ids = [c["id"] for c in list_resp.json()]
        assert connector_id not in ids


# ── DELETE /api/connectors/{id} ───────────────────────────────────────────────

class TestDeleteConnector:
    """DELETE /api/connectors/{id} — happy path, not found, cross-org isolation."""

    _BASE_PAYLOAD = {
        "type": "csv_upload",
        "segment": "B",
        "config": {
            "target_table": "orders",
            "column_map": {"ID": "order_id", "Date": "order_date", "Qty": "quantity"},
        },
    }

    async def _create(self, client: AsyncClient, headers: dict) -> str:
        resp = await client.post("/api/connectors", json=self._BASE_PAYLOAD, headers=headers)
        assert resp.status_code == 201
        return resp.json()["id"]

    @pytest.mark.asyncio
    async def test_delete_returns_204(self, client: AsyncClient, org_a):
        connector_id = await self._create(client, org_a.auth_headers)
        resp = await client.delete(
            f"/api/connectors/{connector_id}", headers=org_a.auth_headers
        )
        assert resp.status_code == 204

    @pytest.mark.asyncio
    async def test_delete_removes_from_list(self, client: AsyncClient, org_a):
        connector_id = await self._create(client, org_a.auth_headers)
        await client.delete(f"/api/connectors/{connector_id}", headers=org_a.auth_headers)
        list_resp = await client.get("/api/connectors", headers=org_a.auth_headers)
        ids = [c["id"] for c in list_resp.json()]
        assert connector_id not in ids

    @pytest.mark.asyncio
    async def test_delete_unknown_connector_returns_404(self, client: AsyncClient, org_a):
        fake_id = "00000000-0000-0000-0000-000000000099"
        resp = await client.delete(f"/api/connectors/{fake_id}", headers=org_a.auth_headers)
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_unauthenticated_returns_401(self, client: AsyncClient, org_a):
        connector_id = await self._create(client, org_a.auth_headers)
        resp = await client.delete(f"/api/connectors/{connector_id}")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_delete_org_isolation(self, client: AsyncClient, org_a, org_b):
        """org_b cannot delete org_a's connector — RLS returns 404."""
        connector_id = await self._create(client, org_a.auth_headers)
        resp = await client.delete(
            f"/api/connectors/{connector_id}", headers=org_b.auth_headers
        )
        assert resp.status_code == 404
        # Connector still exists for org_a
        list_resp = await client.get("/api/connectors", headers=org_a.auth_headers)
        ids = [c["id"] for c in list_resp.json()]
        assert connector_id in ids


# ── POST /api/connectors/{id}/sync ────────────────────────────────────────────

class TestTriggerSync:
    """POST /api/connectors/{id}/sync — manual sync trigger."""

    # Use csv_upload (not sheets_csv) so the background sync task reads from
    # base64 in config rather than making a real HTTP request.  A live network
    # call during teardown corrupts asyncpg pool connections and causes the
    # org fixture's DELETE to fail with 118 errors across the suite.
    _BASE = {
        "type": "csv_upload",
        "segment": "B",
        "config": {
            "target_table": "orders",
            "column_map": {"ID": "order_id", "Date": "order_date", "Qty": "quantity"},
        },
    }

    async def _create(self, client: AsyncClient, headers: dict) -> str:
        resp = await client.post("/api/connectors", json=self._BASE, headers=headers)
        assert resp.status_code == 201
        return resp.json()["id"]

    @pytest.mark.asyncio
    async def test_trigger_sync_returns_202(self, client: AsyncClient, org_a):
        connector_id = await self._create(client, org_a.auth_headers)
        resp = await client.post(
            f"/api/connectors/{connector_id}/sync", headers=org_a.auth_headers
        )
        assert resp.status_code == 202
        assert resp.json()["ok"] is True

    @pytest.mark.asyncio
    async def test_trigger_sync_unknown_connector_returns_404(
        self, client: AsyncClient, org_a
    ):
        fake_id = "00000000-0000-0000-0000-000000000099"
        resp = await client.post(
            f"/api/connectors/{fake_id}/sync", headers=org_a.auth_headers
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_trigger_sync_unauthenticated_returns_401(
        self, client: AsyncClient, org_a
    ):
        connector_id = await self._create(client, org_a.auth_headers)
        resp = await client.post(f"/api/connectors/{connector_id}/sync")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_trigger_sync_webhook_returns_422(self, client: AsyncClient, org_a):
        """webhook connectors are push-based and cannot be manually synced."""
        resp = await client.post(
            "/api/connectors",
            json={
                "type": "webhook",
                "segment": "B",
                "config": {"secret": "mysecret"},
            },
            headers=org_a.auth_headers,
        )
        assert resp.status_code == 201
        connector_id = resp.json()["id"]
        sync_resp = await client.post(
            f"/api/connectors/{connector_id}/sync", headers=org_a.auth_headers
        )
        assert sync_resp.status_code == 422

    @pytest.mark.asyncio
    async def test_trigger_sync_js_sdk_returns_422(self, client: AsyncClient, org_a):
        """js_sdk connectors are push-based and cannot be manually synced."""
        resp = await client.post(
            "/api/connectors",
            json={
                "type": "js_sdk",
                "segment": "A",
                "config": {"allowed_origins": ["https://example.com"]},
            },
            headers=org_a.auth_headers,
        )
        assert resp.status_code == 201
        connector_id = resp.json()["id"]
        sync_resp = await client.post(
            f"/api/connectors/{connector_id}/sync", headers=org_a.auth_headers
        )
        assert sync_resp.status_code == 422

    @pytest.mark.asyncio
    async def test_trigger_sync_org_isolation(
        self, client: AsyncClient, org_a, org_b
    ):
        """org_b cannot trigger a sync on org_a's connector."""
        connector_id = await self._create(client, org_a.auth_headers)
        resp = await client.post(
            f"/api/connectors/{connector_id}/sync", headers=org_b.auth_headers
        )
        assert resp.status_code == 404
