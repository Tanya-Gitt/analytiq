"""
Shared test fixtures for the Unified Analytics Platform.

Setup:
  - Real PostgreSQL instance (pytest-postgresql spins up a temporary PG)
  - Schema applied from db/schema.sql
  - Two test orgs (org_a, org_b) for cross-tenant isolation tests
  - httpx AsyncClient for end-to-end route tests

Run tests:
    pytest tests/ -v

Requirements:
    pytest>=8.0
    pytest-asyncio>=0.23
    httpx>=0.27
    pytest-postgresql>=6.0
    bcrypt
    python-jose[cryptography]
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import AsyncGenerator

import asyncpg
import bcrypt
import pytest_asyncio
from dotenv import load_dotenv
from httpx import ASGITransport, AsyncClient

# Load .env so JWT_SECRET and other env vars are available during tests.
# override=False means pre-set environment variables (e.g. from CI) take priority.
load_dotenv(Path(__file__).parent.parent / ".env", override=False)

# ── Database fixtures ─────────────────────────────────────────────────────────

SCHEMA_PATH = Path(__file__).parent.parent / "db" / "schema.sql"


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def db_pool() -> AsyncGenerator[asyncpg.Pool, None]:
    """
    Session-scoped asyncpg pool connected to a real PostgreSQL test database.

    Uses DATABASE_URL env var if set, otherwise falls back to localhost defaults.
    In CI, set DATABASE_URL=postgresql://postgres:postgres@localhost:5432/analytics_test
    """
    dsn = os.environ.get(
        "TEST_DATABASE_URL",
        "postgresql://postgres:postgres@localhost:5432/analytics_test",
    )
    async def _init_conn(conn: asyncpg.Connection) -> None:
        await conn.set_type_codec(
            "jsonb", encoder=json.dumps, decoder=json.loads, schema="pg_catalog"
        )

    pool = await asyncpg.create_pool(dsn=dsn, min_size=1, max_size=5, init=_init_conn)

    # Apply schema
    schema_sql = SCHEMA_PATH.read_text()
    async with pool.acquire() as conn:
        await conn.execute(schema_sql)

    yield pool

    # Teardown: drop all test data
    async with pool.acquire() as conn:
        await conn.execute(
            "TRUNCATE orgs, users, events, orders, connectors, alert_rules, "
            "custom_rows, sync_runs RESTART IDENTITY CASCADE"
        )
    await pool.close()


async def _cancel_background_tasks() -> None:
    """
    Cancel and await all asyncio tasks except the current one.

    Called in org fixture teardown (before the org DELETE) and in
    clean_tables teardown (safety net for tests that don't use org fixtures).
    Background sync tasks hold asyncpg pool connections; if they are still
    running when we try to acquire a connection for teardown SQL, the pool
    can be exhausted or the connection left in a bad state.
    """
    current = asyncio.current_task()
    orphans = [t for t in asyncio.all_tasks() if t is not current and not t.done()]
    for task in orphans:
        task.cancel()
    if orphans:
        await asyncio.gather(*orphans, return_exceptions=True)


@pytest_asyncio.fixture(autouse=True)
async def clean_tables(db_pool: asyncpg.Pool):
    """
    Wipe ALL tables before each test (setup) and after (teardown).

    Setup truncation ensures tests start with a clean slate even when a
    previous run crashed mid-teardown and left rows behind (e.g. the
    users_email_key UniqueViolationError caused by a dirty DB).

    Teardown truncation is a safety net that catches anything not already
    cleaned by the org fixtures' per-org DELETE.  Both phases include
    orgs + users so the DB is never left dirty regardless of which fixtures
    a given test uses.
    """
    # ── Setup: guarantee clean state before the test runs ───────────────────
    async with db_pool.acquire() as conn:
        await conn.execute(
            "TRUNCATE orgs, users, events, orders, connectors, alert_rules, "
            "custom_rows, sync_runs, rate_limits RESTART IDENTITY CASCADE"
        )

    yield

    # ── Teardown: cancel tasks, then clean any remaining rows ────────────────
    await _cancel_background_tasks()
    async with db_pool.acquire() as conn:
        await conn.execute(
            "TRUNCATE orgs, users, events, orders, connectors, alert_rules, "
            "custom_rows, sync_runs, rate_limits RESTART IDENTITY CASCADE"
        )


# ── Org fixtures ──────────────────────────────────────────────────────────────

class OrgFixture:
    """Holds credentials for a test org."""
    def __init__(self, org_id: str, api_key: str, jwt: str, user_id: str):
        self.org_id = org_id
        self.api_key = api_key
        self.jwt = jwt
        self.user_id = user_id

    @property
    def auth_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.jwt}"}


async def _create_test_org(pool: asyncpg.Pool, name: str, email: str) -> OrgFixture:
    """Helper: create an org + user and return credentials."""
    from app.auth import create_access_token

    password_hash = bcrypt.hashpw(b"testpassword", bcrypt.gensalt()).decode()

    async with pool.acquire() as conn:
        async with conn.transaction():
            org = await conn.fetchrow(
                "INSERT INTO orgs (name) VALUES ($1) RETURNING id, api_key", name
            )
            user = await conn.fetchrow(
                "INSERT INTO users (org_id, email, password_hash) VALUES ($1, $2, $3) RETURNING id",
                org["id"],
                email,
                password_hash,
            )

    jwt = create_access_token(user_id=str(user["id"]), org_id=str(org["id"]))
    return OrgFixture(
        org_id=str(org["id"]),
        api_key=org["api_key"],
        jwt=jwt,
        user_id=str(user["id"]),
    )


@pytest_asyncio.fixture
async def org_a(db_pool: asyncpg.Pool) -> OrgFixture:
    """Test org A."""
    org = await _create_test_org(db_pool, "Org Alpha", "alpha@test.com")
    yield org
    # Cancel background tasks BEFORE releasing the DB connection.
    # Background sync tasks (spawned via asyncio.create_task) hold asyncpg
    # pool connections.  If they are still running when we execute the DELETE
    # below, the pool can be exhausted and the DELETE hangs or fails.
    await _cancel_background_tasks()
    async with db_pool.acquire() as conn:
        await conn.execute("DELETE FROM orgs WHERE id = $1", org.org_id)


@pytest_asyncio.fixture
async def org_b(db_pool: asyncpg.Pool) -> OrgFixture:
    """Test org B — used to verify cross-tenant isolation."""
    org = await _create_test_org(db_pool, "Org Beta", "beta@test.com")
    yield org
    await _cancel_background_tasks()
    async with db_pool.acquire() as conn:
        await conn.execute("DELETE FROM orgs WHERE id = $1", org.org_id)


# ── HTTP client fixture ───────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def client(db_pool: asyncpg.Pool) -> AsyncGenerator[AsyncClient, None]:
    """
    httpx AsyncClient wired to the FastAPI app with a real DB pool.
    The app's pool is replaced with the test pool so tests use the same DB.
    """
    from app.main import app as fastapi_app

    # Inject test pool into app state
    fastapi_app.state.pool = db_pool

    async with AsyncClient(
        transport=ASGITransport(app=fastapi_app),
        base_url="http://test",
    ) as ac:
        yield ac
