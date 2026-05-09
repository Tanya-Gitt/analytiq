"""
POST /api/ingest/{org_api_key} — Segment A event ingest.

Rate limited: token bucket, 100 tokens/s per org, continuous refill.
State is persisted in the `rate_limits` Postgres table so bucket counts
survive app restarts and are correct when the app is scaled to multiple
replicas (each replica reads/updates the same row with SELECT FOR UPDATE).

CORS: validates Origin header against js_sdk connector allowed_origins.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel

from app.database import get_pool
from app.deps import get_org_db_by_api_key

router = APIRouter()


# ── Rate limiting (Postgres-backed token bucket) ──────────────────────────────
# One row per org in the `rate_limits` table:
#   (org_id, tokens DOUBLE PRECISION, last_refill_at TIMESTAMPTZ)
#
# SELECT FOR UPDATE locks the row for the duration of the transaction,
# preventing concurrent requests from seeing stale token counts.
#
# Survives restarts; correct under horizontal scale (N replicas share state).

_RATE = 100.0   # tokens added per second
_BURST = 100.0  # max bucket size


async def _check_rate_limit_db(pool: asyncpg.Pool, org_id: str) -> bool:
    """
    Returns True if the request is allowed, False if rate-limited.

    Algorithm (all inside one serialised transaction):
      1. UPSERT to guarantee the row exists (first request for a new org).
      2. SELECT FOR UPDATE — row-level lock so concurrent requests queue up.
      3. Compute refilled token count based on elapsed time.
      4. If tokens >= 1: consume one, UPDATE, return True.
         Else:           UPDATE (save refill), return False.
    """
    async with pool.acquire() as conn:
        async with conn.transaction():
            # Step 1 — ensure row exists
            await conn.execute(
                """
                INSERT INTO rate_limits (org_id)
                VALUES ($1::uuid)
                ON CONFLICT DO NOTHING
                """,
                org_id,
            )

            # Step 2 — lock row
            row = await conn.fetchrow(
                """
                SELECT tokens, last_refill_at
                FROM   rate_limits
                WHERE  org_id = $1::uuid
                FOR UPDATE
                """,
                org_id,
            )

            # Step 3 — refill
            tokens: float = float(row["tokens"])
            elapsed: float = (
                datetime.now(timezone.utc) - row["last_refill_at"]
            ).total_seconds()
            tokens = min(_BURST, tokens + elapsed * _RATE)

            # Step 4 — consume or deny
            allowed = tokens >= 1.0
            new_tokens = (tokens - 1.0) if allowed else tokens

            await conn.execute(
                """
                UPDATE rate_limits
                SET    tokens         = $2,
                       last_refill_at = NOW()
                WHERE  org_id         = $1::uuid
                """,
                org_id,
                new_tokens,
            )

    return allowed


# ── CORS validation ───────────────────────────────────────────────────────────

async def _check_cors(request: Request, conn: asyncpg.Connection, org_id: str) -> None:
    """
    If an Origin header is present (browser request), validate it against
    the js_sdk connector's allowed_origins for this org.

    Server-to-server requests (no Origin header) bypass CORS validation.
    """
    origin = request.headers.get("origin")
    if not origin:
        return  # server-to-server, no CORS check needed

    row = await conn.fetchrow(
        "SELECT config FROM connectors WHERE org_id = current_setting('app.org_id')::uuid AND type = 'js_sdk' LIMIT 1"
    )
    if row is None:
        raise HTTPException(status_code=403, detail="no js_sdk connector configured for this org")

    allowed: list[str] = row["config"].get("allowed_origins", [])
    if allowed and origin not in allowed:
        raise HTTPException(status_code=403, detail="origin not in allowed_origins")


# ── Pydantic models ───────────────────────────────────────────────────────────

_MAX_STRING_LEN  = 512     # max chars for string scalar fields
_MAX_PROPERTIES  = 50      # max number of keys in properties
_MAX_PROP_DEPTH  = 3       # max JSON nesting depth
_MAX_PROP_VALUE  = 4096    # max chars per property value string


def _validate_properties(props: dict[str, Any], depth: int = 0) -> None:
    """
    Reject payloads that could cause DB bloat or parser bombs.
    Raises ValueError on violation.
    """
    if depth > _MAX_PROP_DEPTH:
        raise ValueError(f"properties nesting too deep (max {_MAX_PROP_DEPTH} levels)")
    if len(props) > _MAX_PROPERTIES:
        raise ValueError(f"too many property keys (max {_MAX_PROPERTIES})")
    for k, v in props.items():
        if isinstance(v, str) and len(v) > _MAX_PROP_VALUE:
            raise ValueError(f"property {k!r} value exceeds {_MAX_PROP_VALUE} chars")
        if isinstance(v, dict):
            _validate_properties(v, depth + 1)


class EventPayload(BaseModel):
    type: str                          # 'track' | 'identify' | 'page'
    event: str | None = None           # required for type='track'
    userId: str | None = None
    anonymousId: str | None = None
    properties: dict[str, Any] = {}


# ── Route ─────────────────────────────────────────────────────────────────────

@router.post("/ingest/{org_api_key}")
async def ingest_event(
    org_api_key: str,
    body: EventPayload,
    request: Request,
    pool: asyncpg.Pool = Depends(get_pool),
    db: asyncpg.Connection = Depends(get_org_db_by_api_key),
):
    """
    Ingest a single event for an org identified by api_key.

    Rate limit: 100 req/s per org (Postgres token bucket, restart-safe).
    CORS: Origin header validated against js_sdk connector allowed_origins.
    """
    # Get org_id from DB context (already set by get_org_db_by_api_key)
    org_id = await db.fetchval("SELECT current_setting('app.org_id', true)")

    # Rate limit check (uses separate pool connection — does not interfere with
    # the RLS-scoped `db` connection already holding a transaction)
    if not await _check_rate_limit_db(pool, org_id):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="rate limit exceeded",
            headers={"Retry-After": "1"},
        )

    # CORS check (browser requests only)
    await _check_cors(request, db, org_id)

    # Validate event type
    if body.type not in ("track", "identify", "page"):
        raise HTTPException(status_code=400, detail=f"invalid type: {body.type!r}")

    if body.type == "track" and not body.event:
        raise HTTPException(status_code=400, detail="event field required for type='track'")

    # Validate properties size to prevent DB bloat and parser bombs
    try:
        _validate_properties(body.properties)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    event_name = body.event or body.type

    await db.execute(
        """
        INSERT INTO events (org_id, event_name, user_id, anonymous_id, properties)
        VALUES (current_setting('app.org_id')::uuid, $1, $2, $3, $4)
        """,
        event_name,
        body.userId,
        body.anonymousId,
        body.properties,
    )

    return {"ok": True}
