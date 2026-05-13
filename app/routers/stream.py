"""
Real-time event stream via Server-Sent Events (SSE).

GET /api/stream/events
  → streams new events for the authenticated org as they arrive

Cursor-based poll loop:
  1. Acquire a connection from the pool
  2. Query for events with id > cursor (most recent 20, ordered by id)
  3. Release the connection back to the pool
  4. Yield each event as "data: {json}\\n\\n"
  5. Sleep 3 s, repeat

We release the connection between polls so we do NOT hold a long-lived
connection open — asyncpg has a finite pool and SSE streams can be
long-lived (minutes to hours). One connection is checked out only for
the brief duration of each SELECT, then returned.

Security:
  - JWT required (same verify_jwt_get_org_id as all other endpoints)
  - RLS enforced via SET LOCAL app.org_id per poll
  - Initial cursor = max(id) so the client sees only events that arrive
    AFTER the connection is opened (no historical flood)

Client reconnect:
  EventSource automatically reconnects; on reconnect the browser sends
  `Last-Event-ID` header. We respect this by accepting an optional
  `cursor` query param (the frontend sends it on reconnect).
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import AsyncIterator

import asyncpg
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.auth import verify_jwt_get_org_id
from app.database import get_pool

logger = logging.getLogger(__name__)

_POLL_INTERVAL = 3.0   # seconds between DB polls
_BATCH_SIZE    = 20    # max events per poll

router = APIRouter()
_bearer = HTTPBearer(auto_error=False)


async def _event_generator(
    request: Request,
    pool: asyncpg.Pool,
    org_id: str,
    cursor: int | None,
) -> AsyncIterator[str]:
    """
    Async generator that yields SSE-formatted strings.
    Each yielded string is one complete SSE message.
    """
    # On initial connect (no cursor): fetch the last 50 events so the user
    # sees recent history immediately after page load / refresh, then stream
    # new events from there. This prevents the "blank on refresh" problem.
    initial_events: list = []
    if cursor is None:
        async with pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute("SET LOCAL ROLE app_role")
                await conn.execute(f"SET LOCAL app.org_id = '{org_id}'")
                rows = await conn.fetch(
                    """
                    SELECT id, event_name, user_id,
                           received_at::text AS received_at,
                           properties
                    FROM   events
                    WHERE  org_id = $1
                    ORDER  BY id DESC
                    LIMIT  50
                    """,
                    org_id,
                )
        # Reverse so oldest → newest in the feed
        initial_events = list(reversed(rows))
        cursor = initial_events[-1]["id"] if initial_events else 0

    # Send an initial "connected" comment so the browser knows the stream
    # is live (SSE comment lines start with ":").
    yield f": connected org={org_id} cursor={cursor}\n\n"

    # Replay the last 50 historical events before entering the live loop
    for row in initial_events:
        payload = {
            "id":          row["id"],
            "event_name":  row["event_name"],
            "user_id":     row["user_id"],
            "received_at": row["received_at"],
            "properties":  row["properties"] or {},
        }
        yield f"id: {row['id']}\ndata: {json.dumps(payload)}\n\n"

    while True:
        # Check if the client has disconnected (avoids burning DB on dead connections)
        if await request.is_disconnected():
            logger.debug("SSE client disconnected for org %s", org_id)
            break

        try:
            async with pool.acquire() as conn:
                async with conn.transaction():
                    await conn.execute("SET LOCAL ROLE app_role")
                    await conn.execute(f"SET LOCAL app.org_id = '{org_id}'")
                    rows = await conn.fetch(
                        """
                        SELECT id, event_name, user_id,
                               received_at::text AS received_at,
                               properties
                        FROM   events
                        WHERE  org_id = $1
                          AND  id     > $2
                        ORDER  BY id
                        LIMIT  $3
                        """,
                        org_id,
                        cursor,
                        _BATCH_SIZE,
                    )

            for row in rows:
                cursor = row["id"]
                payload = {
                    "id":           row["id"],
                    "event_name":   row["event_name"],
                    "user_id":      row["user_id"],
                    "received_at":  row["received_at"],
                    "properties":   row["properties"] or {},
                }
                # SSE format: id line + data line + blank line
                yield f"id: {cursor}\ndata: {json.dumps(payload)}\n\n"

        except asyncpg.PostgresError:
            logger.exception("SSE: DB error for org %s — sleeping before retry", org_id)

        await asyncio.sleep(_POLL_INTERVAL)


@router.get("/stream/events")
async def stream_events(
    request: Request,
    cursor: int | None = Query(default=None, description="Resume from event id (exclusive)"),
    pool: asyncpg.Pool = Depends(get_pool),
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
):
    """
    SSE stream of incoming events for the authenticated org.

    Connect with EventSource:
      const es = new EventSource('/api/stream/events', { withCredentials: false });
      // Pass token via query param since EventSource doesn't support custom headers:
      const es = new EventSource(`/api/stream/events?token=${jwt}`);

    The frontend uses fetch() with the Authorization header instead, and
    reads the response body as a ReadableStream — this avoids the EventSource
    limitation of no custom headers.
    """
    from fastapi import HTTPException, status

    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="not authenticated",
        )
    org_id = verify_jwt_get_org_id(credentials.credentials)

    return StreamingResponse(
        _event_generator(request, pool, org_id, cursor),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",   # tell nginx not to buffer SSE
            "Connection": "keep-alive",
        },
    )
