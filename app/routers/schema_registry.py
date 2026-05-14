"""
Event Schema Registry

GET    /api/schema                         — list schemas
POST   /api/schema                         — upsert schema for an event
DELETE /api/schema/{event_name}            — remove schema
GET    /api/schema/violations              — recent violations (7d)
GET    /api/schema/pii-summary             — PII redaction counts per event (30d)
GET    /api/schema/infer/{event_name}      — infer schema from last 100 events
"""

from __future__ import annotations

import urllib.parse
from typing import Any

import asyncpg
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.deps import get_org_db, require_admin

router = APIRouter()


# ── Models ────────────────────────────────────────────────────────────────────

class PropertyDef(BaseModel):
    type:        str  = "string"   # string | number | boolean | object | array
    required:    bool = False
    description: str  = ""


class SchemaUpsert(BaseModel):
    event_name:  str
    properties:  dict[str, PropertyDef] = {}
    strict_mode: bool = False


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/schema")
async def list_schemas(db: asyncpg.Connection = Depends(get_org_db)):
    rows = await db.fetch(
        "SELECT id, event_name, properties, strict_mode, created_at, updated_at FROM event_schemas ORDER BY event_name"
    )
    return [
        {
            "id":          str(r["id"]),
            "event_name":  r["event_name"],
            "properties":  dict(r["properties"]) if r["properties"] else {},
            "strict_mode": r["strict_mode"],
            "created_at":  r["created_at"].isoformat(),
            "updated_at":  r["updated_at"].isoformat(),
        }
        for r in rows
    ]


@router.post("/schema", status_code=201)
async def upsert_schema(
    body:         SchemaUpsert,
    db:           asyncpg.Connection = Depends(get_org_db),
    current_user: dict = Depends(require_admin),
):
    props = {k: v.model_dump() for k, v in body.properties.items()}
    row = await db.fetchrow(
        """
        INSERT INTO event_schemas (org_id, event_name, properties, strict_mode)
        VALUES (current_setting('app.org_id')::uuid, $1, $2, $3)
        ON CONFLICT (org_id, event_name)
        DO UPDATE SET properties = EXCLUDED.properties,
                      strict_mode = EXCLUDED.strict_mode,
                      updated_at = NOW()
        RETURNING *
        """,
        body.event_name, props, body.strict_mode,
    )
    return {
        "id":          str(row["id"]),
        "event_name":  row["event_name"],
        "properties":  dict(row["properties"]) if row["properties"] else {},
        "strict_mode": row["strict_mode"],
        "updated_at":  row["updated_at"].isoformat(),
    }


@router.delete("/schema/{event_name:path}", status_code=204)
async def delete_schema(
    event_name:   str,
    db:           asyncpg.Connection = Depends(get_org_db),
    current_user: dict = Depends(require_admin),
):
    name = urllib.parse.unquote(event_name)
    result = await db.execute(
        "DELETE FROM event_schemas WHERE event_name = $1", name
    )
    if result == "DELETE 0":
        raise HTTPException(404, "Schema not found")


@router.get("/schema/violations")
async def list_violations(db: asyncpg.Connection = Depends(get_org_db)):
    rows = await db.fetch(
        """
        SELECT event_name, violation, sample_props, occurred_at
        FROM   schema_violations
        WHERE  occurred_at > NOW() - INTERVAL '7 days'
        ORDER  BY occurred_at DESC
        LIMIT  200
        """
    )
    return [
        {
            "event_name":   r["event_name"],
            "violation":    r["violation"],
            "sample_props": dict(r["sample_props"]) if r["sample_props"] else {},
            "occurred_at":  r["occurred_at"].isoformat(),
        }
        for r in rows
    ]


@router.get("/schema/pii-summary")
async def pii_summary(db: asyncpg.Connection = Depends(get_org_db)):
    try:
        rows = await db.fetch(
            """
            SELECT event_name,
                   COUNT(*)                              AS redaction_events,
                   SUM(array_length(fields_redacted, 1)) AS fields_redacted,
                   MAX(occurred_at)                      AS last_seen
            FROM   pii_redactions
            WHERE  occurred_at > NOW() - INTERVAL '30 days'
            GROUP  BY event_name
            ORDER  BY redaction_events DESC
            """
        )
    except Exception:
        rows = []
    return [
        {
            "event_name":       r["event_name"],
            "redaction_events": r["redaction_events"],
            "fields_redacted":  r["fields_redacted"] or 0,
            "last_seen":        r["last_seen"].isoformat() if r["last_seen"] else None,
        }
        for r in rows
    ]


@router.get("/schema/infer/{event_name:path}")
async def infer_schema(
    event_name: str,
    db:         asyncpg.Connection = Depends(get_org_db),
):
    """Infer a schema from the last 100 events of a given type."""
    name = urllib.parse.unquote(event_name)
    rows = await db.fetch(
        """
        SELECT properties FROM events
        WHERE  event_name = $1
        ORDER  BY received_at DESC
        LIMIT  100
        """,
        name,
    )
    if not rows:
        return {"event_name": name, "properties": {}}

    field_counts: dict[str, dict[str, Any]] = {}
    total = len(rows)

    for row in rows:
        props = dict(row["properties"]) if row["properties"] else {}
        for key, val in props.items():
            if key not in field_counts:
                field_counts[key] = {"count": 0, "types": set()}
            field_counts[key]["count"] += 1
            if isinstance(val, bool):
                field_counts[key]["types"].add("boolean")
            elif isinstance(val, (int, float)):
                field_counts[key]["types"].add("number")
            elif isinstance(val, dict):
                field_counts[key]["types"].add("object")
            elif isinstance(val, list):
                field_counts[key]["types"].add("array")
            else:
                field_counts[key]["types"].add("string")

    suggested: dict[str, dict] = {}
    for field, info in field_counts.items():
        types = list(info["types"])
        suggested[field] = {
            "type":        types[0] if len(types) == 1 else "string",
            "required":    info["count"] / total >= 0.8,
            "description": f"Seen in {info['count']}/{total} events",
        }

    return {"event_name": name, "properties": suggested, "sample_size": total}
