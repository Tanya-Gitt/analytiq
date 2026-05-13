"""
Custom funnel builder API.

GET    /api/funnels              — list funnels for the org
POST   /api/funnels              — create a new funnel
PUT    /api/funnels/{id}         — update name/steps
DELETE /api/funnels/{id}         — delete a funnel
GET    /api/funnels/{id}/data    — run the funnel query, return step conversion data
GET    /api/funnels/events       — return distinct event names (for autocomplete)
"""

from __future__ import annotations

import json
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, field_validator

from app.deps import get_org_db

router = APIRouter()


# ── Pydantic models ───────────────────────────────────────────────────────────

class FunnelCreate(BaseModel):
    name:  str
    steps: list[str]

    @field_validator("name")
    @classmethod
    def name_not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("name must not be empty")
        if len(v) > 120:
            raise ValueError("name too long (max 120 chars)")
        return v

    @field_validator("steps")
    @classmethod
    def steps_valid(cls, v: list[str]) -> list[str]:
        v = [s.strip() for s in v if s.strip()]
        if len(v) < 2:
            raise ValueError("funnel must have at least 2 steps")
        if len(v) > 10:
            raise ValueError("funnel can have at most 10 steps")
        return v


class FunnelUpdate(BaseModel):
    name:  str | None = None
    steps: list[str] | None = None

    @field_validator("name")
    @classmethod
    def name_not_empty(cls, v: str | None) -> str | None:
        if v is None:
            return v
        v = v.strip()
        if not v:
            raise ValueError("name must not be empty")
        if len(v) > 120:
            raise ValueError("name too long (max 120 chars)")
        return v

    @field_validator("steps")
    @classmethod
    def steps_valid(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return v
        v = [s.strip() for s in v if s.strip()]
        if len(v) < 2:
            raise ValueError("funnel must have at least 2 steps")
        if len(v) > 10:
            raise ValueError("funnel can have at most 10 steps")
        return v


def _row_to_dict(row: asyncpg.Record) -> dict:
    steps = row["steps"]
    if isinstance(steps, str):
        steps = json.loads(steps)
    return {
        "id":         str(row["id"]),
        "name":       row["name"],
        "steps":      steps,
        "created_at": row["created_at"].isoformat(),
        "updated_at": row["updated_at"].isoformat(),
    }


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/funnels/events")
async def list_funnel_events(
    db: asyncpg.Connection = Depends(get_org_db),
):
    """Return distinct event names for the org (used for autocomplete in the builder)."""
    rows = await db.fetch(
        """
        SELECT DISTINCT event_name
        FROM   events
        WHERE  org_id = current_setting('app.org_id')::uuid
        ORDER  BY event_name
        LIMIT  200
        """
    )
    return [r["event_name"] for r in rows]


@router.get("/funnels")
async def list_funnels(
    db: asyncpg.Connection = Depends(get_org_db),
):
    rows = await db.fetch(
        "SELECT id, name, steps, created_at, updated_at FROM funnels ORDER BY created_at DESC"
    )
    return [_row_to_dict(r) for r in rows]


@router.post("/funnels", status_code=status.HTTP_201_CREATED)
async def create_funnel(
    body: FunnelCreate,
    db: asyncpg.Connection = Depends(get_org_db),
):
    row = await db.fetchrow(
        """
        INSERT INTO funnels (org_id, name, steps)
        VALUES (current_setting('app.org_id')::uuid, $1, $2::jsonb)
        RETURNING id, name, steps, created_at, updated_at
        """,
        body.name,
        json.dumps(body.steps),
    )
    return _row_to_dict(row)


@router.put("/funnels/{funnel_id}")
async def update_funnel(
    funnel_id: UUID,
    body: FunnelUpdate,
    db: asyncpg.Connection = Depends(get_org_db),
):
    if body.name is None and body.steps is None:
        raise HTTPException(400, "provide at least one of name or steps")

    # Build SET clause dynamically
    sets   = ["updated_at = NOW()"]
    params: list = [funnel_id]
    idx    = 2

    if body.name is not None:
        sets.append(f"name = ${idx}")
        params.append(body.name)
        idx += 1
    if body.steps is not None:
        sets.append(f"steps = ${idx}::jsonb")
        params.append(json.dumps(body.steps))
        idx += 1

    row = await db.fetchrow(
        f"UPDATE funnels SET {', '.join(sets)} WHERE id = $1 "
        f"RETURNING id, name, steps, created_at, updated_at",
        *params,
    )
    if row is None:
        raise HTTPException(404, "funnel not found")
    return _row_to_dict(row)


@router.delete("/funnels/{funnel_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_funnel(
    funnel_id: UUID,
    db: asyncpg.Connection = Depends(get_org_db),
):
    result = await db.execute("DELETE FROM funnels WHERE id = $1", funnel_id)
    if result == "DELETE 0":
        raise HTTPException(404, "funnel not found")


@router.get("/funnels/{funnel_id}/data")
async def get_funnel_data(
    funnel_id: UUID,
    days: int = Query(default=30, ge=1, le=365),
    db: asyncpg.Connection = Depends(get_org_db),
):
    """
    Run the funnel query for this funnel definition and return step-level conversion data.

    Algorithm: for each step, count distinct user_ids who fired that event within
    the time window.  Steps are ordered; a user is counted for step N even if they
    haven't completed step N-1 (standard "any order" funnel).  Use the 'ordered'
    variant where users must complete steps in sequence for true conversion tracking.
    """
    funnel_row = await db.fetchrow(
        "SELECT id, name, steps FROM funnels WHERE id = $1", funnel_id
    )
    if funnel_row is None:
        raise HTTPException(404, "funnel not found")

    steps = funnel_row["steps"]
    if isinstance(steps, str):
        steps = json.loads(steps)

    if not steps:
        return {"funnel_id": str(funnel_id), "name": funnel_row["name"], "steps": []}

    # Build a UNION query that counts distinct users per step
    # For ordered funnels: count users who have done step 1 AND step 2 AND ...
    # For each step N, count users in the intersection of steps 1..N
    # This is the standard "ordered funnel" approach.
    result_steps = []
    for i, step in enumerate(steps):
        # Count users who completed steps[0] through steps[i] (in any order within window)
        step_conditions = " AND ".join(
            f"""
            EXISTS (
                SELECT 1 FROM events e{j}
                WHERE e{j}.org_id = current_setting('app.org_id')::uuid
                  AND e{j}.user_id = base.user_id
                  AND e{j}.user_id IS NOT NULL
                  AND e{j}.event_name = ${j + 2}
                  AND e{j}.received_at >= CURRENT_TIMESTAMP - ($1 || ' days')::interval
            )
            """
            for j in range(i + 1)
        )

        params = [str(days)] + steps[:i + 1]
        count = await db.fetchval(
            f"""
            SELECT COUNT(DISTINCT base.user_id)
            FROM (
                SELECT DISTINCT user_id
                FROM events
                WHERE org_id = current_setting('app.org_id')::uuid
                  AND user_id IS NOT NULL
                  AND received_at >= CURRENT_TIMESTAMP - ($1 || ' days')::interval
            ) AS base
            WHERE {step_conditions}
            """,
            *params,
        )
        result_steps.append({"step": step, "users": count or 0})

    return {
        "funnel_id": str(funnel_id),
        "name":      funnel_row["name"],
        "steps":     result_steps,
        "days":      days,
    }
