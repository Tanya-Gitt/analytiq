"""
Export API — download dashboard data as CSV.

GET /api/export/segment-b?days=30[&channel=...][&format=csv]
GET /api/export/segment-a?days=30[&event_type=...][&format=csv]

Reuses the same SQL helpers as the dashboard endpoint so the numbers match
exactly what users see on screen.

Security:
  - Requires a valid JWT (same as dashboard endpoints).
  - RLS enforced via get_org_db dependency.
  - Responses include Content-Disposition: attachment so browsers download
    rather than display the file inline.
"""

from __future__ import annotations

import csv
import io

import asyncpg
from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse

from app.deps import get_org_db
from app.routers.dashboard import _fetch_segment_a_data, _fetch_segment_b_data

router = APIRouter()


def _to_csv(rows: list[dict]) -> str:
    """Serialise a list of flat dicts to a CSV string."""
    if not rows:
        return ""
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue()


def _csv_response(content: str, filename: str) -> StreamingResponse:
    return StreamingResponse(
        iter([content]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/export/segment-b")
async def export_segment_b(
    days: int = Query(default=30, ge=1, le=365),
    channel: str | None = Query(default=None),
    db: asyncpg.Connection = Depends(get_org_db),
):
    """
    Export Segment B (revenue / orders) data as CSV.
    Returns a ZIP-style multi-section CSV with all tables separated by blank lines.
    """
    data = await _fetch_segment_b_data(db, days, channel)

    sections: list[str] = []

    # Revenue trend
    sections.append("# Revenue Trend\n" + _to_csv(data["revenue_trend"]))

    # Top channels
    sections.append("# Top Channels\n" + _to_csv(data["top_channels"]))

    # Top products
    sections.append("# Top Products\n" + _to_csv(data["top_products"]))

    # AOV trend
    sections.append("# Average Order Value Trend\n" + _to_csv(data["aov_trend"]))

    # Revenue by region
    sections.append("# Revenue by Region\n" + _to_csv(data["revenue_by_region"]))

    # Summary KPIs
    summary = [
        {
            "metric": "total_revenue",
            "value": data["total_revenue"],
            "prev_value": data["prev_total_revenue"],
        },
        {
            "metric": "total_orders",
            "value": data["total_orders"],
            "prev_value": data["prev_total_orders"],
        },
        {
            "metric": "delivery_rate",
            "value": data["delivery_rate"] if data["delivery_rate"] is not None else "",
            "prev_value": "",
        },
    ]
    sections.append("# Summary KPIs\n" + _to_csv(summary))

    full_csv = "\n\n".join(sections)
    suffix = f"_channel_{channel}" if channel else ""
    return _csv_response(full_csv, f"segment_b_{days}d{suffix}.csv")


@router.get("/export/segment-a")
async def export_segment_a(
    days: int = Query(default=30, ge=1, le=365),
    event_type: str | None = Query(default=None),
    db: asyncpg.Connection = Depends(get_org_db),
):
    """
    Export Segment A (events / engagement) data as CSV.
    Returns a multi-section CSV with all tables separated by blank lines.
    """
    data = await _fetch_segment_a_data(db, days, event_type)

    sections: list[str] = []

    # Events timeline
    sections.append("# Events Timeline\n" + _to_csv(data["events_timeline"]))

    # Top events
    sections.append("# Top Events\n" + _to_csv(data["top_events"]))

    # Funnel
    sections.append("# Conversion Funnel\n" + _to_csv(data["funnel"]))

    # New vs returning
    sections.append("# New vs Returning Users\n" + _to_csv(data["new_vs_returning"]))

    # Summary KPIs
    summary = [
        {
            "metric": "total_events",
            "value": data["total_events"],
            "prev_value": data["prev_total_events"],
        },
        {
            "metric": "dau",
            "value": data["dau"] if data["dau"] is not None else "",
            "prev_value": "",
        },
    ]
    sections.append("# Summary KPIs\n" + _to_csv(summary))

    full_csv = "\n\n".join(sections)
    suffix = f"_event_{event_type}" if event_type else ""
    return _csv_response(full_csv, f"segment_a_{days}d{suffix}.csv")
