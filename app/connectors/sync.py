"""
Connector sync logic for Segment B connectors.

sync_connector(pool, connector_row) → None

Handles:
  - sheets_csv  : fetch CSV from URL in config["url"], parse, upsert into orders
  - csv_upload  : CSV bytes already stored in config["pending_bytes_b64"], parse, upsert
  - webhook     : no-op (webhook ingest is push-based, no polling needed)
  - js_sdk      : no-op (event ingest is push-based)

Updates connectors.last_synced_at / last_error and writes a sync_runs row.
"""

from __future__ import annotations

import base64
import logging
from typing import Any
from urllib.parse import urlparse

import asyncpg
import httpx

from app.routers.dashboard import invalidate_org_cache

from .coerce import parse_csv_rows

logger = logging.getLogger(__name__)

# ── upsert helpers ────────────────────────────────────────────────────────────

_ORDERS_COLUMNS = [
    "order_id", "order_date", "customer_id", "product_id", "product_name",
    "channel", "quantity", "price_per_unit", "cost_per_unit", "delivered",
    "delivery_time_minutes", "region", "promo_used", "acquisition_source",
]


async def _upsert_orders(
    conn: asyncpg.Connection,
    org_id: str,
    rows: list[dict[str, Any]],
) -> int:
    """
    Bulk-upsert coerced order rows into the orders table.
    Returns the number of rows upserted.

    ON CONFLICT (org_id, order_id) DO UPDATE — idempotent re-runs.
    """
    if not rows:
        return 0

    # Build the column list from what's actually present (union of all row keys)
    cols_present: set[str] = set()
    for row in rows:
        cols_present.update(row.keys())
    # Keep canonical order; only include columns that exist in the schema
    insert_cols = [c for c in _ORDERS_COLUMNS if c in cols_present]

    col_list = ", ".join(insert_cols)
    update_set = ", ".join(
        f"{c} = EXCLUDED.{c}"
        for c in insert_cols
        if c != "order_id"  # don't overwrite the conflict key itself
    )

    # Build value rows as tuples
    records = []
    for row in rows:
        record = tuple(row.get(c) for c in insert_cols)
        records.append(record)

    # Parameterized bulk insert via executemany
    placeholders = ", ".join(f"${i + 2}" for i in range(len(insert_cols)))
    sql = f"""
        INSERT INTO orders (org_id, {col_list})
        VALUES ($1, {placeholders})
        ON CONFLICT (org_id, order_id) DO UPDATE
        SET {update_set}
    """

    await conn.executemany(sql, [
        (org_id, *record) for record in records
    ])
    return len(records)


async def _upsert_custom_rows(
    conn: asyncpg.Connection,
    org_id: str,
    connector_id: str,
    rows: list[dict[str, Any]],
) -> int:
    """
    Insert coerced rows into custom_rows as JSONB.
    Uses INSERT … ON CONFLICT DO NOTHING (no natural key for generic rows).
    Deduplication relies on GIN index queries at read time.
    """
    if not rows:
        return 0

    await conn.executemany(
        """
        INSERT INTO custom_rows (org_id, connector_id, row_data)
        VALUES ($1, $2, $3::jsonb)
        """,
        [(org_id, connector_id, row) for row in rows],
    )
    return len(rows)


# ── sync_connector ────────────────────────────────────────────────────────────

