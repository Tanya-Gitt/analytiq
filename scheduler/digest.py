"""
Weekly email digest.

send_weekly_digest(pool) is called by the scheduler every Monday at 09:00 UTC.

For each org that has at least one user with an email address, it:
  1. Fetches 7-day Segment B summary (revenue, orders, delivery rate)
  2. Fetches 7-day Segment A summary (events, DAU)
  3. Sends a plain-text + HTML digest email to the org's admin user

If SMTP_HOST is not set, the function logs and returns silently — the same
behaviour as the alert notifier, so the scheduler never crashes over missing
SMTP config.
"""

from __future__ import annotations

import logging

import asyncpg

from app.routers.dashboard import _fetch_segment_a_data, _fetch_segment_b_data

from .notifications import send_email

logger = logging.getLogger(__name__)


# ── HTML template ─────────────────────────────────────────────────────────────

def _build_html(
    org_name: str,
    seg_b: dict,
    seg_a: dict,
) -> str:
    def money(v: float) -> str:
        if v >= 1_000_000:
            return f"${v / 1_000_000:.2f}M"
        if v >= 1_000:
            return f"${v / 1_000:.1f}K"
        return f"${v:.2f}"

    def pct(v: float | None) -> str:
        return f"{v * 100:.1f}%" if v is not None else "—"

    def chg(curr: float, prev: float) -> str:
        if prev == 0:
            return ""
        c = ((curr - prev) / prev) * 100
        arrow = "↑" if c >= 0 else "↓"
        color = "#16a34a" if c >= 0 else "#dc2626"
        return f' <span style="color:{color};font-size:12px">{arrow} {abs(c):.1f}%</span>'

    b_rev_chg = chg(seg_b["total_revenue"], seg_b["prev_total_revenue"])
    b_ord_chg = chg(seg_b["total_orders"],  seg_b["prev_total_orders"])
    a_evt_chg = chg(seg_a["total_events"],  seg_a["prev_total_events"])

    dau = seg_a["dau"]
    dau_str = f"{dau:,.0f}" if dau is not None else "—"

    top_products = seg_b["top_products"][:3]
    products_html = "".join(
        f"<li style='margin:4px 0'>{p['product_name']} — {money(p['revenue'])} "
        f"({p['units_sold']:,} units)</li>"
        for p in top_products
    ) or "<li>No product data</li>"

    top_events = seg_a["top_events"][:3]
    events_html = "".join(
        f"<li style='margin:4px 0'>{e['event_name']} — {e['count']:,}</li>"
        for e in top_events
    ) or "<li>No event data</li>"

    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family:system-ui,sans-serif;color:#111;max-width:600px;margin:0 auto;padding:24px">
  <h2 style="color:#4f46e5;margin-bottom:4px">Weekly Analytics Digest</h2>
  <p style="color:#6b7280;font-size:14px;margin-top:0">{org_name} — last 7 days</p>
  <hr style="border:none;border-top:1px solid #e5e7eb;margin:16px 0">

  <h3 style="font-size:15px;color:#374151;margin-bottom:12px">E-commerce (Segment B)</h3>
  <table style="width:100%;border-collapse:collapse;font-size:14px">
    <tr>
      <td style="padding:8px;background:#f9fafb;border:1px solid #e5e7eb;font-weight:600">Revenue</td>
      <td style="padding:8px;border:1px solid #e5e7eb">{money(seg_b["total_revenue"])}{b_rev_chg}</td>
    </tr>
    <tr>
      <td style="padding:8px;background:#f9fafb;border:1px solid #e5e7eb;font-weight:600">Orders</td>
      <td style="padding:8px;border:1px solid #e5e7eb">{seg_b["total_orders"]:,}{b_ord_chg}</td>
    </tr>
    <tr>
      <td style="padding:8px;background:#f9fafb;border:1px solid #e5e7eb;font-weight:600">Delivery rate</td>
      <td style="padding:8px;border:1px solid #e5e7eb">{pct(seg_b["delivery_rate"])}</td>
    </tr>
  </table>
  <p style="font-size:13px;color:#6b7280;margin-top:8px"><strong>Top products:</strong></p>
  <ul style="font-size:13px;color:#374151;margin-top:0;padding-left:20px">{products_html}</ul>

  <hr style="border:none;border-top:1px solid #e5e7eb;margin:16px 0">

  <h3 style="font-size:15px;color:#374151;margin-bottom:12px">Product Events (Segment A)</h3>
  <table style="width:100%;border-collapse:collapse;font-size:14px">
    <tr>
      <td style="padding:8px;background:#f9fafb;border:1px solid #e5e7eb;font-weight:600">Total events</td>
      <td style="padding:8px;border:1px solid #e5e7eb">{seg_a["total_events"]:,}{a_evt_chg}</td>
    </tr>
    <tr>
      <td style="padding:8px;background:#f9fafb;border:1px solid #e5e7eb;font-weight:600">Avg DAU</td>
      <td style="padding:8px;border:1px solid #e5e7eb">{dau_str}</td>
    </tr>
  </table>
  <p style="font-size:13px;color:#6b7280;margin-top:8px"><strong>Top events:</strong></p>
  <ul style="font-size:13px;color:#374151;margin-top:0;padding-left:20px">{events_html}</ul>

  <hr style="border:none;border-top:1px solid #e5e7eb;margin:16px 0">
  <p style="font-size:12px;color:#9ca3af">
    You are receiving this because you are an admin of the <strong>{org_name}</strong>
    organisation on the Analytics Platform.
  </p>
