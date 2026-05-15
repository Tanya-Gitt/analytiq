"""
Heatmap click + scroll tracking.

POST /api/heatmap          — ingest a batch of click/scroll events (from JS SDK)
GET  /api/heatmap/pages    — list distinct page URLs that have data
GET  /api/heatmap/clicks   — aggregate click grid for a page URL
GET  /api/heatmap/scroll   — scroll depth distribution for a page URL
"""

from __future__ import annotations

import logging
from urllib.parse import urlparse

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.deps import get_org_db, get_org_db_by_api_key

logger = logging.getLogger(__name__)
router = APIRouter()

_MAX_BATCH = 50   # max events per ingest call


# ── Models ────────────────────────────────────────────────────────────────────

class HeatmapEvent(BaseModel):
    event_type: str          # 'click' | 'scroll'
    page_url:   str
    x_pct:      int | None = None   # 0–100
    y_pct:      int | None = None   # 0–100
    element:    str | None = None
    user_id:    str | None = None


class HeatmapBatch(BaseModel):
    events: list[HeatmapEvent]


# ── helpers ────────────────────────────────────────────────────────────────────

def _normalise_url(url: str) -> str:
    """Keep only scheme + host + path; strip query and fragment.
    Path-only inputs (no scheme) are returned as just the path."""
    try:
        p = urlparse(url)
        if not p.scheme:
            # Already a bare path like "/people" — strip query/fragment only
            return p.path.rstrip("/") or "/"
        return f"{p.scheme}://{p.netloc}{p.path}".rstrip("/") or url
    except Exception:
        return url[:500]


# ── Routes ────────────────────────────────────────────────────────────────────

@router.post("/heatmap/{org_api_key}", status_code=204)
async def ingest_heatmap(
    org_api_key: str,
    body: HeatmapBatch,
    db:   asyncpg.Connection = Depends(get_org_db_by_api_key),
):
    if not body.events:
        return
    if len(body.events) > _MAX_BATCH:
        raise HTTPException(400, f"Max {_MAX_BATCH} events per batch")

    await db.executemany(
        """
        INSERT INTO heatmap_events
               (org_id, page_url, event_type, x_pct, y_pct, element, user_id)
        VALUES (current_setting('app.org_id')::uuid, $1, $2, $3, $4, $5, $6)
        """,
        [
            (
                _normalise_url(e.page_url),
                e.event_type,
                max(0, min(100, e.x_pct)) if e.x_pct is not None else None,
                max(0, min(100, e.y_pct)) if e.y_pct is not None else None,
                e.element,
                e.user_id,
            )
            for e in body.events
            if e.event_type in ("click", "scroll")
        ],
    )


@router.get("/heatmap/pages")
async def list_pages(
    db: asyncpg.Connection = Depends(get_org_db),
):
    rows = await db.fetch(
        """
        SELECT page_url,
               COUNT(*) FILTER (WHERE event_type = 'click')  AS clicks,
               COUNT(*) FILTER (WHERE event_type = 'scroll') AS scrolls,
               MAX(received_at) AS last_seen
        FROM   heatmap_events
        GROUP  BY page_url
        ORDER  BY clicks DESC
        LIMIT  100
        """
    )
    return [
        {
            "page_url": r["page_url"],
            "clicks":   r["clicks"],
            "scrolls":  r["scrolls"],
            "last_seen": r["last_seen"].isoformat() if r["last_seen"] else None,
        }
        for r in rows
    ]


@router.get("/heatmap/clicks")
async def click_grid(
    page_url: str = Query(...),
    days:     int = Query(30, ge=1, le=365),
    db: asyncpg.Connection = Depends(get_org_db),
):
    """
    Returns a 10×10 grid of click densities (0–100, relative to max cell).
    Grid cell (row, col): row = y_pct // 10, col = x_pct // 10.
    """
    rows = await db.fetch(
        """
        SELECT  (y_pct / 10) AS row,
                (x_pct / 10) AS col,
                COUNT(*)     AS cnt
        FROM    heatmap_events
        WHERE   event_type = 'click'
          AND   page_url   = $1
          AND   received_at >= NOW() - ($2 || ' days')::interval
          AND   x_pct IS NOT NULL AND y_pct IS NOT NULL
        GROUP   BY 1, 2
        """,
        _normalise_url(page_url), str(days),
    )

    # Normalise to 0–100 relative intensity
    cells = [{"row": r["row"], "col": r["col"], "count": r["cnt"]} for r in rows]
    if cells:
        max_count = max(c["count"] for c in cells)
        for c in cells:
            c["intensity"] = round(c["count"] / max_count * 100)
    total = sum(c["count"] for c in cells)
    return {"cells": cells, "total_clicks": total}


@router.get("/heatmap/scroll")
async def scroll_depth(
    page_url: str = Query(...),
    days:     int = Query(30, ge=1, le=365),
    db: asyncpg.Connection = Depends(get_org_db),
):
    """
    Returns % of sessions that scrolled to each 10% depth bucket (0–100).
    """
    rows = await db.fetch(
        """
        SELECT  (y_pct / 10) * 10 AS depth_bucket,
                COUNT(DISTINCT COALESCE(user_id, received_at::text)) AS sessions
        FROM    heatmap_events
        WHERE   event_type = 'scroll'
          AND   page_url   = $1
          AND   received_at >= NOW() - ($2 || ' days')::interval
          AND   y_pct IS NOT NULL
        GROUP   BY 1
        ORDER   BY 1
        """,
        _normalise_url(page_url), str(days),
    )

    total = await db.fetchval(
        """
        SELECT COUNT(DISTINCT COALESCE(user_id, received_at::text))
        FROM   heatmap_events
        WHERE  event_type = 'scroll' AND page_url = $1
          AND  received_at >= NOW() - ($2 || ' days')::interval
        """,
        _normalise_url(page_url), str(days),
    ) or 1

    buckets = []
    for r in rows:
        depth = r["depth_bucket"]
        if depth is not None:
            buckets.append({
                "depth":    int(depth),
                "sessions": r["sessions"],
                "pct":      round(r["sessions"] / total * 100),
            })

    return {"buckets": buckets, "total_sessions": total}