async def sync_connector(
    pool: asyncpg.Pool,
    connector_row: asyncpg.Record,
) -> None:
    """
    Entry point called by the scheduler for each due connector.

    connector_row must have: id, org_id, type, segment, config, status.

    Flow:
    1. Insert sync_runs row with status='running'.
    2. Fetch / parse CSV bytes.
    3. Coerce rows and upsert into appropriate table.
    4. Update sync_runs → 'success' + connectors.last_synced_at.
    On any error: update sync_runs → 'failed' + connectors.last_error.
    """
    connector_id: str = str(connector_row["id"])
    org_id: str = str(connector_row["org_id"])
    connector_type: str = connector_row["type"]
    segment: str = connector_row["segment"]
    config: dict[str, Any] = connector_row["config"] or {}

    # Push-based connectors: nothing to do on the polling path
    if connector_type in ("webhook", "js_sdk"):
        logger.debug("connector %s is push-based, skipping poll", connector_id)
        return

    # ── 1. create sync_runs record ─────────────────────────────────────────
    async with pool.acquire() as conn:
        run_id: int = await conn.fetchval(
            """
            INSERT INTO sync_runs (connector_id, org_id, status)
            VALUES ($1, $2, 'running')
            RETURNING id
            """,
            connector_id,
            org_id,
        )

    try:
        # ── 2. fetch CSV bytes ─────────────────────────────────────────────
        csv_bytes = await _fetch_csv(connector_type, config)

        # ── 3. parse + coerce ──────────────────────────────────────────────
        column_map: dict[str, str] = config.get("column_map", {})
        target_table: str = config.get("target_table", "orders")

        rows = parse_csv_rows(csv_bytes, column_map)
        logger.info(
            "connector %s parsed %d rows from CSV (target=%s)",
            connector_id, len(rows), target_table,
        )

        # ── 4. upsert ─────────────────────────────────────────────────────
        async with pool.acquire() as conn:
            # RLS: set org context for this connection
            async with conn.transaction():
                await conn.execute(f"SET LOCAL app.org_id = '{str(org_id)}'")

                if target_table == "orders" and segment == "B":
                    rows_upserted = await _upsert_orders(conn, org_id, rows)
                else:
                    # Segment A or custom target → custom_rows JSONB store
                    rows_upserted = await _upsert_custom_rows(
                        conn, org_id, connector_id, rows
                    )

                # Update connector metadata inside same transaction
                await conn.execute(
                    """
                    UPDATE connectors
                    SET last_synced_at = NOW(),
                        last_error     = NULL,
                        status         = 'active'
                    WHERE id = $1
                    """,
                    connector_id,
                )

        # ── 5. mark sync_run success ───────────────────────────────────────
        async with pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE sync_runs
                SET status        = 'success',
                    finished_at   = NOW(),
                    rows_upserted = $2
                WHERE id = $1
                """,
                run_id,
                rows_upserted,
            )

        # Bust cached dashboard data so the next request reflects the new rows.
        invalidate_org_cache(org_id)

        logger.info(
            "connector %s sync complete: %d rows upserted", connector_id, rows_upserted
        )

    except Exception as exc:  # noqa: BLE001
        error_msg = str(exc)[:500]  # truncate to fit column
        logger.exception("connector %s sync failed: %s", connector_id, error_msg)

        async with pool.acquire() as conn:
            # Sequential — asyncpg connections are not concurrent-safe
            await conn.execute(
                """
                UPDATE sync_runs
                SET status        = 'failed',
                    finished_at   = NOW(),
                    error_message = $2
                WHERE id = $1
                """,
                run_id,
                error_msg,
            )
            await conn.execute(
                """
                UPDATE connectors
                SET last_error = $2,
                    status     = 'error'
                WHERE id = $1
                """,
                connector_id,
                error_msg,
            )


# ── CSV fetch strategies ──────────────────────────────────────────────────────

def _validate_sheets_url(url: str) -> None:
    """
    SECURITY: Prevent SSRF by validating that sheets_csv URLs are public HTTP(S) only.

    Rejects:
      - Non-http(s) schemes (file://, ftp://, etc.)
      - Internal hostnames (localhost, *.internal, Docker service names like postgres/app/nginx)
      - Private IP ranges (10.x, 172.16-31.x, 192.168.x, 127.x)
    """
    try:
        parsed = urlparse(url)
    except Exception:
        raise ValueError("Invalid URL format")

    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"URL scheme {parsed.scheme!r} not allowed; use http or https")

    host = (parsed.hostname or "").lower().strip(".")
    if not host:
        raise ValueError("URL has no hostname")

    # Block loopback / localhost
    if host in ("localhost", "127.0.0.1", "::1", "0.0.0.0"):
        raise ValueError("URL hostname is not allowed (loopback address)")

    # Block common Docker-internal service names
    _BLOCKED_HOSTS = {"postgres", "app", "nginx", "auth", "scheduler", "frontend"}
    if host in _BLOCKED_HOSTS:
        raise ValueError(f"URL hostname {host!r} is not allowed (internal service name)")

    # Block .local / .internal TLDs
    if host.endswith((".local", ".internal", ".localdomain")):
        raise ValueError(f"URL hostname {host!r} is not allowed (private TLD)")

    # Block RFC-1918 private IP ranges
    import ipaddress
    try:
        addr = ipaddress.ip_address(host)
        if addr.is_private or addr.is_loopback or addr.is_link_local:
            raise ValueError(f"URL hostname {host!r} resolves to a private IP range")
    except ValueError as e:
        if "private IP" in str(e) or "private range" in str(e) or "loopback" in str(e):
            raise
        # Not an IP address — that's fine, hostname validation above already ran


async def _fetch_csv(connector_type: str, config: dict[str, Any]) -> bytes:
    """
    Return raw CSV bytes depending on connector type.

    sheets_csv  : HTTP GET config["url"] with a 30s timeout.
    csv_upload  : base64-decode config["pending_bytes_b64"].
    """
    if connector_type == "sheets_csv":
        url = config.get("url")
        if not url:
            raise ValueError("sheets_csv connector missing config.url")

        # SECURITY: validate URL before fetching to prevent SSRF
        _validate_sheets_url(url)

        async with httpx.AsyncClient(timeout=30.0, follow_redirects=False) as client:
            resp = await client.get(url)
            if resp.status_code != 200:
                raise ValueError(
                    f"CSV fetch failed: HTTP {resp.status_code} from {url!r}"
                )
            return resp.content

    if connector_type == "csv_upload":
        b64 = config.get("pending_bytes_b64")
        if not b64:
            raise ValueError("csv_upload connector missing config.pending_bytes_b64")
        try:
            return base64.b64decode(b64)
        except Exception as exc:
            raise ValueError(f"csv_upload: invalid base64 in pending_bytes_b64: {exc}") from exc

    raise ValueError(f"Unknown connector type for CSV fetch: {connector_type!r}")
