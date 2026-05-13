"""
Warehouse Sync / Data Export

GET /api/warehouse/stats           — row counts per dataset
GET /api/warehouse/export/events   — bulk export events  (json | csv)
GET /api/warehouse/export/orders   — bulk export orders
GET /api/warehouse/export/users    — bulk export identified users + traits
"""

from __future__ import annotations

import csv
import io

import asyncpg
from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response

from app.deps import get_org_db

router = APIRouter()


def _iso(v) -> str | None:
    return v.isoformat() if v else None


# ── Stats ─────────────────────────────────────────────────────────────────────

@router.get("/warehouse/stats")
async def warehouse_stats(db: asyncpg.Connection = Depends(get_org_db)):
    events = await db.fetchval("SELECT COUNT(*) FROM events")
    orders = await db.fetchval("SELECT COUNT(*) FROM orders")
    users  = await db.fetchval(
        "SELECT COUNT(DISTINCT user_id) FROM events WHERE user_id IS NOT NULL"
    )
    oldest_event = await db.fetchval(
        "SELECT MIN(received_at) FROM events"
    )
    return {
        "events":       events or 0,
        "orders":       orders or 0,
        "users":        users  or 0,
        "oldest_event": _iso(oldest_event),
    }


# ── Export helpers ────────────────────────────────────────────────────────────

def _to_csv(records: list[dict], name: str) -> Response:
    if not records:
        return Response(content="", media_type="text/csv",
                        headers={"Content-Disposition": f"attachment; filename={name}.csv"})
    buf = io.StringIO()
    flat = []
    for r in records:
        row = {k: v for k, v in r.items() if k != "traits"}
        for tk, tv in (r.get("traits") or {}).items():
            row[f"trait_{tk}"] = tv
        flat.append(row)
    writer = csv.DictWriter(buf, fieldnames=list(flat[0].keys()), extrasaction="ignore")
    writer.writeheader()
    writer.writerows(flat)
    return Response(
        content=buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={name}.csv"},
    )


def _respond(records: list[dict], fmt: str, name: str):
    if fmt == "csv":
        return _to_csv(records, name)
    return {"data": records, "count": len(records)}


# ── Events ────────────────────────────────────────────────────────────────────

@router.get("/warehouse/export/events")
async def export_events(
    since:  str | None = Query(None, description="ISO 8601 start, e.g. 2024-01-01"),
    until:  str | None = Query(None, description="ISO 8601 end"),
    fmt:    str        = Query("json", description="json or csv"),
    limit:  int        = Query(50_000, ge=1, le=500_000),
    offset: int        = Query(0, ge=0),
    db:     asyncpg.Connection = Depends(get_org_db),
):
    params: list = []
    clauses: list[str] = []
    if since:
        params.append(since)
        clauses.append(f"received_at >= ${len(params)}::timestamptz")
    if until:
        params.append(until)
        clauses.append(f"received_at <= ${len(params)}::timestamptz")
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    params += [limit, offset]

    rows = await db.fetch(
        f"""
        SELECT id, event_name, user_id, anonymous_id, properties, received_at
        FROM events {where}
        ORDER BY received_at DESC
        LIMIT ${len(params)-1} OFFSET ${len(params)}
        """,
        *params,
    )

    records = [
        {
            "id":           r["id"],
            "event_name":   r["event_name"],
            "user_id":      r["user_id"],
            "anonymous_id": r["anonymous_id"],
            "properties":   dict(r["properties"]),
            "received_at":  _iso(r["received_at"]),
        }
        for r in rows
    ]
    return _respond(records, fmt, "events")


# ── Orders ────────────────────────────────────────────────────────────────────

@router.get("/warehouse/export/orders")
async def export_orders(
    since:  str | None = Query(None),
    until:  str | None = Query(None),
    fmt:    str        = Query("json"),
    limit:  int        = Query(50_000, ge=1, le=500_000),
    offset: int        = Query(0, ge=0),
    db:     asyncpg.Connection = Depends(get_org_db),
):
    params: list = []
    clauses: list[str] = []
    if since:
        params.append(since)
        clauses.append(f"order_date >= ${len(params)}::date")
    if until:
        params.append(until)
        clauses.append(f"order_date <= ${len(params)}::date")
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    params += [limit, offset]

    rows = await db.fetch(
        f"""
        SELECT order_id, order_date, customer_id, product_id, product_name,
               channel, quantity, price_per_unit, region, delivered
        FROM orders {where}
        ORDER BY order_date DESC
        LIMIT ${len(params)-1} OFFSET ${len(params)}
        """,
        *params,
    )

    records = [
        {
            "order_id":       r["order_id"],
            "order_date":     str(r["order_date"]),
            "customer_id":    r["customer_id"],
            "product_id":     r["product_id"],
            "product_name":   r["product_name"],
            "channel":        r["channel"],
            "quantity":       r["quantity"],
            "price_per_unit": float(r["price_per_unit"]) if r["price_per_unit"] else None,
            "region":         r["region"],
            "delivered":      r["delivered"],
        }
        for r in rows
    ]
    return _respond(records, fmt, "orders")


# ── Users ─────────────────────────────────────────────────────────────────────

@router.get("/warehouse/export/users")
async def export_users(
    fmt:    str = Query("json"),
    limit:  int = Query(50_000, ge=1, le=500_000),
    offset: int = Query(0, ge=0),
    db:     asyncpg.Connection = Depends(get_org_db),
):
    rows = await db.fetch(
        """
        WITH latest_traits AS (
            SELECT DISTINCT ON (user_id)
                user_id, properties AS traits
            FROM events
            WHERE user_id IS NOT NULL AND event_name = 'identify'
            ORDER BY user_id, received_at DESC
        ),
        stats AS (
            SELECT
                user_id,
                COUNT(*)         AS total_events,
                MIN(received_at) AS first_seen,
                MAX(received_at) AS last_seen
            FROM events
            WHERE user_id IS NOT NULL
            GROUP BY user_id
        )
        SELECT s.user_id, s.total_events, s.first_seen, s.last_seen,
               COALESCE(t.traits, '{}')::jsonb AS traits
        FROM stats s
        LEFT JOIN latest_traits t USING (user_id)
        ORDER BY s.last_seen DESC
        LIMIT $1 OFFSET $2
        """,
        limit, offset,
    )

    records = [
        {
            "user_id":      r["user_id"],
            "total_events": r["total_events"],
            "first_seen":   _iso(r["first_seen"]),
            "last_seen":    _iso(r["last_seen"]),
            "traits":       dict(r["traits"]) if r["traits"] else {},
        }
        for r in rows
    ]
    return _respond(records, fmt, "users")
