"""
asyncpg connection pool — shared across the FastAPI app.

The pool is created once at startup (lifespan) and torn down at shutdown.
All route handlers receive connections via FastAPI DI (app/deps.py).
Never call pool.acquire() directly for org-scoped queries.
"""

from __future__ import annotations

import json
import os

import asyncpg
from fastapi import Request

_pool: asyncpg.Pool | None = None


async def _init_connection(conn: asyncpg.Connection) -> None:  # pragma: no cover
    """Called for each new connection in the pool.
    Registers Python dict ↔ JSONB codec so we can pass dicts directly
    to JSONB columns without calling json.dumps() at every call site.
    Not called in tests — tests override the pool dependency directly.
    """
    await conn.set_type_codec(
        "jsonb",
        encoder=json.dumps,
        decoder=json.loads,
        schema="pg_catalog",
    )


async def create_pool() -> asyncpg.Pool:  # pragma: no cover
    """Production pool factory — called by the app lifespan, not in tests."""
    dsn = os.environ["DATABASE_URL"]  # e.g. postgresql://user:pass@postgres:5432/analytics
    return await asyncpg.create_pool(
        dsn=dsn,
        min_size=2,
        max_size=10,
        command_timeout=30,
        init=_init_connection,
    )


async def close_pool(pool: asyncpg.Pool) -> None:  # pragma: no cover
    """Called at app shutdown — not exercised by tests."""
    await pool.close()


async def get_pool(request: Request) -> asyncpg.Pool:  # pragma: no cover
    """FastAPI dependency: returns the shared pool stored on app.state.
    Overridden in tests via app.dependency_overrides.
    """
    return request.app.state.pool
