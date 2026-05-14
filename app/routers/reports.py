"""
Scheduled Custom Reports

GET    /api/reports                    — list reports
POST   /api/reports                    — create report
PATCH  /api/reports/{report_id}        — update (enabled/recipients)
DELETE /api/reports/{report_id}        — delete
POST   /api/reports/{report_id}/run    — run immediately
"""

from __future__ import annotations

from datetime import datetime, timezone

import asyncpg
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.audit_log import log_action
from app.deps import get_org_db, require_admin
from app.notifications import send_email

router = APIRouter()

VALID_METRICS = frozenset({"events_count", "revenue_total", "dau", "new_users", "churn_count"})
VALID_PERIODS  = frozenset({"daily", "weekly", "monthly"})

PERIOD_INTERVALS = {
    "daily":   "1 day",
    "weekly":  "7 days",
    "monthly": "30 days",
}


class CreateReport(BaseModel):
    name:       str         = Field(..., min_length=1, max_length=80)
    metric:     str
    period:     str
    recipients: list[str]   = Field(..., min_length=1)
    enabled:    bool        = True


class PatchReport(BaseModel):
    enabled:    bool | None   = None
    recipients: list[str] | None = None
    name:       str | None    = None


def _fmt(row: asyncpg.Record) -> dict:
    return {
        "id":          str(row["id"]),
        "name":        row["name"],
        "metric":      row["metric"],
        "period":      row["period"],
        "recipients":  list(row["recipients"]),
        "enabled":     row["enabled"],
        "last_run_at": row["last_run_at"].isoformat() if row["last_run_at"] else None,
        "created_at":  row["created_at"].isoformat(),
    }


async def _compute_metric(db: asyncpg.Connection, metric: str, period: str) -> str:
    interval = PERIOD_INTERVALS.get(period, "7 days")
    if metric == "events_count":
        val = await db.fetchval(
            f"SELECT COUNT(*) FROM events WHERE received_at > NOW() - INTERVAL '{interval}'"
        )
        return f"Events: {val:,}"
    if metric == "revenue_total":
        val = await db.fetchval(
            f"SELECT COALESCE(SUM((properties->>'amount')::numeric), 0) FROM orders WHERE created_at > NOW() - INTERVAL '{interval}'"
        )
        return f"Revenue: ${float(val or 0):,.2f}"
    if metric == "dau":
        val = await db.fetchval(
            "SELECT COUNT(DISTINCT user_id) FROM events WHERE received_at > NOW() - INTERVAL '1 day' AND user_id IS NOT NULL"
        )
        return f"DAU: {val:,}"
    if metric == "new_users":
        val = await db.fetchval(
            f"SELECT COUNT(DISTINCT user_id) FROM events WHERE received_at > NOW() - INTERVAL '{interval}' AND event_name = 'identify' AND user_id IS NOT NULL"
        )
        return f"New users: {val:,}"
    if metric == "churn_count":
        val = await db.fetchval(
            f"SELECT COUNT(DISTINCT user_id) FROM events WHERE user_id IS NOT NULL GROUP BY user_id HAVING MAX(received_at) < NOW() - INTERVAL '{interval}' LIMIT 1"
        )
        return f"At-risk users: {val or 0:,}"
    return f"{metric}: (unknown metric)"


@router.get("/reports")
async def list_reports(
    db:           asyncpg.Connection = Depends(get_org_db),
    current_user: dict = Depends(require_admin),   # contains recipient email addresses
):
    rows = await db.fetch("SELECT * FROM scheduled_reports ORDER BY created_at DESC")
    return [_fmt(r) for r in rows]


@router.post("/reports", status_code=201)
async def create_report(
    body:         CreateReport,
    db:           asyncpg.Connection = Depends(get_org_db),
    current_user: dict = Depends(require_admin),
):
    if body.metric not in VALID_METRICS:
        raise HTTPException(400, f"Invalid metric. Valid: {sorted(VALID_METRICS)}")
    if body.period not in VALID_PERIODS:
        raise HTTPException(400, f"Invalid period. Valid: {sorted(VALID_PERIODS)}")

    row = await db.fetchrow(
        """
        INSERT INTO scheduled_reports (org_id, name, metric, period, recipients, enabled, created_by)
        VALUES (current_setting('app.org_id')::uuid, $1, $2, $3, $4, $5, $6::uuid)
        RETURNING *
        """,
        body.name, body.metric, body.period, body.recipients,
        body.enabled, current_user["sub"],
    )
    return _fmt(row)


@router.patch("/reports/{report_id}")
async def update_report(
    report_id:    str,
    body:         PatchReport,
    db:           asyncpg.Connection = Depends(get_org_db),
    current_user: dict = Depends(require_admin),
):
    existing = await db.fetchrow("SELECT * FROM scheduled_reports WHERE id = $1::uuid", report_id)
    if not existing:
        raise HTTPException(404, "Report not found")

    enabled    = body.enabled    if body.enabled    is not None else existing["enabled"]
    recipients = body.recipients if body.recipients is not None else existing["recipients"]
    name       = body.name       if body.name       is not None else existing["name"]

    row = await db.fetchrow(
        "UPDATE scheduled_reports SET enabled=$2, recipients=$3, name=$4 WHERE id=$1::uuid RETURNING *",
        report_id, enabled, recipients, name,
    )
    return _fmt(row)


@router.delete("/reports/{report_id}", status_code=204)
async def delete_report(
    report_id:    str,
    db:           asyncpg.Connection = Depends(get_org_db),
    current_user: dict = Depends(require_admin),
):
    result = await db.execute("DELETE FROM scheduled_reports WHERE id = $1::uuid", report_id)
    if result == "DELETE 0":
        raise HTTPException(404, "Report not found")


@router.post("/reports/{report_id}/run")
async def run_report(
    report_id:    str,
    db:           asyncpg.Connection = Depends(get_org_db),
    current_user: dict = Depends(require_admin),
):
    report = await db.fetchrow("SELECT * FROM scheduled_reports WHERE id = $1::uuid", report_id)
    if not report:
        raise HTTPException(404, "Report not found")

    metric_str = await _compute_metric(db, report["metric"], report["period"])
    now_str    = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    body_text = (
        f"Analytiq Report: {report['name']}\n"
        f"Period: {report['period'].capitalize()}\n"
        f"Generated: {now_str}\n\n"
        f"{metric_str}\n"
    )

    sent_to = []
    for addr in report["recipients"]:
        try:
            ok = await send_email(
                to=[addr],
                subject=f"[Analytiq] {report['name']} — {report['period'].capitalize()} report",
                body=body_text,
            )
            if ok:
                sent_to.append(addr)
        except Exception:
            pass

    await db.execute(
        "UPDATE scheduled_reports SET last_run_at = NOW() WHERE id = $1::uuid", report_id
    )
    await log_action(db, current_user["sub"], "report.run",
                     resource_type="report", resource_id=report_id,
                     metadata={"name": report["name"], "metric": metric_str})

    return {"sent_to": sent_to, "metric": metric_str, "ran_at": now_str}
