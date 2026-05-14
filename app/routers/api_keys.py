"""
Scoped API Keys — create, list, revoke keys with granular scopes.

GET    /api/api-keys           — list keys (prefix + metadata, no full key)
POST   /api/api-keys           — create key (returns full key ONCE)
GET    /api/api-keys/{key_id}  — get single key metadata
DELETE /api/api-keys/{key_id}  — revoke key
"""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

import asyncpg
import bcrypt
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from app.database import get_pool
from app.deps import get_org_db, require_admin

router = APIRouter()

VALID_SCOPES = frozenset({"ingest", "read", "admin"})


# ── Models ────────────────────────────────────────────────────────────────────

class CreateKeyRequest(BaseModel):
    name:         str = Field(..., min_length=1, max_length=80)
    scopes:       list[str] = ["read"]
    expires_days: int | None = Field(None, ge=1, le=3650)

    def validate_scopes(self) -> list[str]:
        invalid = set(self.scopes) - VALID_SCOPES
        if invalid:
            raise ValueError(f"Invalid scopes: {invalid}")
        return self.scopes


def _fmt_key(row: asyncpg.Record, raw_key: str | None = None) -> dict[str, Any]:
    d = {
        "id":           str(row["id"]),
        "name":         row["name"],
        "prefix":       f"sk_{row['key_prefix']}…",
        "scopes":       list(row["scopes"]),
        "revoked":      row["revoked"],
        "created_at":   row["created_at"].isoformat(),
        "last_used_at": row["last_used_at"].isoformat() if row["last_used_at"] else None,
        "expires_at":   row["expires_at"].isoformat() if row["expires_at"] else None,
    }
    if raw_key:
        d["key"] = raw_key  # only included on creation
    return d


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/api-keys")
async def list_keys(
    db: asyncpg.Connection = Depends(get_org_db),
):
    rows = await db.fetch(
        "SELECT * FROM api_keys WHERE revoked = false ORDER BY created_at DESC"
    )
    return [_fmt_key(r) for r in rows]


@router.post("/api-keys", status_code=201)
async def create_key(
    body:         CreateKeyRequest,
    db:           asyncpg.Connection = Depends(get_org_db),
    current_user: dict = Depends(require_admin),
):
    for scope in body.scopes:
        if scope not in VALID_SCOPES:
            raise HTTPException(400, f"Invalid scope: {scope!r}. Valid: {sorted(VALID_SCOPES)}")

    raw_key    = secrets.token_hex(32)          # 64-char hex key
    key_prefix = raw_key[:8]
    key_hash   = bcrypt.hashpw(raw_key.encode(), bcrypt.gensalt()).decode()

    expires_at = None
    if body.expires_days:
        expires_at = datetime.now(timezone.utc) + timedelta(days=body.expires_days)

    row = await db.fetchrow(
        """
        INSERT INTO api_keys
            (org_id, name, key_prefix, key_hash, scopes, created_by, expires_at)
        VALUES
            (current_setting('app.org_id')::uuid, $1, $2, $3, $4, $5::uuid, $6)
        RETURNING *
        """,
        body.name, key_prefix, key_hash, body.scopes,
        current_user["sub"], expires_at,
    )
    return _fmt_key(row, raw_key=raw_key)


@router.get("/api-keys/{key_id}")
async def get_key(
    key_id: str,
    db:     asyncpg.Connection = Depends(get_org_db),
):
    row = await db.fetchrow("SELECT * FROM api_keys WHERE id = $1::uuid", key_id)
    if not row:
        raise HTTPException(404, "Key not found")
    return _fmt_key(row)


@router.delete("/api-keys/{key_id}", status_code=204)
async def revoke_key(
    key_id:       str,
    db:           asyncpg.Connection = Depends(get_org_db),
    current_user: dict = Depends(require_admin),
):
    result = await db.execute(
        "UPDATE api_keys SET revoked = true WHERE id = $1::uuid", key_id
    )
    if result == "UPDATE 0":
        raise HTTPException(404, "Key not found")


# ── Dependency: authenticate via X-API-Key header ────────────────────────────

async def get_org_db_by_scoped_key(
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    pool: asyncpg.Pool = Depends(get_pool),
) -> asyncpg.Connection:
    """
    Dependency for endpoints that accept X-API-Key authentication.
    Looks up by prefix, bcrypt-checks full key, yields RLS-scoped connection.
    """
    if not x_api_key:
        raise HTTPException(401, "X-API-Key header required")

    prefix = x_api_key[:8]

    conn: asyncpg.Connection = await pool.acquire()
    try:
        async with conn.transaction():
            await conn.execute("SET LOCAL ROLE app_role")
            rows = await conn.fetch(
                "SELECT * FROM api_keys WHERE key_prefix = $1 AND revoked = false", prefix
            )
            matched = None
            for row in rows:
                if bcrypt.checkpw(x_api_key.encode(), row["key_hash"].encode()):
                    if row["expires_at"] and row["expires_at"] < datetime.now(timezone.utc):
                        raise HTTPException(401, "API key has expired")
                    matched = row
                    break

            if not matched:
                raise HTTPException(401, "Invalid or revoked API key")

            # Update last_used_at
            await conn.execute(
                "UPDATE api_keys SET last_used_at = NOW() WHERE id = $1", matched["id"]
            )
            await conn.execute(f"SET LOCAL app.org_id = '{matched['org_id']}'")
            yield conn
    finally:
        await pool.release(conn)
