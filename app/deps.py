"""
FastAPI dependency injection for RLS-enforced database connections.

CRITICAL: Do NOT use middleware for RLS. Starlette's call_next() runs the route
handler in a new task that does not share the middleware's DB connection.
SET LOCAL app.org_id in middleware fires on connection A; the route query runs
on connection B (different pool connection, org_id never set).

CORRECT PATTERN: Use get_org_db or get_org_db_by_api_key as a FastAPI Depends()
on every route that accesses tenant data.

Rule: Never call pool.acquire() directly in route handlers for org-scoped queries.
"""

from __future__ import annotations

import asyncpg
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.auth import verify_jwt, verify_jwt_get_org_id
from app.database import get_pool

bearer_scheme = HTTPBearer(auto_error=False)


async def get_org_db(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    pool: asyncpg.Pool = Depends(get_pool),
) -> asyncpg.Connection:
    """
    Dependency for JWT-authenticated routes.

    1. Validates the Bearer token.
    2. Extracts org_id from the JWT claims.
    3. Opens a pool connection and begins a transaction.
    4. Runs SET LOCAL app.org_id = <org_id> inside that transaction.
    5. Yields the connection to the route handler.
    6. Commits (or rolls back on exception) and releases the connection.

    The route handler MUST use only this yielded connection for any
    org-scoped queries — not pool.acquire() directly.

    Usage:
        @router.get("/api/events")
        async def list_events(db: asyncpg.Connection = Depends(get_org_db)):
            return await db.fetch("SELECT * FROM events")
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing authorization header",
        )

    org_id = verify_jwt_get_org_id(credentials.credentials)  # raises 401 if invalid

    conn: asyncpg.Connection = await pool.acquire()
    try:
        async with conn.transaction():
            # Drop to app_role so RLS policies actually fire (postgres superuser
            # has BYPASSRLS and would skip all policies otherwise).
            await conn.execute("SET LOCAL ROLE app_role")
            await conn.execute(f"SET LOCAL app.org_id = '{org_id}'")
            yield conn
    finally:
        await pool.release(conn)


async def get_org_db_by_api_key(
    org_api_key: str,
    pool: asyncpg.Pool = Depends(get_pool),
) -> asyncpg.Connection:
    """
    Dependency for API-key-authenticated routes (e.g. /api/ingest/{org_api_key}).

    Unlike get_org_db, this does not require a JWT. It looks up the org by
    api_key in the orgs table, then sets app.org_id in the same transaction.

    Usage:
        @router.post("/api/ingest/{org_api_key}")
        async def ingest_event(
            org_api_key: str,
            body: EventPayload,
            db: asyncpg.Connection = Depends(get_org_db_by_api_key),
        ):
            ...

    Note: org_api_key is passed via the path parameter; FastAPI automatically
    injects it when the route declares it as a path param.
    """
    conn: asyncpg.Connection = await pool.acquire()
    try:
        async with conn.transaction():
            # app_user has NOINHERIT — must SET ROLE before touching any table
            # granted to app_role (including orgs). orgs has no RLS policy so the
            # lookup works at app_role without an org context.
            await conn.execute("SET LOCAL ROLE app_role")
            row = await conn.fetchrow(
                "SELECT id FROM orgs WHERE api_key = $1",
                org_api_key,
            )
            if row is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="unknown api key",
                )
            await conn.execute(f"SET LOCAL app.org_id = '{row['id']}'")
            yield conn
    finally:
        await pool.release(conn)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> dict:
    """
    Lightweight dependency that extracts the full JWT payload (user_id, org_id, role)
    without opening a DB connection.  Use when you need role information.
    Returns a dict with keys: sub, org_id, role.
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing authorization header",
        )
    return verify_jwt(credentials.credentials)


async def require_admin(
    current_user: dict = Depends(get_current_user),
) -> dict:
    """Dependency that raises 403 if the authenticated user is not an admin."""
    if current_user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="admin role required",
        )
    return current_user


async def get_org_id_from_jwt(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> str:
    """
    Lightweight dependency that only extracts org_id from JWT without opening a
    DB connection. Useful for routes that need org_id but don't query the DB
    (e.g., rate limit checks before hitting the DB).
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing authorization header",
        )
    return str(verify_jwt_get_org_id(credentials.credentials))
