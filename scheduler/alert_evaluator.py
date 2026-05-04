"""
Alert FSM evaluator.

evaluate_alerts(pool) → None

Loads all active alert rules grouped by (org_id, metric), evaluates each
metric once per org (batch — avoids N+1), then applies per-rule FSM:

  OK  → TRIGGERED  : condition met for first time → fire notification
  TRIGGERED → OK   : condition no longer met → fire "resolved" notification
  TRIGGERED (unchanged) : condition still met, re-fire only after 24 h cooldown

Notifications:
  slack  : HTTP POST to destination (webhook URL)
  email  : SMTP via smtplib (sync, run in executor); skipped gracefully if
           SMTP_HOST env var is absent.
"""

from __future__ import annotations

import asyncio
import logging
import os
import smtplib
import ssl
from datetime import datetime, timezone
from email.message import EmailMessage
from typing import Any

import asyncpg
import httpx

from .metrics import evaluate_metric

logger = logging.getLogger(__name__)

_REFIRE_HOURS = 24  # re-send a still-triggered alert after this many hours


# ── notification dispatch ─────────────────────────────────────────────────────

async def _send_slack(webhook_url: str, text: str) -> None:
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(webhook_url, json={"text": text})
            if resp.status_code != 200:
                logger.warning(
                    "Slack webhook returned %d: %s", resp.status_code, resp.text[:200]
                )
    except Exception:  # noqa: BLE001
        logger.exception("Failed to send Slack notification")


def _send_email_sync(
    to_addr: str,
    subject: str,
    body: str,
) -> None:
    """Send email via SMTP. Runs in a thread executor (smtplib is sync)."""
    smtp_host = os.environ.get("SMTP_HOST", "")
    if not smtp_host:
        logger.info("SMTP_HOST not set — skipping email notification to %s", to_addr)
        return

    smtp_port = int(os.environ.get("SMTP_PORT", "587"))
    smtp_user = os.environ.get("SMTP_USER", "")
    smtp_pass = os.environ.get("SMTP_PASS", "")
    smtp_from = os.environ.get("SMTP_FROM", smtp_user)

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = smtp_from
    msg["To"] = to_addr
    msg.set_content(body)

    context = ssl.create_default_context()
    try:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=15) as smtp:
            smtp.ehlo()
            smtp.starttls(context=context)
            if smtp_user:
                smtp.login(smtp_user, smtp_pass)
            smtp.send_message(msg)
        logger.info("Email sent to %s: %s", to_addr, subject)
    except Exception:  # noqa: BLE001
        logger.exception("Failed to send email to %s", to_addr)


async def _notify(rule: dict[str, Any], subject: str, body: str) -> None:
    channel = rule["channel"]
    destination = rule["destination"]

    if channel == "slack":
        await _send_slack(destination, f"*{subject}*\n{body}")
    elif channel == "email":
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None, _send_email_sync, destination, subject, body
        )
    else:
        logger.warning("Unknown notification channel %r for rule %s", channel, rule["id"])


# ── FSM helpers ───────────────────────────────────────────────────────────────

def _condition_met(rule: dict[str, Any], value: float | None) -> bool:
    condition = rule["condition"]
    threshold = rule["threshold"]

    if condition == "no_data":
        return value is None
    if value is None:
        return False
    if condition == "below":
        return value < float(threshold)
    if condition == "above":
        return value > float(threshold)
    return False


def _should_refire(rule: dict[str, Any]) -> bool:
    """True if TRIGGERED rule has been silent for ≥ _REFIRE_HOURS."""
    last = rule["last_triggered_at"]
    if last is None:
        return True
    now = datetime.now(timezone.utc)
    # last_triggered_at may come back as naive UTC from asyncpg
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    delta_hours = (now - last).total_seconds() / 3600
    return delta_hours >= _REFIRE_HOURS


# ── main evaluator ────────────────────────────────────────────────────────────

async def evaluate_alerts(pool: asyncpg.Pool) -> None:
    """
    Load all alert rules, evaluate metrics in batches (one DB query per
    unique (org_id, metric) pair), then apply the FSM and fire notifications.
    """
    async with pool.acquire() as conn:
        rules = await conn.fetch(
            """
            SELECT id, org_id, name, metric, condition, threshold,
                   window_hours, channel, destination, state, last_triggered_at
            FROM   alert_rules
            ORDER  BY org_id, metric
            """
        )

    if not rules:
        return

    # ── batch: evaluate each unique (org_id, metric) once ─────────────────
    metric_values: dict[tuple[str, str], float | None] = {}

    # Collect unique pairs first
    pairs: set[tuple[str, str]] = set()
    for rule in rules:
        pairs.add((str(rule["org_id"]), rule["metric"]))

    async with pool.acquire() as conn:
        for org_id, metric in pairs:
            # Determine window_hours — use the max window among rules for this
            # org+metric so we don't under-sample for longer-window rules.
            window_hours = max(
                rule["window_hours"]
                for rule in rules
                if str(rule["org_id"]) == org_id and rule["metric"] == metric
            )
            # RLS: set org context
            async with conn.transaction():
                await conn.execute(f"SET LOCAL app.org_id = '{str(org_id)}'")
                value = await evaluate_metric(conn, org_id, metric, window_hours)
            metric_values[(org_id, metric)] = value

    # ── FSM transitions ────────────────────────────────────────────────────
    for rule in rules:
        rule_dict = dict(rule)
        org_id = str(rule_dict["org_id"])
        metric = rule_dict["metric"]
        value = metric_values.get((org_id, metric))
        current_state = rule_dict["state"]
        met = _condition_met(rule_dict, value)

        new_state = current_state
        should_notify = False
        notification_kind = "triggered"

        if current_state == "OK" and met:
            new_state = "TRIGGERED"
            should_notify = True
            notification_kind = "triggered"

        elif current_state == "TRIGGERED" and not met:
            new_state = "OK"
            should_notify = True
            notification_kind = "resolved"

        elif current_state == "TRIGGERED" and met and _should_refire(rule_dict):
            # Stay TRIGGERED, but re-fire the notification
            should_notify = True
            notification_kind = "triggered"

        # Persist state change
        if new_state != current_state or (should_notify and notification_kind == "triggered"):
            async with pool.acquire() as conn:
                await conn.execute(
                    """
                    UPDATE alert_rules
                    SET state             = $2,
                        last_triggered_at = CASE WHEN $3 THEN NOW() ELSE last_triggered_at END
                    WHERE id = $1
                    """,
                    rule_dict["id"],
                    new_state,
                    notification_kind == "triggered" and should_notify,
                )

        # Fire notification
        if should_notify:
            value_str = f"{value:.4g}" if value is not None else "no data"
            if notification_kind == "triggered":
                subject = f"[ALERT] {rule_dict['name']}"
                body = (
                    f"Metric '{metric}' is {value_str} "
                    f"(condition: {rule_dict['condition']} {rule_dict['threshold']})"
                )
            else:
                subject = f"[RESOLVED] {rule_dict['name']}"
                body = (
                    f"Metric '{metric}' is back to normal ({value_str}). "
                    f"Alert '{rule_dict['name']}' is resolved."
                )

            await _notify(rule_dict, subject, body)