</body>
</html>"""


def _build_plain(org_name: str, seg_b: dict, seg_a: dict) -> str:
    def money(v: float) -> str:
        if v >= 1_000_000:
            return f"${v / 1_000_000:.2f}M"
        if v >= 1_000:
            return f"${v / 1_000:.1f}K"
        return f"${v:.2f}"

    dau = seg_a["dau"]
    dau_str = f"{dau:,.0f}" if dau is not None else "—"
    dr = seg_b["delivery_rate"]
    dr_str = f"{dr * 100:.1f}%" if dr is not None else "—"

    lines = [
        f"Weekly Analytics Digest — {org_name} — last 7 days",
        "",
        "E-COMMERCE (SEGMENT B)",
        f"  Revenue:       {money(seg_b['total_revenue'])}",
        f"  Orders:        {seg_b['total_orders']:,}",
        f"  Delivery rate: {dr_str}",
    ]
    if seg_b["top_products"]:
        lines.append("  Top products:")
        for p in seg_b["top_products"][:3]:
            lines.append(f"    - {p['product_name']} {money(p['revenue'])} ({p['units_sold']:,} units)")

    lines += [
        "",
        "PRODUCT EVENTS (SEGMENT A)",
        f"  Total events: {seg_a['total_events']:,}",
        f"  Avg DAU:      {dau_str}",
    ]
    if seg_a["top_events"]:
        lines.append("  Top events:")
        for e in seg_a["top_events"][:3]:
            lines.append(f"    - {e['event_name']}: {e['count']:,}")

    return "\n".join(lines)


# ── main entry point ──────────────────────────────────────────────────────────

async def send_weekly_digest(pool: asyncpg.Pool) -> None:
    """
    Called by the scheduler every Monday at 09:00 UTC.

    Queries all orgs that have at least one user with an email address,
    fetches 7-day dashboard data for each org, and sends a digest email.
    """
    logger.info("Weekly digest: starting run")

    # Fetch all orgs with at least one user
    async with pool.acquire() as conn:
        orgs = await conn.fetch(
            """
            SELECT o.id AS org_id, o.name AS org_name,
                   u.email AS admin_email
            FROM   orgs o
            JOIN   users u ON u.org_id = o.id
            ORDER  BY o.id, u.created_at
            """
        )

    # De-duplicate: one email per org (first registered user)
    seen: set[str] = set()
    targets: list[dict] = []
    for row in orgs:
        org_id = str(row["org_id"])
        if org_id not in seen:
            seen.add(org_id)
            targets.append(dict(row))

    if not targets:
        logger.info("Weekly digest: no orgs found, nothing to send")
        return

    logger.info("Weekly digest: sending to %d org(s)", len(targets))

    for org in targets:
        org_id = str(org["org_id"])
        org_name = org["org_name"]
        email = org["admin_email"]

        try:
            async with pool.acquire() as conn:
                # RLS: set org context so queries are scoped to this org
                async with conn.transaction():
                    await conn.execute("SET LOCAL ROLE app_role")
                    await conn.execute(f"SET LOCAL app.org_id = '{org_id}'")
                    seg_b = await _fetch_segment_b_data(conn, days=7)
                    seg_a = await _fetch_segment_a_data(conn, days=7)

            subject = f"Your weekly analytics digest — {org_name}"
            plain   = _build_plain(org_name, seg_b, seg_a)
            html    = _build_html(org_name, seg_b, seg_a)

            await send_email(email, subject, plain, html_body=html)
            logger.info("Weekly digest: sent to %s (%s)", email, org_name)

        except Exception:  # noqa: BLE001
            logger.exception(
                "Weekly digest: failed for org %s (%s)", org_id, org_name
            )

    logger.info("Weekly digest: run complete")
