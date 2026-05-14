#!/usr/bin/env python3
"""
Run database schema + all migrations in order.

Called by Render's startCommand before uvicorn starts:
    python scripts/migrate.py && uvicorn app.main:app ...

Also safe to run manually:
    DATABASE_URL=postgresql://... python scripts/migrate.py

Idempotent — every SQL file uses IF NOT EXISTS / DO $$ guards.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

import asyncpg

ROOT = Path(__file__).parent.parent
SCHEMA_PATH    = ROOT / "db" / "schema.sql"
MIGRATIONS_DIR = ROOT / "db" / "migrations"


async def run() -> None:
    dsn = (
        os.environ.get("DATABASE_URL")
        or os.environ.get("TEST_DATABASE_URL")
        or "postgresql://postgres:postgres@localhost:5432/analytics_test"
    )

    # Render injects DATABASE_URL with the postgres:// scheme;
    # asyncpg requires postgresql://
    if dsn.startswith("postgres://"):
        dsn = dsn.replace("postgres://", "postgresql://", 1)

    print("[migrate] connecting to database …", flush=True)

    async def _init_conn(conn: asyncpg.Connection) -> None:
        await conn.set_type_codec(
            "jsonb", encoder=json.dumps, decoder=json.loads, schema="pg_catalog"
        )

    pool = await asyncpg.create_pool(dsn=dsn, min_size=1, max_size=3, init=_init_conn)

    async with pool.acquire() as conn:
        # Ensure app_role / app_user exist (created by Docker shell script but
        # absent in fresh Render / Neon / CI environments).
        print("[migrate] ensuring roles …", flush=True)
        await conn.execute("""
            DO $$
            BEGIN
                IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_role') THEN
                    CREATE ROLE app_role;
                END IF;
                IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_user') THEN
                    CREATE ROLE app_user;
                END IF;
            END $$;
        """)
        # Grant app_role membership to the current DB user (e.g. neondb_owner on Neon,
        # postgres in Docker). This is required so the app can do SET LOCAL ROLE app_role
        # inside transactions to enforce RLS policies.
        # GRANT is idempotent — granting a role the user already has is a no-op.
        await conn.execute("GRANT app_role TO CURRENT_USER")

        print("[migrate] applying schema.sql …", flush=True)
        await conn.execute(SCHEMA_PATH.read_text())

        migrations = sorted(MIGRATIONS_DIR.glob("*.sql"))
        for path in migrations:
            print(f"[migrate] applying {path.name} …", flush=True)
            await conn.execute(path.read_text())

    await pool.close()
    print(f"[migrate] done — schema + {len(migrations)} migration(s) applied.", flush=True)


if __name__ == "__main__":
    try:
        asyncio.run(run())
    except Exception as exc:
        print(f"[migrate] FAILED: {exc}", file=sys.stderr)
        sys.exit(1)
