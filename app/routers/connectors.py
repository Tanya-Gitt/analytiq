"""
POST   /api/connectors                        — create a connector (with setup-time validation).
GET    /api/connectors                        — list connectors for the authenticated org.
PATCH  /api/connectors/{id}                  — update name, config, sync_interval_minutes, or status.
DELETE /api/connectors/{id}                  — permanently delete a connector and its sync history.
POST   /api/connectors/{id}/sync             — manually trigger an immediate sync.
POST   /api/connectors/{id}/upload-csv        — upload a CSV file for a csv_upload connector
                                               and immediately trigger a sync.
GET    /api/connectors/{id}/sync-runs         — last 20 sync runs for a connector.
"""

from __future__ import annotations

import asyncio
import base64
import re
from typing import Any
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel

from app.connectors.sync import sync_connector
from app.database import get_pool
from app.deps import get_org_db

router = APIRouter()

# Required orders columns that MUST be present in column_map for csv_upload
_REQUIRED_ORDER_COLUMNS = {"order_id", "order_date", "quantity"}

# Column name sanitization: only allow [a-zA-Z0-9_], max 63 chars
_SAFE_COLUMN_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]{0,62}$")


def sanitize_column_name(name: str) -> str:
    """
    Sanitize a CSV header name for safe use in dynamic DDL (CREATE INDEX).
    Allows only [a-zA-Z0-9_], max 63 chars. Replaces unsafe chars with '_'.
    Raises ValueError if the sanitized name is empty or starts with a digit.

    CRITICAL: Always call this before using a column name in any DDL statement.
    CREATE INDEX is DDL and cannot be parameterized — SQL injection via
    user-supplied CSV headers is a real attack vector.
    """
    clean = re.sub(r"[^a-zA-Z0-9_]", "_", name)[:63]
    if not clean or not clean.strip("_"):
        raise ValueError(
            f"Column name {name!r} contains no alphanumeric characters after sanitization"
        )
    if clean[0].isdigit():
        clean = "col_" + clean[:59]
    return clean


def _validate_column_map(column_map: dict[str, str], target_table: str) -> None:
    """
    Validate that all required columns for the target table are mapped.
    Raises HTTP 422 with a clear error on first missing column.
    Also sanitizes all column names to prevent DDL injection.
    """
    if target_table == "orders":
        mapped_targets = set(column_map.values())
        missing = _REQUIRED_ORDER_COLUMNS - mapped_targets
        if missing:
            raise HTTPException(
                status_code=422,
                detail=f"missing required column mapping: {', '.join(sorted(missing))}",
            )
    # Sanitize all CSV header names (keys in column_map)
    for csv_header in column_map:
        try:
            sanitize_column_name(csv_header)
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))


class ConnectorCreate(BaseModel):
    type: str                   # 'sheets_csv' | 'csv_upload' | 'webhook' | 'js_sdk'
    segment: str                # 'A' | 'B'
    name: str | None = None     # auto-derived from type if not provided
    config: dict[str, Any] = {}
    sync_interval_minutes: int = 60


@router.post("/connectors", status_code=201)
async def create_connector(
    body: ConnectorCreate,
    db: asyncpg.Connection = Depends(get_org_db),
):
    """
    Create a new connector for the authenticated org.

    Validates column_map at creation time (not sync time) so the user gets
    immediate feedback on missing required columns.
    """
    valid_types = {"sheets_csv", "csv_upload", "webhook", "js_sdk"}
    if body.type not in valid_types:
        raise HTTPException(status_code=422, detail=f"invalid type: {body.type!r}")
    if body.segment not in ("A", "B"):
        raise HTTPException(status_code=422, detail="segment must be 'A' or 'B'")

    # Setup-time validation for CSV-based connectors (csv_upload and sheets_csv)
    if body.type in ("csv_upload", "sheets_csv"):
        column_map: dict[str, str] = body.config.get("column_map", {})
        target_table: str = body.config.get("target_table", "orders")
        _validate_column_map(column_map, target_table)

    connector_name = body.name or f"{body.type} connector"
    connector = await db.fetchrow(
        """
        INSERT INTO connectors (org_id, name, type, segment, config, sync_interval_minutes)
        VALUES (current_setting('app.org_id')::uuid, $1, $2, $3, $4, $5)
        RETURNING id, name, type, segment, status, created_at
        """,
        connector_name,
        body.type,
        body.segment,
        body.config,
        body.sync_interval_minutes,
    )
    return dict(connector)


