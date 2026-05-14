"""
Feature Flags + A/B Experimentation.

GET    /api/flags              — list all flags for the org
POST   /api/flags              — create a flag
PATCH  /api/flags/{id}         — update name / description / enabled / rollout_pct / targeting
DELETE /api/flags/{id}         — delete a flag
POST   /api/flags/evaluate     — evaluate flags for a user (SDK endpoint, no auth)
"""

from __future__ import annotations

import hashlib
import logging
from typing import Any

import asyncpg
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.audit_log import log_action
from app.deps import get_org_db, get_org_db_by_api_key, require_admin

logger = logging.getLogger(__name__)
router = APIRouter()


# ── Models ────────────────────────────────────────────────────────────────────

class TargetingRule(BaseModel):
    attribute: str
    operator:  str   # eq | neq | contains | gt | lt
    value:     Any


class FlagCreate(BaseModel):
    name:        str = Field(..., min_length=1, max_length=80, pattern=r'^[a-z0-9-_]+$')
    description: str = ""
    enabled:     bool = False
    rollout_pct: int  = Field(0, ge=0, le=100)
    targeting:   list[TargetingRule] = []


class FlagPatch(BaseModel):
    description: str | None = None
    enabled:     bool | None = None
    rollout_pct: int | None = Field(None, ge=0, le=100)
    targeting:   list[TargetingRule] | None = None


class FlagResponse(BaseModel):
    id:          str
    name:        str
    description: str
    enabled:     bool
    rollout_pct: int
    targeting:   list[dict]
    created_at:  str
    updated_at:  str


class EvaluateRequest(BaseModel):
    user_id:    str | None = None
    attributes: dict[str, Any] = {}   # e.g. {"plan": "pro", "country": "US"}


# ── helpers ────────────────────────────────────────────────────────────────────

def _row_to_flag(row: asyncpg.Record) -> dict:
    return {
        "id":          str(row["id"]),
        "name":        row["name"],
        "description": row["description"],
        "enabled":     row["enabled"],
        "rollout_pct": row["rollout_pct"],
        "targeting":   row["targeting"] or [],
        "created_at":  row["created_at"].isoformat(),
        "updated_at":  row["updated_at"].isoformat(),
    }


def _matches_targeting(rules: list[dict], attrs: dict[str, Any]) -> bool:
    """All rules must match (AND logic)."""
    for rule in rules:
        attr  = rule.get("attribute", "")
        op    = rule.get("operator", "eq")
        value = rule.get("value")
        actual = attrs.get(attr)
        if actual is None:
            return False
        if op == "eq" and actual != value:
            return False
        elif op == "neq" and actual == value:
            return False
        elif op == "contains" and str(value) not in str(actual):
            return False
        elif op == "gt":
            try:
                if float(actual) <= float(value):
                    return False
            except (TypeError, ValueError):
                return False
        elif op == "lt":
            try:
                if float(actual) >= float(value):
                    return False
            except (TypeError, ValueError):
                return False
    return True


def _in_rollout(flag_name: str, user_id: str, rollout_pct: int) -> bool:
    """Stable hash-based bucket assignment — same user always gets same result."""
    if rollout_pct >= 100:
        return True
    if rollout_pct <= 0:
        return False
    digest = hashlib.sha256(f"{flag_name}:{user_id}".encode()).hexdigest()
    bucket = int(digest[:8], 16) % 100
    return bucket < rollout_pct


def _evaluate_flag(flag: dict, user_id: str | None, attributes: dict) -> bool:
    if not flag["enabled"]:
        return False
    rules = flag["targeting"]
    if rules and not _matches_targeting(rules, attributes):
        return False
    if user_id:
        return _in_rollout(flag["name"], user_id, flag["rollout_pct"])
    return flag["rollout_pct"] >= 100


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/flags")
async def list_flags(db: asyncpg.Connection = Depends(get_org_db)):
    rows = await db.fetch("SELECT * FROM feature_flags ORDER BY created_at DESC, name ASC")
    return [_row_to_flag(r) for r in rows]


