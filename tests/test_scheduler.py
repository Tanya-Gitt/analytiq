"""
Tests for scheduler/main.py — orphan recovery and connector poll logic.

Coverage:
  - _recover_orphaned_runs: marks old 'running' sync_runs as 'failed' and
    resets connector status to 'error'.
  - _recover_orphaned_runs: ignores fresh 'running' runs (< 5 min old).
  - _recover_orphaned_runs: no-ops when there are no running rows.
  - _connector_poll: fires sync tasks for overdue connectors.
  - _connector_poll: does NOT fire for paused or error-state connectors.
  - _connector_poll: does NOT fire for push-based connectors (webhook, js_sdk).
  - _connector_poll: does NOT fire if connector is not yet due.
  - _safe_sync: logs but does not re-raise exceptions from sync_connector.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import asyncpg
import pytest

from scheduler.main import (
    _connector_poll,
    _recover_orphaned_runs,
    _safe_sync,
)

# ── helpers ────────────────────────────────────────────────────────────────────

async def _create_connector(
    pool: asyncpg.Pool,
    org_id: str,
    *,
    conn_type: str = "csv_upload",
    segment: str = "B",
    status: str = "active",
    sync_interval_minutes: int = 60,
    last_synced_at=None,
) -> str:
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(f"SET LOCAL app.org_id = '{org_id}'")
            connector_id = await conn.fetchval(
                """
                INSERT INTO connectors
                    (org_id, name, type, segment, status,
                     sync_interval_minutes, last_synced_at, config)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                RETURNING id
                """,
                org_id,
                f"test {conn_type}",
                conn_type,
                segment,
                status,
                sync_interval_minutes,
                last_synced_at,
                {},
            )
    return str(connector_id)


async def _create_sync_run(
    pool: asyncpg.Pool,
    connector_id: str,
    org_id: str,
    *,
    status: str = "running",
    started_at=None,
) -> str:
    if started_at is None:
        started_at = datetime.now(timezone.utc)
    async with pool.acquire() as conn:
        run_id = await conn.fetchval(
            """
            INSERT INTO sync_runs (connector_id, org_id, status, started_at)
            VALUES ($1, $2::uuid, $3, $4)
            RETURNING id
            """,
            connector_id,
            org_id,
            status,
            started_at,
        )
    return str(run_id)


async def _get_connector_status(pool: asyncpg.Pool, connector_id: str) -> str:
    async with pool.acquire() as conn:
        return await conn.fetchval(
            "SELECT status FROM connectors WHERE id = $1", connector_id
        )


async def _get_run_status(pool: asyncpg.Pool, run_id: str) -> str:
    async with pool.acquire() as conn:
        return await conn.fetchval(
            "SELECT status FROM sync_runs WHERE id = $1", int(run_id)
        )


# ── orphan recovery ────────────────────────────────────────────────────────────

class TestRecoverOrphanedRuns:
    @pytest.mark.asyncio
    async def test_old_running_run_marked_failed(self, db_pool, org_a):
        """A 'running' sync_run older than 5 min must become 'failed'."""
        connector_id = await _create_connector(db_pool, org_a.org_id)
        old_start = datetime.now(timezone.utc) - timedelta(minutes=10)
        run_id = await _create_sync_run(
            db_pool, connector_id, org_a.org_id, status="running", started_at=old_start
        )

        await _recover_orphaned_runs(db_pool)

        assert await _get_run_status(db_pool, run_id) == "failed"

    @pytest.mark.asyncio
    async def test_old_orphan_sets_connector_to_error(self, db_pool, org_a):
        """After orphan recovery the connector itself must show status='error'."""
        connector_id = await _create_connector(db_pool, org_a.org_id)
        old_start = datetime.now(timezone.utc) - timedelta(minutes=6)
        await _create_sync_run(
            db_pool, connector_id, org_a.org_id, status="running", started_at=old_start
        )

        await _recover_orphaned_runs(db_pool)

        assert await _get_connector_status(db_pool, connector_id) == "error"

    @pytest.mark.asyncio
    async def test_fresh_running_run_left_alone(self, db_pool, org_a):
        """A 'running' run started < 5 min ago must NOT be touched."""
        connector_id = await _create_connector(db_pool, org_a.org_id)
        fresh_start = datetime.now(timezone.utc) - timedelta(minutes=2)
        run_id = await _create_sync_run(
            db_pool, connector_id, org_a.org_id, status="running", started_at=fresh_start
        )

        await _recover_orphaned_runs(db_pool)

        # Still running — not touched
        assert await _get_run_status(db_pool, run_id) == "running"
        assert await _get_connector_status(db_pool, connector_id) == "active"

    @pytest.mark.asyncio
    async def test_no_running_rows_is_noop(self, db_pool, org_a):
        """When there are no 'running' rows, recovery must not raise or change anything."""
        connector_id = await _create_connector(db_pool, org_a.org_id)
        run_id = await _create_sync_run(
            db_pool, connector_id, org_a.org_id, status="success",
            started_at=datetime.now(timezone.utc) - timedelta(hours=2),
        )

        await _recover_orphaned_runs(db_pool)

        # Completed run untouched
        assert await _get_run_status(db_pool, run_id) == "success"
        assert await _get_connector_status(db_pool, connector_id) == "active"

    @pytest.mark.asyncio
    async def test_orphan_error_message_set(self, db_pool, org_a):
        """The failed run must have an error_message set by recovery."""
        connector_id = await _create_connector(db_pool, org_a.org_id)
        old_start = datetime.now(timezone.utc) - timedelta(minutes=10)
        run_id = await _create_sync_run(
            db_pool, connector_id, org_a.org_id, status="running", started_at=old_start
        )

        await _recover_orphaned_runs(db_pool)

        async with db_pool.acquire() as conn:
            error_msg = await conn.fetchval(
                "SELECT error_message FROM sync_runs WHERE id = $1", int(run_id)
            )
        assert error_msg is not None
        assert len(error_msg) > 0


# ── connector poll ─────────────────────────────────────────────────────────────

class TestConnectorPoll:
    @pytest.mark.asyncio
    async def test_overdue_connector_gets_synced(self, db_pool, org_a):
        """An active connector with last_synced_at > interval ago must trigger a sync."""
        old_sync = datetime.now(timezone.utc) - timedelta(hours=2)
        connector_id = await _create_connector(
            db_pool, org_a.org_id,
            sync_interval_minutes=60,
            last_synced_at=old_sync,
        )

        synced_ids: list[str] = []

        async def _fake_sync(pool, connector_row):
            synced_ids.append(str(connector_row["id"]))

        with patch("scheduler.main.sync_connector", side_effect=_fake_sync):
            await _connector_poll(db_pool)
            # Allow any spawned tasks to run
            await asyncio.sleep(0.05)

        assert connector_id in synced_ids

    @pytest.mark.asyncio
    async def test_never_synced_connector_gets_synced(self, db_pool, org_a):
        """A connector with last_synced_at=NULL (never synced) is always due."""
        connector_id = await _create_connector(
            db_pool, org_a.org_id,
            sync_interval_minutes=60,
            last_synced_at=None,
        )

        synced_ids: list[str] = []

        async def _fake_sync(pool, connector_row):
            synced_ids.append(str(connector_row["id"]))

        with patch("scheduler.main.sync_connector", side_effect=_fake_sync):
            await _connector_poll(db_pool)
            await asyncio.sleep(0.05)

        assert connector_id in synced_ids

    @pytest.mark.asyncio
    async def test_recently_synced_connector_skipped(self, db_pool, org_a):
        """A connector synced 1 minute ago with 60 min interval must NOT trigger."""
        recent_sync = datetime.now(timezone.utc) - timedelta(minutes=1)
        await _create_connector(
            db_pool, org_a.org_id,
            sync_interval_minutes=60,
            last_synced_at=recent_sync,
        )

        synced_ids: list[str] = []

        async def _fake_sync(pool, connector_row):
            synced_ids.append(str(connector_row["id"]))

        with patch("scheduler.main.sync_connector", side_effect=_fake_sync):
            await _connector_poll(db_pool)
            await asyncio.sleep(0.05)

        assert len(synced_ids) == 0

    @pytest.mark.asyncio
    async def test_paused_connector_skipped(self, db_pool, org_a):
        """Connectors with status='paused' must not be polled."""
        await _create_connector(
            db_pool, org_a.org_id,
            status="paused",
            last_synced_at=None,
        )

        synced_ids: list[str] = []

        async def _fake_sync(pool, connector_row):
            synced_ids.append(str(connector_row["id"]))

        with patch("scheduler.main.sync_connector", side_effect=_fake_sync):
            await _connector_poll(db_pool)
            await asyncio.sleep(0.05)

        assert len(synced_ids) == 0

    @pytest.mark.asyncio
    async def test_error_status_connector_skipped(self, db_pool, org_a):
        """Connectors with status='error' must not be polled."""
        await _create_connector(
            db_pool, org_a.org_id,
            status="error",
            last_synced_at=None,
        )

        synced_ids: list[str] = []

        async def _fake_sync(pool, connector_row):
            synced_ids.append(str(connector_row["id"]))

        with patch("scheduler.main.sync_connector", side_effect=_fake_sync):
            await _connector_poll(db_pool)
            await asyncio.sleep(0.05)

        assert len(synced_ids) == 0

    @pytest.mark.asyncio
    async def test_webhook_connector_skipped(self, db_pool, org_a):
        """Push-based webhook connectors must NOT be included in the poll query."""
        await _create_connector(
            db_pool, org_a.org_id,
            conn_type="webhook",
            segment="B",
            last_synced_at=None,
        )

        synced_ids: list[str] = []

        async def _fake_sync(pool, connector_row):
            synced_ids.append(str(connector_row["id"]))

        with patch("scheduler.main.sync_connector", side_effect=_fake_sync):
            await _connector_poll(db_pool)
            await asyncio.sleep(0.05)

        assert len(synced_ids) == 0

    @pytest.mark.asyncio
    async def test_js_sdk_connector_skipped(self, db_pool, org_a):
        """Push-based js_sdk connectors must NOT be included in the poll query."""
        await _create_connector(
            db_pool, org_a.org_id,
            conn_type="js_sdk",
            segment="A",
            last_synced_at=None,
        )

        synced_ids: list[str] = []

        async def _fake_sync(pool, connector_row):
            synced_ids.append(str(connector_row["id"]))

        with patch("scheduler.main.sync_connector", side_effect=_fake_sync):
            await _connector_poll(db_pool)
            await asyncio.sleep(0.05)

        assert len(synced_ids) == 0


# ── _safe_sync exception swallowing ───────────────────────────────────────────

class TestSafeSync:
    @pytest.mark.asyncio
    async def test_exception_is_logged_not_raised(self, db_pool, org_a):
        """
        _safe_sync must swallow any exception from sync_connector so that
        one failing connector cannot crash the scheduler task loop.
        """
        connector_id = await _create_connector(db_pool, org_a.org_id)

        # Build a minimal asyncpg.Record-like dict
        class FakeRecord(dict):
            def __getitem__(self, key):
                return super().__getitem__(key)

        fake_row = FakeRecord({
            "id": connector_id,
            "org_id": org_a.org_id,
            "type": "csv_upload",
            "segment": "B",
            "config": {},
            "status": "active",
            "sync_interval_minutes": 60,
        })

        async def _exploding_sync(pool, row):
            raise RuntimeError("boom — simulated crash")

        # Must not raise
        with patch("scheduler.main.sync_connector", side_effect=_exploding_sync):
            await _safe_sync(db_pool, fake_row)  # should NOT raise

    @pytest.mark.asyncio
    async def test_successful_sync_does_not_raise(self, db_pool, org_a):
        """Happy-path: _safe_sync completes without error for a clean sync."""
        connector_id = await _create_connector(db_pool, org_a.org_id)

        class FakeRecord(dict):
            def __getitem__(self, key):
                return super().__getitem__(key)

        fake_row = FakeRecord({
            "id": connector_id,
            "org_id": org_a.org_id,
            "type": "csv_upload",
            "segment": "B",
            "config": {},
            "status": "active",
            "sync_interval_minutes": 60,
        })

        call_count = 0

        async def _ok_sync(pool, row):
            nonlocal call_count
            call_count += 1

        with patch("scheduler.main.sync_connector", side_effect=_ok_sync):
            await _safe_sync(db_pool, fake_row)

        assert call_count == 1
