"""
Chart annotations API — dated labels that appear as reference lines on charts.

GET    /api/annotations?segment=B  — list annotations for the org + segment
POST   /api/annotations            — create an annotation
DELETE /api/annotations/{id}       — delete an annotation
"""

from __future__ import annotations

import datetime
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, field_validator

from app.deps import get_org_db

router = APIRouter()

# Hard cap on annotations per (org, segment). Charts can only visually fit
# ~8 stacked labels at the standard 200px height; we allow some headroom for
# users to keep historical markers around. Anything past this is rejected
# at create time so the table never grows unbounded.
MAX_ANNOTATIONS_PER_SEGMENT = 20


# ── Pydantic models ───────────────────────────────────────────────────────────

class AnnotationCreate(BaseModel):
    segment: str
    date:    str              # ISO date string "YYYY-MM-DD"
    label:   str
    color:   str = "#6366f1"

    @field_validator("label")
    @classmethod
    def label_not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("label must not be empty")
        if len(v) > 120:
            raise ValueError("label too long (max 120 chars)")
        return v

    @field_validator("color")
    @classmethod
    def color_format(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("color must not be empty")
        return v


def _row_to_dict(row: asyncpg.Record) -> dict:
    return {
        "id":         str(row["id"]),
        "segment":    row["segment"],
        "date":       row["date"].isoformat() if hasattr(row["date"], "isoformat") else str(row["date"]),
        "label":      row["label"],
        "color":      row["color"],
        "created_at": row["created_at"].isoformat(),
    }


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/annotations")
async def list_annotations(
    segment: str = Query(..., description="'A' or 'B'"),
    db: asyncpg.Connection = Depends(get_org_db),
):
    """Return all annotations for the org filtered by segment, ordered by date."""
    if segment not in ("A", "B"):
        raise HTTPException(400, "segment must be 'A' or 'B'")

    rows = await db.fetch(
        """
        SELECT id, segment, date, label, color, created_at
        FROM   annotations
        WHERE  segment = $1
        ORDER  BY date, created_at
        """,
        segment,
    )
    return [_row_to_dict(r) for r in rows]


@router.post("/annotations", status_code=status.HTTP_201_CREATED)
async def create_annotation(
    body: AnnotationCreate,
    db: asyncpg.Connection = Depends(get_org_db),
):
    """Create a new chart annotation."""
    if body.segment not in ("A", "B"):
        raise HTTPException(400, "segment must be 'A' or 'B'")

    try:
        parsed_date = datetime.date.fromisoformat(body.date)
    except ValueError:
        raise HTTPException(400, "date must be in YYYY-MM-DD format")

    # Enforce per-segment cap before insert.
    existing = await db.fetchval(
        "SELECT COUNT(*) FROM annotations WHERE segment = $1",
        body.segment,
    )
    if existing >= MAX_ANNOTATIONS_PER_SEGMENT:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Annotation limit reached ({MAX_ANNOTATIONS_PER_SEGMENT} per segment). "
                f"Delete an older annotation before adding a new one."
            ),
        )

    try:
        row = await db.fetchrow(
            """
            INSERT INTO annotations (org_id, segment, date, label, color)
            VALUES (current_setting('app.org_id')::uuid, $1, $2, $3, $4)
            RETURNING id, segment, date, label, color, created_at
            """,
            body.segment,
            parsed_date,
            body.label,
            body.color,
        )
    except asyncpg.InvalidTextRepresentationError:
        raise HTTPException(400, "date must be in YYYY-MM-DD format")

    return _row_to_dict(row)


@router.delete("/annotations/{annotation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_annotation(
    annotation_id: UUID,
    db: asyncpg.Connection = Depends(get_org_db),
):
    """Delete an annotation.  Only the owning org can delete it (RLS enforced)."""
    result = await db.execute(
        "DELETE FROM annotations WHERE id = $1",
        annotation_id,
    )
    if result == "DELETE 0":
        raise HTTPException(404, "annotation not found")
