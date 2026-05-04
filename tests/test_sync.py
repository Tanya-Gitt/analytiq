"""
Tests for app/connectors/sync.py — sync_connector() success/failure paths
and sync_runs status tracking.
"""

from __future__ import annotations

import base64
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import asyncpg
import pytest

from app.connectors.sync import sync_connector

# ── helpers ────────────────────────────────────────────────────────────────────

def _make_csv_bytes(rows: list[dict]) -> bytes:
    if not rows:
        return b"order_id,order_date,quantity\n"
    header = ",".join(rows[0].keys())
    lines = [header] + [",".join(str(v) for v in row.values()) for row in rows]
    return "\n".join(lines).encode()


def _b64_csv(rows: list[dict]) -> str:
    return base64.b64encode(_make_csv_bytes(rows)).decode()


async def _make_connector_record(pool: asyncpg.Pool, org_id: str, **kwargs) -> asyncpg.Record:
    """Insert a connector row and return it as an asyncpg Record."""
    config = kwargs.pop("config", {})
    conn_type = kwargs.pop("type", "csv_upload")
    segment = kwargs.pop("segment", "B")

    async with pool.acquire() as conn:
        async with conn.transaction():
            # FORCE ROW LEVEL SECURITY requires SET LOCAL even for superuser
            await conn.execute(f"SET LOCAL app.org_id = '{org_id}'")
            row = await conn.fetchrow(
                """
                INSERT INTO connectors (org_id, name, type, segment, config)
                VALUES ($1, $2, $3, $4, $5)
                RETURNING id, org_id, type, segment, config, status, sync_interval_minutes
                """,
                org_id,
                f"{conn_type} test connector",
                conn_type,
                segment,
                config,
            )
    return row


# ── csv_upload sync ────────────────────────────────────────────────────────────

class TestCsvUploadSync:
    @pytest.mark.asyncio
    async def test_success_upserts_orders(self, db_pool, org_a):
        rows = [
            {"order_id": "SYNC-1", "order_date": "2024-01-01", "quantity": "3"},
            {"order_id": "SYNC-2", "order_date": "2024-01-02", "quantity": "7"},
        ]
        config = {
            "target_table": "orders",
            "column_map": {
                "order_id": "order_id",
                "order_date": "order_date",
                "quantity": "quantity",
            },
            "pending_bytes_b64": _b64_csv(rows),
        }
        connector = await _make_connector_record(db_pool, org_a.org_id, config=config)

        await sync_connector(db_pool, connector)

        # Verify orders were upserted
        async with db_pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(f"SET LOCAL app.org_id = '{str(org_a.org_id)}'")
                count = await conn.fetchval("SELECT COUNT(*) FROM orders")
        assert count == 2

    @pytest.mark.asyncio
    async def test_success_updates_last_synced_at(self, db_pool, org_a):
        before = datetime.now(timezone.utc)
        config = {
            "target_table": "orders",
            "column_map": {
                "order_id": "order_id",
                "order_date": "order_date",
                "quantity": "quantity",
            },
            "pending_bytes_b64": _b64_csv([
                {"order_id": "SYNC-TS-1", "order_date": "2024-01-01", "quantity": "1"},
            ]),
        }
        connector = await _make_connector_record(db_pool, org_a.org_id, config=config)
        await sync_connector(db_pool, connector)

        async with db_pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT last_synced_at, status FROM connectors WHERE id = $1",
                connector["id"],
            )
        assert row["last_synced_at"] >= before
        assert row["status"] == "active"

    @pytest.mark.asyncio
    async def test_sync_runs_record_created_success(self, db_pool, org_a):
        config = {
            "target_table": "orders",
            "column_map": {
                "order_id": "order_id",
                "order_date": "order_date",
                "quantity": "quantity",
            },
            "pending_bytes_b64": _b64_csv([
                {"order_id": "SR-1", "order_date": "2024-03-01", "quantity": "2"},
            ]),
        }
        connector = await _make_connector_record(db_pool, org_a.org_id, config=config)
        await sync_connector(db_pool, connector)

        async with db_pool.acquire() as conn:
            run = await conn.fetchrow(
                "SELECT status, rows_upserted FROM sync_runs WHERE connector_id = $1",
                connector["id"],
            )
        assert run["status"] == "success"
        assert run["rows_upserted"] == 1

    @pytest.mark.asyncio
    async def test_idempotent_upsert_on_rerun(self, db_pool, org_a):
        """Running the same CSV twice must not duplicate orders."""
        config = {
            "target_table": "orders",
            "column_map": {
                "order_id": "order_id",
                "order_date": "order_date",
                "quantity": "quantity",
            },
            "pending_bytes_b64": _b64_csv([
                {"order_id": "IDEM-1", "order_date": "2024-01-01", "quantity": "5"},
            ]),
        }
        connector = await _make_connector_record(db_pool, org_a.org_id, config=config)
        await sync_connector(db_pool, connector)
        await sync_connector(db_pool, connector)

        async with db_pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(f"SET LOCAL app.org_id = '{str(org_a.org_id)}'")
                count = await conn.fetchval(
                    "SELECT COUNT(*) FROM orders WHERE order_id = 'IDEM-1'"
                )
        assert count == 1


