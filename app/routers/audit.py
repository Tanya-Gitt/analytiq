"""
Audit Log

GET /api/audit  — paginated admin action history with optional filters
"""

from __future__ import annotations

import asyncpg
from fastapi import APIRouter, Depends, Query

from app.deps import get_org_db

router = APIRouter()

ACTION_CATEGORIES = {
    "flag":      ["flag.created", "flag.updated", "flag.deleted"],
    "team":      ["member.invited", "member.removed", "member.role_changed"],
    "connector": ["connector.created", "connector.deleted"],
    "gdpr":      ["gdpr.export", "gdpr.forget", "gdpr.opt_out", "gdpr.opt_out_removed"],
    "alert":     ["alert.created", "alert.deleted"],
}


@router.get("/audit")
async def list_audit(
    category: str | None = Query(None, description="flag|team|connector|gdpr|alert"),
    limit:    int        = Query(100, ge=1, le=500),
    offset:   int        = Query(0,   ge=0),
    db:       asyncpg.Connection = Depends(get_org_db),
):
    where = ""
    params: list = [limit, offset]

    if category and category in ACTION_CATEGORIES:
        actions = ACTION_CATEGORIES[category]
        placeholders = ", ".join(f"${i+3}" for i in range(len(actions)))
        where = f"WHERE action IN ({placeholders})"
        params = actions + [limit, offset]
        limit_idx  = len(actions) + 1
        offset_idx = len(actions) + 2
    else:
        limit_idx, offset_idx = 1, 2

    rows = await db.fetch(
        f"""
        SELECT id, actor_email, action, resource_type, resource_id, metadata, created_at
        FROM audit_log
        {where}
        ORDER BY created_at DESC
        LIMIT ${limit_idx} OFFSET ${offset_idx}
        """,
        *params,
    )

    total = await db.fetchval("SELECT COUNT(*) FROM audit_log")

    return {
        "entries": [
            {
                "id":            r["id"],
                "actor_email":   r["actor_email"],
                "action":        r["action"],
                "resource_type": r["resource_type"],
                "resource_id":   r["resource_id"],
                "metadata":      dict(r["metadata"]) if r["metadata"] else {},
                "created_at":    r["created_at"].isoformat(),
            }
            for r in rows
        ],
        "total":  total,
        "limit":  limit,
        "offset": offset,
    }
