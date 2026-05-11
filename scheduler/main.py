"""
APScheduler polling loop for the analytics platform.

Runs two recurring jobs:
  1. connector_poll  — every 60 s: find connectors due for a sync, kick off tasks
  2. alert_eval      — every 60 s: evaluate all alert rules (staggered 30 s)

Orphan recovery on startup:
  Any sync_runs row with status='running' older than 5 minutes is considered
  a crashed run. We mark it 'failed' and reset the connector status to 'error'
  so the scheduler retries on the next poll.

No APScheduler job store: the connectors table IS the schedule. We query it
each tick to find connectors whose next-due time has elapsed. This avoids
the synchronous psycopg2 dependency that APScheduler's SQLAlchemyJobStore
would require (incompatible with our asyncpg setup).
"""

from __future__ import annotations

import asyncio
import logging
import os
import signal
from datetime import datetime, timedelta, timezone

import asyncpg
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.connectors.sync import sync_connector
from app.database import _init_connection  # JSONB codec registration

from .alert_evaluator import evaluate_alerts
from .digest import send_weekly_digest

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
)
logger = logging.getLogger(__name__)

_ORPHAN_THRESHOLD_MINUTES = 5
_POLL_INTERVAL_SECONDS = 60
_ALERT_INTERVAL_SECONDS = 60
_ALERT_STAGGER_SECONDS = 30  # start alert eval offset from connector poll


# ── orphan recovery ───────────────────────────────────────────────────────────

async def _recover_orphaned_runs(pool: asyncpg.Pool) -> None:
    """
    Mark sync_runs rows that are stuck in 'running' for > 5 minutes as
    'failed', and set the corresponding connector to status='error'.
    """
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute("SET LOCAL ROLE app_role")
            orphaned = await conn.fetch(
                """
                SELECT id, connector_id
                FROM   sync_runs
                WHERE  status     = 'running'
                  AND  started_at < NOW() - make_interval(mins => $1)
                """,
                _ORPHAN_THRESHOLD_MINUTES,
            )

    if not orphaned:
        logger.debug("No orphaned sync_runs found")
        return

    logger.warning("Recovering %d orphaned sync_run(s)", len(orphaned))
    for row in orphaned:
        async with pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute("SET LOCAL ROLE app_role")
                # Sequential — asyncpg does not allow concurrent ops on one connection
                await conn.execute(
                    """
                    UPDATE sync_runs
                    SET status        = 'failed',
                        finished_at   = NOW(),
                        error_message = 'Orphaned: scheduler restarted'
                    WHERE id = $1
                    """,
                    row["id"],
                )
                await conn.execute(
                    """
                    UPDATE connectors
                    SET status     = 'error',
                        last_error = 'Sync orphaned at scheduler restart'
                    WHERE id = $1
                    """,
                    row["connector_id"],
                )


# ── connector poll job ────────────────────────────────────────────────────────

async def _connector_poll(pool: asyncpg.Pool) -> None:
    """
    Query for connectors whose next sync is due, then fire each as an
    independent asyncio task (non-blocking — slow syncs don't delay others).

    A connector is "due" when:
      last_synced_at IS NULL  (never synced)
      OR last_synced_at + sync_interval_minutes <= NOW()

    Only active connectors are polled (not 'paused' or 'error').
    Push-based types (webhook, js_sdk) are excluded in sync_connector itself,
    but we also skip them here to avoid unnecessary task overhead.
    """
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute("SET LOCAL ROLE app_role")
            due = await conn.fetch(
                """
                SELECT id, org_id, type, segment, config,
                       sync_interval_minutes, status
                FROM   connectors
                WHERE  status  = 'active'
                  AND  type   IN ('sheets_csv', 'csv_upload')
                  AND  (
                      last_synced_at IS NULL
                      OR last_synced_at + make_interval(mins => sync_interval_minutes) <= NOW()
                  )
                """
            )

    if not due:
        logger.debug("connector_poll: no connectors due")
        return

    logger.info("connector_poll: %d connector(s) due for sync", len(due))
    for connector_row in due:
        asyncio.create_task(
            _safe_sync(pool, connector_row),
            name=f"sync-{connector_row['id']}",
        )


async def _safe_sync(pool: asyncpg.Pool, connector_row: asyncpg.Record) -> None:
    """Wrapper that catches and logs any unhandled exception from sync_connector."""
    try:
        await sync_connector(pool, connector_row)
    except Exception:  # noqa: BLE001
        logger.exception(
            "Unhandled exception in sync_connector for connector %s",
            connector_row["id"],
        )


# ── alert eval job ────────────────────────────────────────────────────────────

async def _alert_eval(pool: asyncpg.Pool) -> None:
    try:
        await evaluate_alerts(pool)
    except Exception:  # noqa: BLE001
        logger.exception("Unhandled exception in evaluate_alerts")


# ── entry point ───────────────────────────────────────────────────────────────

async def run_scheduler() -> None:  # pragma: no cover
    database_url = os.environ["DATABASE_URL"]

    # asyncpg requires postgresql:// scheme (not postgres://)
    dsn = database_url.replace("postgres://", "postgresql://", 1)

    pool = await asyncpg.create_pool(
        dsn=dsn,
        min_size=2,
        max_size=10,
        init=_init_connection,  # registers JSONB codec so config comes back as dict not string
    )
    logger.info("Database pool created")

    # Orphan recovery before the first poll
    await _recover_orphaned_runs(pool)

    scheduler = AsyncIOScheduler()

    now_utc = datetime.now(timezone.utc)

    # Connector poll: every 60 s, starting immediately
    scheduler.add_job(
        _connector_poll,
        "interval",
        seconds=_POLL_INTERVAL_SECONDS,
        args=[pool],
        id="connector_poll",
        next_run_time=now_utc,
    )

    # Alert eval: every 60 s, staggered 30 s after connector poll so that
    # a sync that completes just before the poll boundary is reflected in
    # the first alert evaluation after it.
    scheduler.add_job(
        _alert_eval,
        "interval",
        seconds=_ALERT_INTERVAL_SECONDS,
        args=[pool],
        id="alert_eval",
        next_run_time=now_utc + timedelta(seconds=_ALERT_STAGGER_SECONDS),
    )

    # Weekly digest: every Monday at 09:00 UTC.
    # Sends a plain-text + HTML summary of the past 7 days to each org's
    # admin email. Skipped gracefully when SMTP_HOST is not configured.
    scheduler.add_job(
        send_weekly_digest,
        "cron",
        day_of_week="mon",
        hour=9,
        minute=0,
        args=[pool],
        id="weekly_digest",
        timezone="UTC",
    )

    scheduler.start()
    logger.info(
        "Scheduler started (connector_poll every %ds, alert_eval every %ds)",
        _POLL_INTERVAL_SECONDS,
        _ALERT_INTERVAL_SECONDS,
    )

    # Graceful shutdown on SIGTERM / SIGINT
    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()

    def _handle_signal() -> None:
        logger.info("Shutdown signal received")
        stop_event.set()

    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, _handle_signal)

    await stop_event.wait()

    logger.info("Shutting down scheduler...")
    scheduler.shutdown(wait=True)
    await pool.close()
    logger.info("Scheduler stopped cleanly")


def main() -> None:  # pragma: no cover
    asyncio.run(run_scheduler())


if __name__ == "__main__":  # pragma: no cover
    main()