# ── failure path ───────────────────────────────────────────────────────────────

class TestSyncFailure:
    @pytest.mark.asyncio
    async def test_bad_base64_sets_error_status(self, db_pool, org_a):
        config = {
            "target_table": "orders",
            "column_map": {"order_id": "order_id", "order_date": "order_date", "quantity": "quantity"},
            "pending_bytes_b64": "not-valid-base64!!!",
        }
        connector = await _make_connector_record(db_pool, org_a.org_id, config=config)

        # Should not raise — errors are caught internally
        await sync_connector(db_pool, connector)

        async with db_pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT status, last_error FROM connectors WHERE id = $1",
                connector["id"],
            )
            run = await conn.fetchrow(
                "SELECT status, error_message FROM sync_runs WHERE connector_id = $1",
                connector["id"],
            )

        assert row["status"] == "error"
        assert row["last_error"] is not None
        assert run["status"] == "failed"
        assert run["error_message"] is not None

    @pytest.mark.asyncio
    async def test_http_error_sets_error_status(self, db_pool, org_a):
        """sheets_csv HTTP 404 should mark connector as error."""
        config = {
            "target_table": "orders",
            "column_map": {"order_id": "order_id", "order_date": "order_date", "quantity": "quantity"},
            "url": "https://example.com/nonexistent.csv",
        }
        connector = await _make_connector_record(
            db_pool, org_a.org_id, type="sheets_csv", config=config
        )

        mock_resp = AsyncMock()
        mock_resp.status_code = 404
        mock_resp.content = b""

        with patch("app.connectors.sync.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.get = AsyncMock(return_value=mock_resp)
            mock_client_cls.return_value = mock_client

            await sync_connector(db_pool, connector)

        async with db_pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT status FROM connectors WHERE id = $1", connector["id"]
            )
        assert row["status"] == "error"


# ── push-based connectors ──────────────────────────────────────────────────────

class TestPushBasedConnectors:
    @pytest.mark.asyncio
    async def test_webhook_connector_is_noop(self, db_pool, org_a):
        connector = await _make_connector_record(
            db_pool, org_a.org_id, type="webhook", config={"secret": "x"}
        )
        # Should return immediately without touching sync_runs
        await sync_connector(db_pool, connector)

        async with db_pool.acquire() as conn:
            count = await conn.fetchval(
                "SELECT COUNT(*) FROM sync_runs WHERE connector_id = $1", connector["id"]
            )
        assert count == 0

    @pytest.mark.asyncio
    async def test_js_sdk_connector_is_noop(self, db_pool, org_a):
        connector = await _make_connector_record(
            db_pool, org_a.org_id, type="js_sdk", config={"allowed_origins": []}
        )
        await sync_connector(db_pool, connector)

        async with db_pool.acquire() as conn:
            count = await conn.fetchval(
                "SELECT COUNT(*) FROM sync_runs WHERE connector_id = $1", connector["id"]
            )
        assert count == 0


# ── _fetch_csv missing config ──────────────────────────────────────────────────

class TestFetchCsvMissingConfig:
    """Missing required config keys set connector to error without raising."""

    @pytest.mark.asyncio
    async def test_sheets_csv_missing_url_sets_error(self, db_pool, org_a):
        """sheets_csv without config.url must mark the connector as error."""
        config = {
            "target_table": "orders",
            "column_map": {
                "order_id": "order_id",
                "order_date": "order_date",
                "quantity": "quantity",
            },
            # 'url' intentionally omitted
        }
        connector = await _make_connector_record(
            db_pool, org_a.org_id, type="sheets_csv", config=config
        )

        await sync_connector(db_pool, connector)

        async with db_pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT status, last_error FROM connectors WHERE id = $1",
                connector["id"],
            )
        assert row["status"] == "error"
        assert row["last_error"] is not None

    @pytest.mark.asyncio
    async def test_csv_upload_missing_b64_sets_error(self, db_pool, org_a):
        """csv_upload without config.pending_bytes_b64 must mark the connector as error."""
        config = {
            "target_table": "orders",
            "column_map": {
                "order_id": "order_id",
                "order_date": "order_date",
                "quantity": "quantity",
            },
            # 'pending_bytes_b64' intentionally omitted
        }
        connector = await _make_connector_record(
            db_pool, org_a.org_id, type="csv_upload", config=config
        )

        await sync_connector(db_pool, connector)

        async with db_pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT status, last_error FROM connectors WHERE id = $1",
                connector["id"],
            )
        assert row["status"] == "error"
        assert row["last_error"] is not None


# ── Segment A / custom_rows path ──────────────────────────────────────────────

