#!/usr/bin/env python3
"""
Seed the Analytiq Demo org with 365 days of realistic product analytics data.

Usage:
    python scripts/seed_demo.py              # seed (skip if demo org exists)
    python scripts/seed_demo.py --reset      # drop demo org and re-seed
    DATABASE_URL=postgresql://... python scripts/seed_demo.py

What gets created:
    • 1 demo org + 1 admin user (read-only via /api/auth/demo-login)
    • ~150,000 events  across 365 days (realistic growth + seasonality)
    • ~8,000 orders     with Starter / Pro / Enterprise pricing
    • ~12,000 heatmap   click + scroll events across 6 key pages
    • 600 unique users  across 4 activity cohorts (power / regular / occasional / churned)
    • 3 connectors      (Stripe active, CSV active, Webhook paused)
    • 3 alert rules     (DAU, revenue, error-rate)
    • 2 funnels         (Signup→Paid, Feature Adoption)
    • 5 feature flags   (ai_copilot, dark_mode, new_dashboard, bulk_export, pdf_reports)
    • 6 annotations     (Beta launch, Product Hunt, TechCrunch, pricing update, v2.0, partnership)
    • 5 anomaly events  (traffic spikes + revenue dips)
    • 2 scheduled reports
    • 3 API keys
    • Audit log entries for all admin actions

Credentials:
    Email:    demo@analytiq.io
    Password: DemoAnalytiq2024!
    Or just hit  POST /api/auth/demo-login  — no password needed.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import random
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import asyncpg
import bcrypt

# ── Config ────────────────────────────────────────────────────────────────────

DEMO_ORG_NAME  = "Analytiq Demo"
DEMO_EMAIL     = os.environ.get("DEMO_EMAIL",    "demo@analytiq.io")
DEMO_PASSWORD  = os.environ.get("DEMO_PASSWORD", "DemoAnalytiq2024!")

ROOT = Path(__file__).parent.parent

rng = random.Random(42)   # deterministic so re-runs produce the same data

NOW   = datetime.now(timezone.utc)
START = NOW - timedelta(days=365)


# ── Helpers ───────────────────────────────────────────────────────────────────

def days_ago(n: int) -> datetime:
    return NOW - timedelta(days=n)


def ts(dt: datetime) -> str:
    return dt.isoformat()


def jitter(dt: datetime, max_seconds: int = 3600) -> datetime:
    return dt + timedelta(seconds=rng.randint(0, max_seconds))


# ── User cohorts ──────────────────────────────────────────────────────────────
# 600 unique external user IDs (these are your customers' user IDs, not DB rows)

POWER_USERS      = [f"usr_power_{i:03d}"      for i in range(1,  51)]   # 50
REGULAR_USERS    = [f"usr_regular_{i:03d}"    for i in range(1, 201)]   # 200
OCCASIONAL_USERS = [f"usr_occasional_{i:03d}" for i in range(1, 251)]   # 250
CHURNED_USERS    = [f"usr_churned_{i:03d}"    for i in range(1, 101)]   # 100

ALL_ACTIVE_USERS = POWER_USERS + REGULAR_USERS + OCCASIONAL_USERS


# ── Event / page metadata ─────────────────────────────────────────────────────

PAGES = [
    "/",
    "/dashboard",
    "/events",
    "/funnels",
    "/people",
    "/settings",
    "/pricing",
    "/docs",
    "/blog",
]

FEATURES = [
    "funnel_builder",
    "retention_chart",
    "cohort_analysis",
    "ai_copilot",
    "data_export",
    "custom_dashboard",
    "alert_builder",
    "heatmap_viewer",
]

BROWSERS    = ["Chrome", "Firefox", "Safari", "Edge"]
PLATFORMS   = ["web", "mobile_web"]
COUNTRIES   = ["IN", "US", "GB", "DE", "SG", "AU", "CA", "FR"]
UTM_SOURCES = ["google", "linkedin", "twitter", "direct", "referral", "email"]
UTM_MEDIUMS = ["cpc", "organic", "social", "email", "referral"]
PLANS       = ["starter", "pro", "enterprise"]
PLAN_PRICES = {"starter": 29.0, "pro": 79.0, "enterprise": 299.0}
PLAN_ANNUAL = {"starter": 290.0, "pro": 790.0, "enterprise": 2990.0}


# ── Growth + seasonality model ────────────────────────────────────────────────

# 5 special events that cause traffic spikes
SPIKE_DAYS = {
    300: ("Beta launch 🚀",          4.5),
    210: ("Product Hunt #1 🏆",      7.0),
    160: ("TechCrunch coverage 📰",  5.0),
    90:  ("Pricing update 💰",       0.7),   # dip, not spike
    30:  ("v2.0 Release 🎉",         6.0),
    7:   ("Enterprise partnership",  3.5),
}


def daily_volume(day_index: int) -> int:
    """
    Base event volume for a given day (0 = 365 days ago, 364 = today).

    Grows from ~100 to ~600 via a smooth S-curve, with weekly seasonality
    and five named spike events applied on top.
    """
    # S-curve growth: slow start, acceleration at midpoint, plateau near end
    t       = day_index / 364.0
    base    = 100 + 500 * (1 / (1 + math.exp(-8 * (t - 0.45))))

    # Weekly seasonality: weekends quieter
    dt      = START + timedelta(days=day_index)
    dow     = dt.weekday()   # 0=Mon … 6=Sun
    seasonal_factor = {0: 1.00, 1: 1.05, 2: 1.00, 3: 0.95,
                       4: 0.85, 5: 0.60, 6: 0.50}[dow]

    # Spike/dip events: days_ago is (364 - day_index)
    days_remaining = 364 - day_index
    spike_factor   = 1.0
    for spike_day, (_, mult) in SPIKE_DAYS.items():
        dist = abs(days_remaining - spike_day)
        if dist <= 1:
            spike_factor = max(spike_factor, mult * (1.0 if dist == 0 else 0.5))

    # Random daily noise ±12 %
    noise = rng.uniform(0.88, 1.12)

    return max(20, int(base * seasonal_factor * spike_factor * noise))


def daily_revenue(day_index: int) -> float:
    """MRR proxy: grows from ~$200/day to ~$2,500/day."""
    t = day_index / 364.0
    return 200 + 2300 * (1 / (1 + math.exp(-7 * (t - 0.5))))


def order_count(day_index: int) -> int:
    t = day_index / 364.0
    base = 3 + 22 * t
    return max(1, int(base * rng.uniform(0.7, 1.3)))


# ── Event generators ──────────────────────────────────────────────────────────

_EVENT_TYPE_WEIGHTS = [
    ("page_view",           38),
    ("button_click",        20),
    ("identify",             6),
    ("search",               8),
    ("feature_used",        12),
    ("purchase",             3),
    ("signup",               3),
    ("error",                2),
    ("video_play",           4),
    ("onboarding_complete",  4),
]
_EVENT_NAMES, _EVENT_WEIGHTS = zip(*_EVENT_TYPE_WEIGHTS)


def _pick_user(day_index: int) -> str:
    """
    Pick a user for an event.  Churned users only appear in the first 270 days.
    Power users are over-represented (they're more active).
    """
    days_remaining = 364 - day_index
    pool: list[str]
    if days_remaining > 70:
        pool = (POWER_USERS * 6) + (REGULAR_USERS * 3) + OCCASIONAL_USERS + (CHURNED_USERS * 2)
    else:
        pool = (POWER_USERS * 8) + (REGULAR_USERS * 4) + OCCASIONAL_USERS
    return rng.choice(pool)


def _make_event(org_id: str, day_index: int) -> dict:
    dt = START + timedelta(days=day_index)
    dt = jitter(dt, max_seconds=86399)

    event_name = rng.choices(_EVENT_NAMES, weights=_EVENT_WEIGHTS, k=1)[0]
    user_id    = _pick_user(day_index)

    props: dict = {
        "platform":   rng.choice(PLATFORMS),
        "browser":    rng.choice(BROWSERS),
        "country":    rng.choice(COUNTRIES),
    }

    if event_name == "page_view":
        page = rng.choice(PAGES)
        props.update({
            "page":       page,
            "utm_source": rng.choice(UTM_SOURCES) if rng.random() < 0.4 else None,
            "utm_medium": rng.choice(UTM_MEDIUMS) if rng.random() < 0.4 else None,
            "duration_s": rng.randint(5, 420),
        })
    elif event_name == "feature_used":
        props["feature"] = rng.choice(FEATURES)
        props["duration_ms"] = rng.randint(200, 8000)
    elif event_name == "identify":
        props.update({
            "plan":  rng.choice(PLANS),
            "trial": rng.random() < 0.3,
        })
    elif event_name == "signup":
        props.update({
            "plan":       rng.choice(PLANS),
            "utm_source": rng.choice(UTM_SOURCES),
        })
    elif event_name == "search":
        terms = ["retention", "funnel", "cohort", "export", "alert", "dashboard", "api", "team"]
        props["query"] = rng.choice(terms)
        props["results"] = rng.randint(0, 15)
    elif event_name == "error":
        codes = ["404", "500", "422", "403"]
        props.update({
            "code":    rng.choice(codes),
            "page":    rng.choice(PAGES),
            "message": "Unexpected error occurred",
        })
    elif event_name == "purchase":
        plan  = rng.choice(PLANS)
        annual = rng.random() < 0.35
        props.update({
            "plan":    plan,
            "amount":  PLAN_ANNUAL[plan] if annual else PLAN_PRICES[plan],
            "billing": "annual" if annual else "monthly",
        })
    elif event_name == "video_play":
        props.update({
            "video":    rng.choice(["intro_tour", "funnel_demo", "api_walkthrough", "case_study"]),
            "duration": rng.randint(30, 600),
            "watched_s": rng.randint(10, 600),
        })

    return {
        "org_id":       org_id,
        "event_name":   event_name,
        "user_id":      user_id,
        "anonymous_id": None,
        "properties":   props,
        "received_at":  dt,
    }


def _make_order(org_id: str, day_index: int) -> dict:
    dt     = START + timedelta(days=day_index)
    dt     = jitter(dt, max_seconds=86399)
    plan   = rng.choices(PLANS, weights=[50, 35, 15], k=1)[0]
    annual = rng.random() < 0.30
    amount = PLAN_ANNUAL[plan] if annual else PLAN_PRICES[plan]
    user_id = rng.choice(ALL_ACTIVE_USERS)

    return {
        "org_id":    org_id,
        "user_id":   user_id,
        "properties": {
            "plan":    plan,
            "amount":  amount,
            "billing": "annual" if annual else "monthly",
            "country": rng.choice(COUNTRIES),
            "stripe_charge_id": f"ch_{uuid.uuid4().hex[:20]}",
        },
        "created_at": dt,
    }


def _make_heatmap_event(org_id: str, day_index: int) -> dict:
    dt = START + timedelta(days=day_index)
    dt = jitter(dt, max_seconds=86399)
    etype = rng.choices(["click", "scroll"], weights=[60, 40], k=1)[0]
    pages = ["/", "/dashboard", "/events", "/funnels", "/pricing", "/docs"]

    return {
        "org_id":     org_id,
        "page_url":   rng.choice(pages),
        "event_type": etype,
        "x_pct":      rng.randint(0, 100) if etype == "click" else None,
        "y_pct":      rng.randint(0, 100),
        "element":    rng.choice(["button.cta", "a.nav-link", "div.card", "input.search"]) if etype == "click" else None,
        "user_id":    rng.choice(ALL_ACTIVE_USERS),
        "received_at": dt,
    }


# ── Main seeder ───────────────────────────────────────────────────────────────

async def seed(pool: asyncpg.Pool, reset: bool = False) -> None:

    # ── 0. Check / reset demo org ─────────────────────────────────────────────
    async with pool.acquire() as conn:
        existing_org = await conn.fetchval(
            "SELECT id FROM orgs WHERE name = $1", DEMO_ORG_NAME
        )

        if existing_org and not reset:
            print(f"[seed] Demo org already exists ({existing_org}). Use --reset to re-seed.")
            return

        if existing_org and reset:
            print(f"[seed] --reset: deleting existing demo org {existing_org} …")
            await conn.execute("DELETE FROM orgs WHERE id = $1", existing_org)
            print("[seed] old demo org deleted.")

    # ── 1. Create org + admin user ────────────────────────────────────────────
    print("[seed] creating demo org + user …")
    pw_hash = bcrypt.hashpw(DEMO_PASSWORD.encode(), bcrypt.gensalt(rounds=10)).decode()

    async with pool.acquire() as conn:
        async with conn.transaction():
            org = await conn.fetchrow(
                "INSERT INTO orgs (name) VALUES ($1) RETURNING id, api_key",
                DEMO_ORG_NAME,
            )
            org_id  = str(org["id"])
            api_key = org["api_key"]

            user = await conn.fetchrow(
                """
                INSERT INTO users (org_id, email, password_hash, role)
                VALUES ($1::uuid, $2, $3, 'admin')
                RETURNING id
                """,
                org_id, DEMO_EMAIL, pw_hash,
            )
            user_id = str(user["id"])

    print(f"[seed] org_id={org_id}  user_id={user_id}")

    # ── helper: run with org context ─────────────────────────────────────────
    # All subsequent inserts go through a connection with app.org_id set so
    # RLS policies are satisfied.

    async def with_org(conn: asyncpg.Connection) -> None:
        await conn.execute(f"SET LOCAL app.org_id = '{org_id}'")

    # ── 2. Events (≈150k rows, inserted in batches) ───────────────────────────
    print("[seed] generating events (365 days) …")
    batch: list[tuple] = []
    total_events = 0

    INSERT_EVENTS = """
        INSERT INTO events (org_id, event_name, user_id, anonymous_id, properties, received_at)
        VALUES ($1::uuid, $2, $3, $4, $5, $6)
    """

    async with pool.acquire() as conn:
        async with conn.transaction():
            await with_org(conn)
            for day in range(365):
                n = daily_volume(day)
                for _ in range(n):
                    e = _make_event(org_id, day)
                    batch.append((
                        e["org_id"], e["event_name"], e["user_id"],
                        e["anonymous_id"], json.dumps(e["properties"]), e["received_at"],
                    ))
                    if len(batch) >= 500:
                        await conn.executemany(INSERT_EVENTS, batch)
                        total_events += len(batch)
                        batch.clear()
            if batch:
                await conn.executemany(INSERT_EVENTS, batch)
                total_events += len(batch)
                batch.clear()

    print(f"[seed] ✓ {total_events:,} events inserted")

    # ── 3. Orders ─────────────────────────────────────────────────────────────
    print("[seed] generating orders …")
    order_batch: list[tuple] = []
    total_orders = 0

    INSERT_ORDERS = """
        INSERT INTO orders (org_id, user_id, properties, created_at)
        VALUES ($1::uuid, $2, $3, $4)
    """

    async with pool.acquire() as conn:
        async with conn.transaction():
            await with_org(conn)
            for day in range(365):
                for _ in range(order_count(day)):
                    o = _make_order(org_id, day)
                    order_batch.append((
                        o["org_id"], o["user_id"],
                        json.dumps(o["properties"]), o["created_at"],
                    ))
                    if len(order_batch) >= 500:
                        await conn.executemany(INSERT_ORDERS, order_batch)
                        total_orders += len(order_batch)
                        order_batch.clear()
            if order_batch:
                await conn.executemany(INSERT_ORDERS, order_batch)
                total_orders += len(order_batch)
                order_batch.clear()

    print(f"[seed] ✓ {total_orders:,} orders inserted")

    # ── 4. Heatmap events ─────────────────────────────────────────────────────
    print("[seed] generating heatmap events …")
    hm_batch: list[tuple] = []
    total_hm = 0

    INSERT_HM = """
        INSERT INTO heatmap_events (org_id, page_url, event_type, x_pct, y_pct, element, user_id, received_at)
        VALUES ($1::uuid, $2, $3, $4, $5, $6, $7, $8)
    """

    async with pool.acquire() as conn:
        async with conn.transaction():
            await with_org(conn)
            # ~33 heatmap events per day = ~12,000 total
            for day in range(365):
                for _ in range(rng.randint(20, 50)):
                    h = _make_heatmap_event(org_id, day)
                    hm_batch.append((
                        h["org_id"], h["page_url"], h["event_type"],
                        h["x_pct"], h["y_pct"], h["element"],
                        h["user_id"], h["received_at"],
                    ))
                    if len(hm_batch) >= 500:
                        await conn.executemany(INSERT_HM, hm_batch)
                        total_hm += len(hm_batch)
                        hm_batch.clear()
            if hm_batch:
                await conn.executemany(INSERT_HM, hm_batch)
                total_hm += len(hm_batch)
                hm_batch.clear()

    print(f"[seed] ✓ {total_hm:,} heatmap events inserted")

    # ── 5. Connectors ─────────────────────────────────────────────────────────
    print("[seed] creating connectors …")
    async with pool.acquire() as conn:
        async with conn.transaction():
            await with_org(conn)
            await conn.executemany(
                """
                INSERT INTO connectors (org_id, type, name, config, status, last_synced_at)
                VALUES ($1::uuid, $2, $3, $4, $5, $6)
                """,
                [
                    (
                        org_id, "stripe", "Stripe Production",
                        json.dumps({"publishable_key": "pk_live_demo_****", "mode": "live"}),
                        "active", days_ago(1),
                    ),
                    (
                        org_id, "csv", "Monthly Cohort CSV",
                        json.dumps({"url": "https://example.com/cohorts.csv", "schedule": "weekly"}),
                        "active", days_ago(3),
                    ),
                    (
                        org_id, "webhook", "Zapier Webhook",
                        json.dumps({"endpoint": "https://hooks.zapier.com/demo", "events": ["purchase", "signup"]}),
                        "paused", days_ago(14),
                    ),
                ],
            )
    print("[seed] ✓ 3 connectors")

    # ── 6. Alert rules ────────────────────────────────────────────────────────
    print("[seed] creating alert rules …")
    async with pool.acquire() as conn:
        async with conn.transaction():
            await with_org(conn)
            await conn.executemany(
                """
                INSERT INTO alert_rules (org_id, name, metric, operator, threshold, period_minutes, channels, enabled)
                VALUES ($1::uuid, $2, $3, $4, $5, $6, $7, $8)
                """,
                [
                    (
                        org_id, "DAU drops below 30", "dau", "lt", 30, 1440,
                        json.dumps(["email"]), True,
                    ),
                    (
                        org_id, "Daily revenue below $200", "revenue_total", "lt", 200, 1440,
                        json.dumps(["email", "slack"]), True,
                    ),
                    (
                        org_id, "Error rate above 5%", "error_rate", "gt", 5, 60,
                        json.dumps(["slack"]), True,
                    ),
                ],
            )
    print("[seed] ✓ 3 alert rules")

    # ── 7. Funnels ────────────────────────────────────────────────────────────
    print("[seed] creating funnels …")
    async with pool.acquire() as conn:
        async with conn.transaction():
            await with_org(conn)
            await conn.executemany(
                """
                INSERT INTO funnels (org_id, name, steps)
                VALUES ($1::uuid, $2, $3)
                """,
                [
                    (
                        org_id,
                        "Signup to Paid Conversion",
                        json.dumps(["page_view", "signup", "onboarding_complete", "purchase"]),
                    ),
                    (
                        org_id,
                        "Feature Adoption",
                        json.dumps(["signup", "feature_used", "feature_used", "purchase"]),
                    ),
                ],
            )
    print("[seed] ✓ 2 funnels")

    # ── 8. Feature flags ──────────────────────────────────────────────────────
    print("[seed] creating feature flags …")
    flags = [
        ("ai_copilot_beta",   "AI Copilot (beta)",                    True,  25,
         [{"attribute": "plan", "operator": "eq", "value": "enterprise"}]),
        ("new_dashboard_v2",  "Redesigned dashboard layout",          True,  75, []),
        ("dark_mode",         "Dark mode UI",                         True,  50, []),
        ("bulk_export",       "Bulk data export (beta)",              True,  10,
         [{"attribute": "plan", "operator": "neq", "value": "starter"}]),
        ("pdf_reports",       "PDF scheduled report attachments",     True, 100, []),
    ]
    async with pool.acquire() as conn:
        async with conn.transaction():
            await with_org(conn)
            await conn.executemany(
                """
                INSERT INTO feature_flags (org_id, name, description, enabled, rollout_pct, targeting)
                VALUES ($1::uuid, $2, $3, $4, $5, $6)
                """,
                [
                    (org_id, name, desc, enabled, pct, json.dumps(targeting))
                    for name, desc, enabled, pct, targeting in flags
                ],
            )
    print(f"[seed] ✓ {len(flags)} feature flags")

    # ── 9. Annotations ────────────────────────────────────────────────────────
    print("[seed] creating annotations …")
    annotation_data = [
        (300, "A", "Beta launch 🚀",             "#10b981"),
        (210, "A", "Product Hunt #1 🏆",          "#f59e0b"),
        (160, "B", "TechCrunch coverage 📰",      "#6366f1"),
        (90,  "A", "Pricing update 💰",           "#ef4444"),
        (30,  "A", "v2.0 Release 🎉",             "#3b82f6"),
        (7,   "B", "Enterprise partnership 🤝",   "#8b5cf6"),
    ]
    async with pool.acquire() as conn:
        async with conn.transaction():
            await with_org(conn)
            await conn.executemany(
                """
                INSERT INTO annotations (org_id, segment, date, label, color)
                VALUES ($1::uuid, $2, $3, $4, $5)
                """,
                [
                    (org_id, seg, (NOW - timedelta(days=d)).date(), label, color)
                    for d, seg, label, color in annotation_data
                ],
            )
    print(f"[seed] ✓ {len(annotation_data)} annotations")

    # ── 10. Anomaly events ────────────────────────────────────────────────────
    print("[seed] creating anomaly events …")
    anomalies = [
        # (days_ago, metric, value, baseline, std_dev, z_score, direction, severity)
        (210, "events_count", 4200.0, 600.0,  80.0, 45.0, "high", "critical"),
        (160, "events_count", 3100.0, 580.0,  75.0, 34.9, "high", "critical"),
        (45,  "revenue_total", 85.0, 1800.0, 220.0, -7.8, "low",  "critical"),
        (30,  "events_count", 5800.0, 900.0, 110.0, 44.5, "high", "critical"),
        (7,   "events_count", 3200.0, 1100.0, 130.0, 16.2, "high", "warning"),
    ]
    async with pool.acquire() as conn:
        async with conn.transaction():
            await with_org(conn)
            await conn.executemany(
                """
                INSERT INTO anomaly_events
                    (org_id, metric, value, baseline, std_dev, z_score, direction, severity, detected_at)
                VALUES ($1::uuid, $2, $3, $4, $5, $6, $7, $8, $9)
                """,
                [
                    (org_id, metric, value, baseline, std_dev, z_score, direction, severity,
                     days_ago(d))
                    for d, metric, value, baseline, std_dev, z_score, direction, severity in anomalies
                ],
            )
    print(f"[seed] ✓ {len(anomalies)} anomaly events")

    # ── 11. Scheduled reports ─────────────────────────────────────────────────
    print("[seed] creating scheduled reports …")
    async with pool.acquire() as conn:
        async with conn.transaction():
            await with_org(conn)
            await conn.executemany(
                """
                INSERT INTO scheduled_reports
                    (org_id, name, metric, period, recipients, enabled, created_by, last_run_at)
                VALUES ($1::uuid, $2, $3, $4, $5, $6, $7::uuid, $8)
                """,
                [
                    (
                        org_id, "Weekly DAU Summary", "dau", "weekly",
                        [DEMO_EMAIL], True, user_id, days_ago(7),
                    ),
                    (
                        org_id, "Monthly Revenue Report", "revenue_total", "monthly",
                        [DEMO_EMAIL], True, user_id, days_ago(30),
                    ),
                ],
            )
    print("[seed] ✓ 2 scheduled reports")

    # ── 12. API keys ──────────────────────────────────────────────────────────
    print("[seed] creating API keys …")
    async with pool.acquire() as conn:
        async with conn.transaction():
            await with_org(conn)

            def _key_hash(raw: str) -> tuple[str, str]:
                import hashlib
                prefix = raw[:8]
                h      = hashlib.sha256(raw.encode()).hexdigest()
                return prefix, h

            keys = [
                ("Production SDK Key", ["ingest", "read"],    None),
                ("Analytics Export",   ["read", "export"],    None),
                ("CI Integration",     ["ingest"],            days_ago(-30)),   # expires in 30 days
            ]
            for name, scopes, expires_at in keys:
                raw    = f"anlq_{uuid.uuid4().hex}"
                prefix, h = _key_hash(raw)
                await conn.execute(
                    """
                    INSERT INTO api_keys
                        (org_id, name, key_prefix, key_hash, scopes, created_by, revoked, expires_at)
                    VALUES ($1::uuid, $2, $3, $4, $5, $6::uuid, false, $7)
                    """,
                    org_id, name, prefix, h, scopes, user_id, expires_at,
                )
    print("[seed] ✓ 3 API keys")

    # ── 13. Audit log ─────────────────────────────────────────────────────────
    print("[seed] creating audit log entries …")
    audit_entries = [
        (days_ago(300), DEMO_EMAIL, "org.created",       "org",    org_id,  {}),
        (days_ago(299), DEMO_EMAIL, "connector.created", "connector", "stripe", {"name": "Stripe Production"}),
        (days_ago(210), DEMO_EMAIL, "alert.created",     "alert",  "dau",   {"name": "DAU drops below 30"}),
        (days_ago(90),  DEMO_EMAIL, "report.run",        "report", "weekly-dau", {"metric": "dau"}),
        (days_ago(30),  DEMO_EMAIL, "flag.updated",      "flag",   "new_dashboard_v2", {"rollout_pct": 75}),
        (days_ago(7),   DEMO_EMAIL, "member.invited",    "user",   "teammate@example.com", {"role": "viewer"}),
    ]
    async with pool.acquire() as conn:
        async with conn.transaction():
            await with_org(conn)
            await conn.executemany(
                """
                INSERT INTO audit_log
                    (org_id, actor_email, action, resource_type, resource_id, metadata, created_at)
                VALUES ($1::uuid, $2, $3, $4, $5, $6, $7)
                """,
                [
                    (org_id, email, action, rtype, rid, json.dumps(meta), created_at)
                    for created_at, email, action, rtype, rid, meta in audit_entries
                ],
            )
    print(f"[seed] ✓ {len(audit_entries)} audit log entries")

    # ── Done ──────────────────────────────────────────────────────────────────
    print()
    print("=" * 60)
    print("  Demo org seeded successfully!")
    print(f"  Org ID:   {org_id}")
    print(f"  API Key:  {api_key}")
    print(f"  Email:    {DEMO_EMAIL}")
    print(f"  Password: {DEMO_PASSWORD}")
    print()
    print("  Or use the no-password endpoint:")
    print("  POST /api/auth/demo-login")
    print("=" * 60)
    print()
    print(f"  Events:    {total_events:>8,}")
    print(f"  Orders:    {total_orders:>8,}")
    print(f"  Heatmaps:  {total_hm:>8,}")
    print(f"  Users:     {len(ALL_ACTIVE_USERS) + len(CHURNED_USERS):>8,} unique user IDs")
    print()


# ── Entry point ───────────────────────────────────────────────────────────────

async def main() -> None:
    parser = argparse.ArgumentParser(description="Seed the Analytiq demo org")
    parser.add_argument("--reset", action="store_true",
                        help="Delete the existing demo org and re-seed from scratch")
    args = parser.parse_args()

    dsn = (
        os.environ.get("DATABASE_URL")
        or os.environ.get("TEST_DATABASE_URL")
        or "postgresql://postgres:postgres@localhost:5432/analytics_test"
    )
    if dsn.startswith("postgres://"):
        dsn = dsn.replace("postgres://", "postgresql://", 1)

    print("[seed] connecting …", flush=True)

    async def _init(conn: asyncpg.Connection) -> None:
        await conn.set_type_codec(
            "jsonb", encoder=json.dumps, decoder=json.loads, schema="pg_catalog"
        )

    pool = await asyncpg.create_pool(dsn=dsn, min_size=1, max_size=5, init=_init)
    try:
        await seed(pool, reset=args.reset)
    finally:
        await pool.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[seed] interrupted.")
        sys.exit(0)
    except Exception as exc:
        print(f"[seed] FAILED: {exc}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)