@router.post("/flags", status_code=201)
async def create_flag(
    body:         FlagCreate,
    db:           asyncpg.Connection = Depends(get_org_db),
    current_user: dict = Depends(require_admin),
):
    try:
        row = await db.fetchrow(
            """
            INSERT INTO feature_flags (org_id, name, description, enabled, rollout_pct, targeting)
            VALUES (current_setting('app.org_id')::uuid, $1, $2, $3, $4, $5)
            RETURNING *
            """,
            body.name, body.description, body.enabled, body.rollout_pct,
            [r.model_dump() for r in body.targeting],
        )
    except asyncpg.UniqueViolationError:
        raise HTTPException(409, f"Flag '{body.name}' already exists")
    await log_action(db, current_user["sub"], "flag.created",
                     resource_type="flag", resource_id=str(row["id"]),
                     metadata={"name": body.name})
    return _row_to_flag(row)


@router.patch("/flags/{flag_id}")
async def update_flag(
    flag_id:      str,
    body:         FlagPatch,
    db:           asyncpg.Connection = Depends(get_org_db),
    current_user: dict = Depends(require_admin),
):
    existing = await db.fetchrow(
        "SELECT * FROM feature_flags WHERE id = $1::uuid", flag_id
    )
    if not existing:
        raise HTTPException(404, "Flag not found")

    enabled     = body.enabled     if body.enabled     is not None else existing["enabled"]
    rollout_pct = body.rollout_pct if body.rollout_pct is not None else existing["rollout_pct"]
    description = body.description if body.description is not None else existing["description"]
    targeting   = [r.model_dump() for r in body.targeting] if body.targeting is not None else existing["targeting"]

    row = await db.fetchrow(
        """
        UPDATE feature_flags
        SET    enabled = $2, rollout_pct = $3, description = $4, targeting = $5
        WHERE  id = $1::uuid
        RETURNING *
        """,
        flag_id, enabled, rollout_pct, description, targeting,
    )
    await log_action(db, current_user["sub"], "flag.updated",
                     resource_type="flag", resource_id=flag_id,
                     metadata={"name": row["name"], "enabled": enabled, "rollout_pct": rollout_pct})
    return _row_to_flag(row)


@router.delete("/flags/{flag_id}", status_code=204)
async def delete_flag(
    flag_id:      str,
    db:           asyncpg.Connection = Depends(get_org_db),
    current_user: dict = Depends(require_admin),
):
    existing = await db.fetchrow("SELECT name FROM feature_flags WHERE id = $1::uuid", flag_id)
    result = await db.execute(
        "DELETE FROM feature_flags WHERE id = $1::uuid", flag_id
    )
    if result == "DELETE 0":
        raise HTTPException(404, "Flag not found")
    await log_action(db, current_user["sub"], "flag.deleted",
                     resource_type="flag", resource_id=flag_id,
                     metadata={"name": existing["name"] if existing else ""})


@router.post("/flags/evaluate/{org_api_key}")
async def evaluate_flags(
    org_api_key: str,
    body: EvaluateRequest,
    db:   asyncpg.Connection = Depends(get_org_db_by_api_key),
):
    """
    Evaluate all enabled flags for a given user_id + attributes.
    Returns a dict of {flag_name: bool}.

    Authenticated by org API key in the URL path (same pattern as /api/ingest/{key})
    so the JS SDK can call this without a JWT Bearer token.
    """
    rows = await db.fetch(
        "SELECT * FROM feature_flags WHERE enabled = true ORDER BY name"
    )
    result: dict[str, bool] = {}
    for row in rows:
        flag = _row_to_flag(row)
        result[flag["name"]] = _evaluate_flag(flag, body.user_id, body.attributes)
    return result