class TestSegmentACustomRows:
    """
    When segment = 'A' or target_table = 'custom_rows', rows go to the
    custom_rows JSONB table via _upsert_custom_rows.
    """

    @pytest.mark.asyncio
    async def test_segment_a_rows_inserted_into_custom_rows(self, db_pool, org_a):
        """Segment A connector syncs rows into custom_rows, not orders."""
        rows = [
            {"event": "page_view", "user_id": "u-1", "ts": "2024-01-01T00:00:00"},
            {"event": "click",     "user_id": "u-2", "ts": "2024-01-01T01:00:00"},
        ]
        csv_header = ",".join(rows[0].keys())
        csv_lines = [csv_header] + [",".join(str(v) for v in r.values()) for r in rows]
        csv_bytes = "\n".join(csv_lines).encode()
        b64 = base64.b64encode(csv_bytes).decode()

        config = {
            "target_table": "custom_rows",
            # column_map must be non-empty: empty map → parse_csv_rows returns []
            "column_map": {
                "event":   "event",
                "user_id": "user_id",
                "ts":      "ts",
            },
            "pending_bytes_b64": b64,
        }
        # Segment A: target != "orders" → goes to _upsert_custom_rows
        connector = await _make_connector_record(
            db_pool, org_a.org_id, type="csv_upload", segment="A", config=config
        )
        await sync_connector(db_pool, connector)

        async with db_pool.acquire() as conn:
            count = await conn.fetchval(
                "SELECT COUNT(*) FROM custom_rows WHERE connector_id = $1",
                connector["id"],
            )
        assert count == 2

    @pytest.mark.asyncio
    async def test_segment_b_custom_table_goes_to_custom_rows(self, db_pool, org_a):
        """Segment B with target_table=custom_rows also routes to _upsert_custom_rows."""
        csv_bytes = b"name,value\nfoo,1\nbar,2\n"
        b64 = base64.b64encode(csv_bytes).decode()

        config = {
            "target_table": "custom_rows",
            "column_map": {
                "name":  "name",
                "value": "value",
            },
            "pending_bytes_b64": b64,
        }
        connector = await _make_connector_record(
            db_pool, org_a.org_id, type="csv_upload", segment="B", config=config
        )
        await sync_connector(db_pool, connector)

        async with db_pool.acquire() as conn:
            count = await conn.fetchval(
                "SELECT COUNT(*) FROM custom_rows WHERE connector_id = $1",
                connector["id"],
            )
        assert count == 2


# ── sheets_csv happy path ─────────────────────────────────────────────────────

class TestSheetsCsvSuccess:
    """sheets_csv connector: mock a 200 HTTP response with valid CSV content."""

    @pytest.mark.asyncio
    async def test_sheets_csv_200_upserts_orders(self, db_pool, org_a):
        csv_content = (
            b"order_id,order_date,quantity\n"
            b"SHEET-1,2024-03-01,4\n"
            b"SHEET-2,2024-03-02,2\n"
        )
        config = {
            "target_table": "orders",
            "url": "https://docs.google.com/spreadsheets/fake",
            "column_map": {
                "order_id":   "order_id",
                "order_date": "order_date",
                "quantity":   "quantity",
            },
        }
        connector = await _make_connector_record(
            db_pool, org_a.org_id, type="sheets_csv", config=config
        )

        mock_resp = AsyncMock()
        mock_resp.status_code = 200
        mock_resp.content = csv_content

        with patch("app.connectors.sync.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.get = AsyncMock(return_value=mock_resp)
            mock_client_cls.return_value = mock_client

            await sync_connector(db_pool, connector)

        async with db_pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT status, last_error FROM connectors WHERE id = $1",
                connector["id"],
            )
        assert row["status"] == "active"
        assert row["last_error"] is None


# ── _fetch_csv unknown type ────────────────────────────────────────────────────

class TestFetchCsvUnknownType:
    """Calling _fetch_csv with an unrecognised type must raise ValueError."""

    @pytest.mark.asyncio
    async def test_unknown_type_raises_value_error(self, db_pool, org_a):
        """
        If a connector type somehow reaches _fetch_csv without being
        'sheets_csv' or 'csv_upload', it raises ValueError and the sync
        marks the connector as error.
        """
        import pytest as _pytest

        from app.connectors.sync import _fetch_csv
        with _pytest.raises(ValueError, match="Unknown connector type"):
            await _fetch_csv("ftp_server", {})


class TestUpsertCustomRowsEmpty:
    """_upsert_custom_rows with empty rows list returns 0 (early-return path)."""

    @pytest.mark.asyncio
    async def test_empty_csv_custom_rows_upserts_zero(self, db_pool, org_a):
        """
        A CSV with only a header and no data rows calls _upsert_custom_rows([])
        which hits the early-return `if not rows: return 0` path.
        """
        csv_bytes = b"event,user_id\n"  # header only — no data rows
        b64 = base64.b64encode(csv_bytes).decode()

        config = {
            "target_table": "custom_rows",
            "column_map": {"event": "event", "user_id": "user_id"},
            "pending_bytes_b64": b64,
        }
        connector = await _make_connector_record(
            db_pool, org_a.org_id, type="csv_upload", segment="A", config=config
        )
        await sync_connector(db_pool, connector)

        # Sync should succeed with 0 rows
        async with db_pool.acquire() as conn:
            run = await conn.fetchrow(
                "SELECT status, rows_upserted FROM sync_runs WHERE connector_id = $1",
                connector["id"],
            )
        assert run["status"] == "success"
        assert run["rows_upserted"] == 0