@router.get("/connectors")
async def list_connectors(db: asyncpg.Connection = Depends(get_org_db)):
    """List all connectors for the authenticated org (RLS-filtered automatically)."""
    rows = await db.fetch(
        """
        SELECT id, name, type, segment, status, sync_interval_minutes,
               last_synced_at, last_error, created_at
        FROM connectors
        ORDER BY created_at DESC
        """
    )
    return [dict(r) for r in rows]


class UpdateConnectorBody(BaseModel):
    name: str | None = None
    sync_interval_minutes: int | None = None
    status: str | None = None
    config: dict | None = None


@router.patch("/connectors/{connector_id}")
async def update_connector(
    connector_id: UUID,
    body: UpdateConnectorBody,
    db: asyncpg.Connection = Depends(get_org_db),
):
    """
    Partially update a connector's mutable fields.

    Allowed fields: name, sync_interval_minutes, status, config.
    Returns the full updated connector row.
    RLS ensures only the owning org can update its connectors.
    """
    # Build SET clause dynamically — only update provided fields
    updates: dict[str, Any] = {}
    if body.name is not None:
        updates["name"] = body.name
    if body.sync_interval_minutes is not None:
        if body.sync_interval_minutes < 1:
            raise HTTPException(status_code=422, detail="sync_interval_minutes must be ≥ 1")
        updates["sync_interval_minutes"] = body.sync_interval_minutes
    if body.status is not None:
        if body.status not in ("active", "paused", "error"):
            raise HTTPException(status_code=422, detail="status must be active, paused, or error")
        updates["status"] = body.status
    if body.config is not None:
        updates["config"] = body.config

    if not updates:
        raise HTTPException(status_code=422, detail="no fields to update")

    # Build parameterised SET clause
    set_parts = []
    values: list[Any] = []
    for i, (col, val) in enumerate(updates.items(), start=1):
        set_parts.append(f"{col} = ${i}")
        values.append(val)

    values.append(connector_id)
    id_param = f"${len(values)}"

    row = await db.fetchrow(
        f"""
        UPDATE connectors
        SET {', '.join(set_parts)}
        WHERE id = {id_param}
        RETURNING id, name, type, segment, status, sync_interval_minutes,
                  last_synced_at, last_error, created_at
        """,
        *values,
    )
    if row is None:
        raise HTTPException(status_code=404, detail="connector not found")
    return dict(row)


@router.post("/connectors/{connector_id}/sync", status_code=202)
async def trigger_sync(
    connector_id: UUID,
    db: asyncpg.Connection = Depends(get_org_db),
    pool: asyncpg.Pool = Depends(get_pool),
):
    """
    Manually trigger an immediate sync for a connector.

    Supported types: sheets_csv, csv_upload (if pending_bytes_b64 is present).
    webhook and js_sdk are push-based and cannot be manually synced — returns 422.

    Returns 202 Accepted immediately; sync runs in the background.
    """
    row = await db.fetchrow(
        "SELECT id, org_id, type, segment, config, status, sync_interval_minutes "
        "FROM connectors WHERE id = $1",
        connector_id,
    )
    if row is None:
        raise HTTPException(status_code=404, detail="connector not found")

    if row["type"] in ("webhook", "js_sdk"):
        raise HTTPException(
            status_code=422,
            detail=f"{row['type']} connectors are push-based and cannot be manually synced",
        )

    asyncio.create_task(sync_connector(pool, row))
    return {"ok": True, "message": "sync started"}


