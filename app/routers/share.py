"""
Share token API — lets org owners create public read-only links.

POST   /api/share           — create a share token (JWT auth required)
GET    /api/share           — list all tokens for the authenticated org
DELETE /api/share/{token}   — revoke a share token
GET    /api/share/{token}/data — PUBLIC: return dashboard snapshot (no auth)

The public endpoint does not require a JWT.  It validates the token,
checks expiry, then re-uses the existing _fetch_segment_b_data /
_fetch_segment_a_data helpers with a manually scoped connection so
that RLS still fires correctly.

Cache: public data reads are cached in-process for 5 minutes (same
TTLCache bucket as the regular dashboard) so a viral public link
cannot DoS the database.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import asyncpg
import cachetools
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from app.database import get_pool
from app.deps import get_org_db, get_org_id_from_jwt
from app.routers.dashboard import _fetch_segment_a_data, _fetch_segment_b_data

router = APIRouter()

# ── In-process cache for public share reads ───────────────────────────────────
# keyed by (token, days) → serialisable dict
# 5-minute TTL keeps viral links from hammering the DB
_share_cache: cachetools.TTLCache = cachetools.TTLCache(maxsize=500, ttl=300)


# ── Pydantic models ───────────────────────────────────────────────────────────

class ShareCreateRequest(BaseModel):
    segment:    str           # 'A' | 'B'
    days:       int   = 30    # time window the public page will show
    label:      str   = ""    # optional human-readable name
    expires_at: datetime | None = None  # None = never expires


class ShareTokenOut(BaseModel):
    id:         str
    token:      str
    segment:    str
    days:       int
    label:      str
    expires_at: datetime | None
    created_at: datetime
    public_url: str           # convenience — fully formed URL hint


# ── Helpers ───────────────────────────────────────────────────────────────────

def _row_to_out(row: asyncpg.Record) -> dict:
    return {
        "id":         str(row["id"]),
        "token":      row["token"],
        "segment":    row["segment"],
        "days":       row["days"],
        "label":      row["label"],
        "expires_at": row["expires_at"].isoformat() if row["expires_at"] else None,
        "created_at": row["created_at"].isoformat(),
        "public_url": f"/share/{row['token']}",
    }


# ── Authenticated CRUD ────────────────────────────────────────────────────────

@router.post("/share", status_code=status.HTTP_201_CREATED)
async def create_share_token(
    body: ShareCreateRequest,
    db: asyncpg.Connection = Depends(get_org_db),
):
    """Create a new public share link for the authenticated org."""
    if body.segment not in ("A", "B"):
        raise HTTPException(400, "segment must be 'A' or 'B'")
    if not (1 <= body.days <= 365):
        raise HTTPException(400, "days must be between 1 and 365")
    if len(body.label) > 120:
        raise HTTPException(400, "label too long (max 120 chars)")

    row = await db.fetchrow(
        """
        INSERT INTO share_tokens (org_id, segment, days, label, expires_at)
        VALUES (
            current_setting('app.org_id')::uuid,
            $1, $2, $3, $4
        )
        RETURNING id, token, segment, days, label, expires_at, created_at
        """,
        body.segment,
        body.days,
        body.label,
        body.expires_at,
    )
    return _row_to_out(row)


@router.get("/share")
async def list_share_tokens(
    db: asyncpg.Connection = Depends(get_org_db),
):
    """List all share tokens for the authenticated org."""
    rows = await db.fetch(
        """
        SELECT id, token, segment, days, label, expires_at, created_at
        FROM   share_tokens
        ORDER  BY created_at DESC
        """
    )
    return [_row_to_out(r) for r in rows]


@router.delete("/share/{token}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_share_token(
    token: str,
    db: asyncpg.Connection = Depends(get_org_db),
):
    """Revoke (delete) a share token.  Only the owning org can delete it."""
    result = await db.execute(
        "DELETE FROM share_tokens WHERE token = $1",
        token,
    )
    # asyncpg returns "DELETE N" — if N=0 the token wasn't found / belongs to another org
    if result == "DELETE 0":
        raise HTTPException(404, "token not found")
    # Evict the public cache for this token
    for days in range(1, 366):
        _share_cache.pop((token, days), None)


# ── Public endpoint (no auth) ─────────────────────────────────────────────────

@router.get("/share/{token}/data")
async def public_share_data(
    token: str,
    pool: asyncpg.Pool = Depends(get_pool),
):
    """
    Return a read-only dashboard snapshot for the given share token.

    No authentication required — the token IS the credential.
    Validates expiry and then calls the same fetch helpers used by the
    authenticated dashboard.
    """
    # ── 1. Look up and validate the token ─────────────────────────────────────
    # RLS on share_tokens: SELECT policy allows any row when app.org_id is unset
    # (public token lookup).  We intentionally do NOT set app.org_id here so
    # the SELECT policy's open branch fires.  Write policies still require org context.
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute("SET LOCAL ROLE app_role")
            # app.org_id intentionally not set → SELECT policy uses the open branch
            token_row = await conn.fetchrow(
                """
                SELECT id, org_id, segment, days, expires_at
                FROM   share_tokens
                WHERE  token = $1
                """,
                token,
            )

    if token_row is None:
        raise HTTPException(404, "share link not found")

    # ── 2. Check expiry ────────────────────────────────────────────────────────
    if token_row["expires_at"] is not None:
        if datetime.now(timezone.utc) > token_row["expires_at"]:
            raise HTTPException(410, "share link has expired")

    org_id  = str(token_row["org_id"])
    segment = token_row["segment"]
    days    = token_row["days"]

    # ── 3. Check cache ─────────────────────────────────────────────────────────
    cache_key = (token, days)
    if cache_key in _share_cache:
        return _share_cache[cache_key]

    # ── 4. Fetch dashboard data with RLS scoped to the token's org ─────────────
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute("SET LOCAL ROLE app_role")
            await conn.execute(f"SET LOCAL app.org_id = '{org_id}'")

            if segment == "B":
                data: dict[str, Any] = await _fetch_segment_b_data(conn, days)
            else:
                data = await _fetch_segment_a_data(conn, days)

    result = {"segment": segment, "days": days, "data": data}
    _share_cache[cache_key] = result
    return result
