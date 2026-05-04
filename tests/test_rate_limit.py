"""
Unit tests for the Postgres-backed token-bucket rate limiter.

Tests exercise _check_rate_limit_db() directly against a real database,
verifying burst cap, continuous refill, and per-org isolation.

Key design decision: timing-sensitive boundary tests (e.g. "101st request
fails") use _set_bucket() to write exact state into rate_limits rather than
burning 100 live DB calls — 100 × ~10 ms = ~1 s of elapsed time would
naturally refill the bucket and make the assertions flaky.
"""

from __future__ import annotations

import asyncpg
import pytest


async def _set_bucket(
    pool: asyncpg.Pool, org_id: str, tokens: float, seconds_ago: float = 0
) -> None:
    """
    Directly write a rate_limits row so tests can set up specific states
    without burning N DB transactions.

    seconds_ago: makes last_refill_at N seconds in the past, so the next
    _check_rate_limit_db call will see (seconds_ago * 100) tokens of natural
    refill added on top of `tokens`.  Pass 0 to freeze the clock.
    """
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO rate_limits (org_id, tokens, last_refill_at)
            VALUES ($1::uuid, $2, NOW() - ($3 || ' seconds')::interval)
            ON CONFLICT (org_id) DO UPDATE
              SET tokens         = $2,
                  last_refill_at = NOW() - ($3 || ' seconds')::interval
            """,
            org_id,
            tokens,
            str(seconds_ago),
        )


async def _read_tokens(pool: asyncpg.Pool, org_id: str) -> float | None:
    """Read the current stored token count for an org (None if no row yet)."""
    async with pool.acquire() as conn:
        return await conn.fetchval(
            "SELECT tokens FROM rate_limits WHERE org_id = $1::uuid",
            org_id,
        )


class TestTokenBucket:

    @pytest.mark.asyncio
    async def test_first_100_succeed(self, db_pool: asyncpg.Pool, org_a):
        """A fresh org should allow 100 consecutive requests before blocking."""
        from app.routers.ingest import _check_rate_limit_db

        passed = 0
        for _ in range(100):
            if await _check_rate_limit_db(db_pool, org_a.org_id):
                passed += 1
        assert passed == 100

    @pytest.mark.asyncio
    async def test_101st_fails(self, db_pool: asyncpg.Pool, org_a):
        """
        With tokens well below 0 and last_refill_at = NOW, the next request
        must be denied even if the DB call takes up to 500 ms (at 100 tokens/s,
        500 ms adds 50 tokens, still leaving us at -50 < 1).

        We seed -100 rather than 0 because seeding exactly 0 is flaky under
        load: the DB round-trip itself can take > 10 ms, which adds a full
        token at 100/s and flips the result to True.
        """
        from app.routers.ingest import _check_rate_limit_db

        await _set_bucket(db_pool, org_a.org_id, tokens=-100.0, seconds_ago=0)
        assert await _check_rate_limit_db(db_pool, org_a.org_id) is False

    @pytest.mark.asyncio
    async def test_refill_after_one_second(self, db_pool: asyncpg.Pool, org_a):
        """
        With 0 tokens and last_refill_at backdated 1 second, the refill
        adds 100 tokens (rate=100/s) → next request must succeed.
        """
        from app.routers.ingest import _check_rate_limit_db

        await _set_bucket(db_pool, org_a.org_id, tokens=0.0, seconds_ago=1.0)
        assert await _check_rate_limit_db(db_pool, org_a.org_id) is True

    @pytest.mark.asyncio
    async def test_buckets_are_per_org(self, db_pool: asyncpg.Pool, org_a, org_b):
        """Exhausting org_a's bucket must not affect org_b."""
        from app.routers.ingest import _check_rate_limit_db

        await _set_bucket(db_pool, org_a.org_id, tokens=0.0, seconds_ago=0)

        assert await _check_rate_limit_db(db_pool, org_a.org_id) is False  # org_a blocked
        assert await _check_rate_limit_db(db_pool, org_b.org_id) is True   # org_b unaffected

    @pytest.mark.asyncio
    async def test_partial_refill(self, db_pool: asyncpg.Pool, org_a):
        """
        0 tokens + 0.5s backdate → ~50 new tokens via refill math.
        After one call we read the stored token count to verify the refill
        happened correctly, rather than looping (which would itself add tokens
        at 100/s via elapsed time during each DB transaction).
        """
        from app.routers.ingest import _check_rate_limit_db

        await _set_bucket(db_pool, org_a.org_id, tokens=0.0, seconds_ago=0.5)
        allowed = await _check_rate_limit_db(db_pool, org_a.org_id)

        assert allowed is True  # 50 tokens → consume 1 → allowed
        remaining = await _read_tokens(db_pool, org_a.org_id)
        # ~49 tokens remaining; allow a ±3 window for sub-millisecond drift
        assert remaining is not None
        assert 46.0 <= float(remaining) <= 50.0

    @pytest.mark.asyncio
    async def test_does_not_exceed_burst_cap(self, db_pool: asyncpg.Pool, org_a):
        """
        Backdating by 100 seconds would add 10 000 tokens without the cap.
        After one call the stored tokens must be ≤ BURST (100).
        """
        from app.routers.ingest import _check_rate_limit_db

        await _set_bucket(db_pool, org_a.org_id, tokens=0.0, seconds_ago=100.0)
        await _check_rate_limit_db(db_pool, org_a.org_id)  # triggers refill + consume

        remaining = await _read_tokens(db_pool, org_a.org_id)
        assert remaining is not None
        assert float(remaining) <= 100.0   # burst cap applied
        assert float(remaining) >= 98.0    # ≈ 99 (100 cap − 1 consumed)

    @pytest.mark.asyncio
    async def test_tokens_persisted_across_calls(self, db_pool: asyncpg.Pool, org_a):
        """
        State lives in Postgres, not process memory.
        Seed exactly 3 tokens, make 3 calls, verify the row reads ~0.
        """
        from app.routers.ingest import _check_rate_limit_db

        await _set_bucket(db_pool, org_a.org_id, tokens=3.0, seconds_ago=0)

        for _ in range(3):
            await _check_rate_limit_db(db_pool, org_a.org_id)

        remaining = await _read_tokens(db_pool, org_a.org_id)
        assert remaining is not None
        # 3 tokens consumed; tiny refill from 3 DB round-trips (~30 ms ≈ 3 tokens) expected
        assert float(remaining) < 4.0