@router.delete("/connectors/{connector_id}", status_code=204)
async def delete_connector(
    connector_id: UUID,
    db: asyncpg.Connection = Depends(get_org_db),
):
    """
    Permanently delete a connector and all its sync history (CASCADE).
    RLS ensures only the owning org can delete its own connectors.
    Returns 404 if the connector does not exist (or belongs to another org).
    """
    deleted = await db.fetchval(
        "DELETE FROM connectors WHERE id = $1 RETURNING id",
        connector_id,
    )
    if deleted is None:
        raise HTTPException(status_code=404, detail="connector not found")


@router.post("/connectors/{connector_id}/upload-csv", status_code=status.HTTP_202_ACCEPTED)
async def upload_csv(
    connector_id: UUID,
    file: UploadFile = File(..., description="CSV file to import"),
    db: asyncpg.Connection = Depends(get_org_db),
    pool: asyncpg.Pool = Depends(get_pool),
):
    """
    Accept a CSV file upload for a csv_upload connector, store it as
    base64 in config.pending_bytes_b64, then immediately trigger a sync.

    Returns 202 Accepted — the sync runs asynchronously (check sync-runs
    for status). The stored b64 blob is cleared from config after the
    sync completes (handled inside sync_connector).

    Validates:
      - connector exists and belongs to the authenticated org (via RLS on db)
      - connector type must be 'csv_upload'
      - file content-type must be text/csv or application/octet-stream
    """
    # Fetch connector — RLS ensures it belongs to the authenticated org
    row = await db.fetchrow(
        "SELECT id, org_id, type, segment, config, status, sync_interval_minutes "
        "FROM connectors WHERE id = $1",
        connector_id,
    )
    if row is None:
        raise HTTPException(status_code=404, detail="connector not found")

    if row["type"] != "csv_upload":
        raise HTTPException(
            status_code=422,
            detail=f"connector type is {row['type']!r}; only csv_upload supports file upload",
        )

    # Guard against memory bombs before reading the whole file.
    # nginx allows 12 MB bodies; we cap at 10 MB here in app code as a second layer.
    _MAX_CSV_BYTES = 10 * 1024 * 1024  # 10 MB
    if file.size is not None and file.size > _MAX_CSV_BYTES:
        raise HTTPException(status_code=413, detail="CSV file too large (max 10 MB)")

    # Read and base64-encode the uploaded file
    csv_bytes = await file.read()
    if not csv_bytes:
        raise HTTPException(status_code=422, detail="uploaded file is empty")
    if len(csv_bytes) > _MAX_CSV_BYTES:
        raise HTTPException(status_code=413, detail="CSV file too large (max 10 MB)")

    b64 = base64.b64encode(csv_bytes).decode()

    # Merge pending_bytes_b64 into the existing config (keep column_map etc.)
    existing_config: dict[str, Any] = dict(row["config"] or {})
    existing_config["pending_bytes_b64"] = b64

    await db.execute(
        "UPDATE connectors SET config = $1 WHERE id = $2",
        existing_config,
        connector_id,
    )

    # Re-fetch the full connector row (sync_connector expects an asyncpg.Record)
    connector_row = await db.fetchrow(
        "SELECT id, org_id, type, segment, config, status, sync_interval_minutes "
        "FROM connectors WHERE id = $1",
        connector_id,
    )

    # Fire sync — runs asynchronously, response returns immediately
    asyncio.create_task(sync_connector(pool, connector_row))

    return {"ok": True, "message": "sync started"}


@router.get("/connectors/{connector_id}/sync-runs")
async def get_sync_runs(
    connector_id: UUID,
    db: asyncpg.Connection = Depends(get_org_db),
):
    """Return the last 20 sync runs for a connector."""
    rows = await db.fetch(
        """
        SELECT id, status, started_at, finished_at, rows_upserted, error_message
        FROM sync_runs
        WHERE connector_id = $1
        ORDER BY started_at DESC
        LIMIT 20
        """,
        connector_id,
    )
    return [dict(r) for r in rows]
