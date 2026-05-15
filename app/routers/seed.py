"""
One-time demo data seed endpoint.

POST /api/internal/seed?secret=<SEED_SECRET>

Runs the seed script inline using the app's existing DB pool.
Protected by a static secret set via SEED_SECRET env var.
Remove this router (or the env var) after seeding.
"""

from __future__ import annotations

import json
import math
import os
import random
from datetime import datetime, timedelta, timezone

import asyncpg
import bcrypt
from fastapi import APIRouter, Depends, HTTPException

from app.database import get_pool

router = APIRouter()

_SECRET = os.environ.get("SEED_SECRET", "")

DEMO_ORG_NAME = "Analytiq Demo"
DEMO_EMAIL    = "demo@analytiq.io"
DEMO_PASSWORD = "DemoAnalytiq2024!"

rng   = random.Random(42)
NOW   = datetime.now(timezone.utc)
START = NOW - timedelta(days=365)

POWER_USERS      = [f"usr_power_{i:03d}"      for i in range(1,  51)]
REGULAR_USERS    = [f"usr_regular_{i:03d}"    for i in range(1, 201)]
OCCASIONAL_USERS = [f"usr_occasional_{i:03d}" for i in range(1, 251)]
CHURNED_USERS    = [f"usr_churned_{i:03d}"    for i in range(1, 101)]
ALL_ACTIVE       = POWER_USERS + REGULAR_USERS + OCCASIONAL_USERS

PAGES    = ["/", "/dashboard", "/events", "/funnels", "/people", "/settings", "/pricing", "/docs"]
FEATURES = ["funnel_builder", "retention_chart", "cohort_analysis", "ai_copilot", "data_export", "custom_dashboard"]
BROWSERS = ["Chrome", "Firefox", "Safari", "Edge"]
COUNTRIES= ["IN", "US", "GB", "DE", "SG", "AU", "CA", "FR"]
PLANS    = ["starter", "pro", "enterprise"]
PLAN_PRICES = {"starter": 29.0, "pro": 79.0, "enterprise": 299.0}
PLAN_ANNUAL = {"starter": 290.0, "pro": 790.0, "enterprise": 2990.0}

PRODUCTS = [
    ("Analytics Pro",   "P001", 49.0,  35.0),
    ("Data Connector",  "P002", 29.0,  18.0),
    ("Dashboard Plus",  "P003", 79.0,  55.0),
    ("AI Copilot Add-on","P004",39.0,  25.0),
    ("Export Bundle",   "P005", 19.0,  10.0),
    ("Enterprise Suite","P006",299.0, 190.0),
    ("Team Seats x5",   "P007", 99.0,  60.0),
    ("API Access",      "P008", 59.0,  38.0),
]
CHANNELS = ["organic", "paid_search", "social", "referral", "email", "direct"]
ACQ_SOURCES = ["google", "linkedin", "twitter", "friend", "blog", "conference"]

_ENAMES  = ["page_view","button_click","identify","search","feature_used","purchase","signup","error","video_play","onboarding_complete"]
_EWEIGHTS= [38, 20, 6, 8, 12, 3, 3, 2, 4, 4]

SPIKE_DAYS = {300: 4.5, 210: 7.0, 160: 5.0, 90: 0.7, 30: 6.0, 7: 3.5}


def _vol(day: int) -> int:
    t  = day / 364.0
    b  = 100 + 500 / (1 + math.exp(-8 * (t - 0.45)))
    dow= (START + timedelta(days=day)).weekday()
    sf = {0:1.0,1:1.05,2:1.0,3:0.95,4:0.85,5:0.6,6:0.5}[dow]
    sp = 1.0
    for sd, m in SPIKE_DAYS.items():
        if abs((364-day)-sd) <= 1:
            sp = max(sp, m)
    return max(20, int(b * sf * sp * rng.uniform(0.88, 1.12)))


def _evt(org_id: str, day: int) -> tuple:
    dt = START + timedelta(days=day, seconds=rng.randint(0, 86399))
    en = rng.choices(_ENAMES, weights=_EWEIGHTS, k=1)[0]
    dr = 364 - day
    pool = (POWER_USERS*6 + REGULAR_USERS*3 + OCCASIONAL_USERS + CHURNED_USERS*2) if dr > 70 else (POWER_USERS*8 + REGULAR_USERS*4 + OCCASIONAL_USERS)
    uid = rng.choice(pool)
    props: dict = {"platform": rng.choice(["web","mobile_web"]), "browser": rng.choice(BROWSERS), "country": rng.choice(COUNTRIES)}
    if en == "page_view":    props.update({"page": rng.choice(PAGES), "duration_s": rng.randint(5,420)})
    elif en == "feature_used": props["feature"] = rng.choice(FEATURES)
    elif en == "purchase":
        pl = rng.choice(PLANS)
        ann = rng.random() < 0.35
        props.update({"plan": pl, "amount": PLAN_ANNUAL[pl] if ann else PLAN_PRICES[pl], "billing": "annual" if ann else "monthly"})
    return (org_id, en, uid, None, json.dumps(props), dt)


def _order(org_id: str, day: int) -> tuple:
    dt          = START + timedelta(days=day)
    order_date  = dt.date()
    product     = rng.choice(PRODUCTS)
    p_name, p_id, price, cost = product
    qty         = rng.choices([1, 2, 3, 5], weights=[60, 25, 10, 5], k=1)[0]
    delivered   = rng.random() < 0.93
    del_minutes = rng.randint(1200, 14400) if delivered else None
    return (
        org_id,                            # $1  org_id
        f"ORD-{day:04d}-{rng.randint(1000,9999)}",  # $2  order_id
        order_date,                        # $3  order_date
        rng.choice(ALL_ACTIVE),            # $4  customer_id
        p_id,                              # $5  product_id
        p_name,                            # $6  product_name
        rng.choice(CHANNELS),              # $7  channel
        qty,                               # $8  quantity
        float(price),                      # $9  price_per_unit
        float(cost),                       # $10 cost_per_unit
        delivered,                         # $11 delivered
        del_minutes,                       # $12 delivery_time_minutes
        rng.choice(COUNTRIES),             # $13 region
        rng.random() < 0.20,               # $14 promo_used
        rng.choice(ACQ_SOURCES),           # $15 acquisition_source
    )


@router.post("/internal/seed", status_code=202)
async def seed_demo(secret: str = "", pool: asyncpg.Pool = Depends(get_pool)):
    if not _SECRET or secret != _SECRET:
        raise HTTPException(403, "invalid or missing secret")

    async with pool.acquire() as conn:
        exists = await conn.fetchval("SELECT id FROM orgs WHERE name = $1", DEMO_ORG_NAME)
        if exists:
            return {"status": "already_seeded", "org_id": str(exists)}

    pw = bcrypt.hashpw(DEMO_PASSWORD.encode(), bcrypt.gensalt(rounds=10)).decode()

    async with pool.acquire() as conn:
        async with conn.transaction():
            org  = await conn.fetchrow("INSERT INTO orgs (name) VALUES ($1) RETURNING id, api_key", DEMO_ORG_NAME)
            oid  = str(org["id"])
            user = await conn.fetchrow(
                "INSERT INTO users (org_id, email, password_hash, role) VALUES ($1::uuid,$2,$3,'admin') RETURNING id",
                oid, DEMO_EMAIL, pw)
            uid = str(user["id"])

    async def _ctx(c): await c.execute(f"SET LOCAL app.org_id = '{oid}'")

    # Events
    ev_batch, total_e = [], 0
    INS_E = "INSERT INTO events (org_id,event_name,user_id,anonymous_id,properties,received_at) VALUES ($1::uuid,$2,$3,$4,$5,$6)"
    async with pool.acquire() as conn:
        async with conn.transaction():
            await _ctx(conn)
            for day in range(365):
                for _ in range(_vol(day)):
                    ev_batch.append(_evt(oid, day))
                    if len(ev_batch) >= 500:
                        await conn.executemany(INS_E, ev_batch)
                        total_e += len(ev_batch)
                        ev_batch.clear()
            if ev_batch:
                await conn.executemany(INS_E, ev_batch)
                total_e += len(ev_batch)

    # Orders
    or_batch, total_o = [], 0
    INS_O = """
        INSERT INTO orders
          (org_id,order_id,order_date,customer_id,product_id,product_name,
           channel,quantity,price_per_unit,cost_per_unit,delivered,
           delivery_time_minutes,region,promo_used,acquisition_source)
        VALUES ($1::uuid,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15)
        ON CONFLICT (org_id, order_id) DO NOTHING
    """
    async with pool.acquire() as conn:
        async with conn.transaction():
            await _ctx(conn)
            for day in range(365):
                n = max(1, int((3 + 22*(day/364)) * rng.uniform(0.7,1.3)))
                for _ in range(n):
                    or_batch.append(_order(oid, day))
                    if len(or_batch) >= 500:
                        await conn.executemany(INS_O, or_batch)
                        total_o += len(or_batch)
                        or_batch.clear()
            if or_batch:
                await conn.executemany(INS_O, or_batch)
                total_o += len(or_batch)

    # Misc: connectors, alerts, funnels, flags, annotations, anomalies
    # NOTE: asyncpg codec calls json.dumps() automatically for JSONB — pass raw dicts/lists
    async with pool.acquire() as conn:
        async with conn.transaction():
            await _ctx(conn)
            await conn.executemany(
                "INSERT INTO connectors (org_id,type,name,segment,config,status,last_synced_at) VALUES ($1::uuid,$2,$3,$4,$5,$6,$7)",
                [(oid,"webhook","Stripe Revenue Webhook","B",{"events":["payment.succeeded","subscription.created"]},"active",NOW-timedelta(days=1)),
                 (oid,"csv_upload","Monthly Cohort CSV","A",{"schedule":"weekly"},"active",NOW-timedelta(days=3)),
                 (oid,"js_sdk","Web SDK (Production)","A",{"site":"analytiq-phi.vercel.app"},"active",NOW-timedelta(hours=2))])
            await conn.executemany(
                "INSERT INTO alert_rules (org_id,name,metric,condition,threshold,window_hours,channel,destination) VALUES ($1::uuid,$2,$3,$4,$5,$6,$7,$8)",
                [(oid,"DAU drops below 30","dau","below",30,24,"email","alerts@analytiq.io"),
                 (oid,"Daily revenue below $200","revenue_total","below",200,24,"slack","#alerts"),
                 (oid,"Error rate above 5%","error_rate","above",5,1,"slack","#ops")])
            await conn.executemany(
                "INSERT INTO funnels (org_id,name,steps) VALUES ($1::uuid,$2,$3)",
                [(oid,"Signup to Paid",["page_view","signup","onboarding_complete","purchase"]),
                 (oid,"Feature Adoption",["signup","feature_used","feature_used","purchase"])])
            await conn.executemany(
                "INSERT INTO feature_flags (org_id,name,description,enabled,rollout_pct,targeting) VALUES ($1::uuid,$2,$3,$4,$5,$6)",
                [(oid,"ai_copilot_beta","AI Copilot (beta)",True,25,[]),
                 (oid,"new_dashboard_v2","Redesigned dashboard",True,75,[]),
                 (oid,"dark_mode","Dark mode UI",True,50,[]),
                 (oid,"bulk_export","Bulk data export",True,10,[]),
                 (oid,"pdf_reports","PDF report attachments",True,100,[])])
            await conn.executemany(
                "INSERT INTO annotations (org_id,segment,date,label,color) VALUES ($1::uuid,$2,$3,$4,$5)",
                [(oid,"A",(NOW-timedelta(days=300)).date(),"Beta launch 🚀","#10b981"),
                 (oid,"A",(NOW-timedelta(days=210)).date(),"Product Hunt #1 🏆","#f59e0b"),
                 (oid,"B",(NOW-timedelta(days=160)).date(),"TechCrunch coverage 📰","#6366f1"),
                 (oid,"A",(NOW-timedelta(days=90)).date(),"Pricing update 💰","#ef4444"),
                 (oid,"A",(NOW-timedelta(days=30)).date(),"v2.0 Release 🎉","#3b82f6"),
                 (oid,"B",(NOW-timedelta(days=7)).date(),"Enterprise partnership 🤝","#8b5cf6")])
            await conn.executemany(
                "INSERT INTO anomaly_events (org_id,metric,value,baseline,std_dev,z_score,direction,severity,detected_at) VALUES ($1::uuid,$2,$3,$4,$5,$6,$7,$8,$9)",
                [(oid,"events_count",4200,600,80,45.0,"high","critical",NOW-timedelta(days=210)),
                 (oid,"revenue_total",85,1800,220,-7.8,"low","critical",NOW-timedelta(days=45)),
                 (oid,"events_count",5800,900,110,44.5,"high","critical",NOW-timedelta(days=30))])
            await conn.executemany(
                "INSERT INTO scheduled_reports (org_id,name,metric,period,recipients,enabled,created_by,last_run_at) VALUES ($1::uuid,$2,$3,$4,$5,$6,$7::uuid,$8)",
                [(oid,"Weekly DAU Summary","dau","weekly",[DEMO_EMAIL],True,uid,NOW-timedelta(days=7)),
                 (oid,"Monthly Revenue Report","revenue_total","monthly",[DEMO_EMAIL],True,uid,NOW-timedelta(days=30))])

    return {"status": "seeded", "org_id": oid, "events": total_e, "orders": total_o}


@router.post("/internal/reseed-orders", status_code=202)
async def reseed_orders(secret: str = "", pool: asyncpg.Pool = Depends(get_pool)):
    """Delete and re-seed orders for the demo org with the correct schema."""
    if not _SECRET or secret != _SECRET:
        raise HTTPException(403, "invalid or missing secret")

    async with pool.acquire() as conn:
        oid_val = await conn.fetchval("SELECT id FROM orgs WHERE name = $1", DEMO_ORG_NAME)
    if not oid_val:
        raise HTTPException(404, "Demo org not found — run /internal/seed first")

    oid = str(oid_val)

    # Wipe existing orders for demo org
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM orders WHERE org_id = $1::uuid", oid)

    INS_O = """
        INSERT INTO orders
          (org_id,order_id,order_date,customer_id,product_id,product_name,
           channel,quantity,price_per_unit,cost_per_unit,delivered,
           delivery_time_minutes,region,promo_used,acquisition_source)
        VALUES ($1::uuid,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15)
        ON CONFLICT (org_id, order_id) DO NOTHING
    """

    or_batch, total_o = [], 0
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(f"SET LOCAL app.org_id = '{oid}'")
            for day in range(365):
                n = max(1, int((3 + 22 * (day / 364)) * rng.uniform(0.7, 1.3)))
                for _ in range(n):
                    or_batch.append(_order(oid, day))
                    if len(or_batch) >= 500:
                        await conn.executemany(INS_O, or_batch)
                        total_o += len(or_batch)
                        or_batch.clear()
            if or_batch:
                await conn.executemany(INS_O, or_batch)
                total_o += len(or_batch)

    return {"status": "reseeded", "org_id": oid, "orders": total_o}


@router.post("/internal/reseed-misc", status_code=202)
async def reseed_misc(secret: str = "", pool: asyncpg.Pool = Depends(get_pool)):
    """Re-insert all misc demo data: flags, alerts, funnels, connectors, reports, annotations, anomalies."""
    if not _SECRET or secret != _SECRET:
        raise HTTPException(403, "invalid or missing secret")
    try:
        return await _do_reseed_misc(pool)
    except Exception as exc:
        import traceback
        raise HTTPException(500, detail=f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}")


async def _do_reseed_misc(pool: asyncpg.Pool):

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id FROM orgs WHERE name = $1", DEMO_ORG_NAME
        )
    if not row:
        raise HTTPException(404, "Demo org not found — run /internal/seed first")

    oid = str(row["id"])

    # Get demo user id
    async with pool.acquire() as conn:
        uid = str(await conn.fetchval(
            "SELECT id FROM users WHERE org_id = $1::uuid LIMIT 1", oid
        ))

    async with pool.acquire() as conn:
        async with conn.transaction():
            # FORCE RLS applies even to the table owner, so we must set app.org_id
            await conn.execute(f"SET LOCAL app.org_id = '{oid}'")

            # Wipe existing misc data for demo org
            await conn.execute("DELETE FROM connectors WHERE org_id = $1::uuid", oid)
            await conn.execute("DELETE FROM alert_rules WHERE org_id = $1::uuid", oid)
            await conn.execute("DELETE FROM funnels WHERE org_id = $1::uuid", oid)
            await conn.execute("DELETE FROM feature_flags WHERE org_id = $1::uuid", oid)
            await conn.execute("DELETE FROM annotations WHERE org_id = $1::uuid", oid)
            await conn.execute("DELETE FROM anomaly_events WHERE org_id = $1::uuid", oid)
            await conn.execute("DELETE FROM scheduled_reports WHERE org_id = $1::uuid", oid)
            await conn.execute("DELETE FROM events WHERE org_id = $1::uuid AND event_name = 'identify'", oid)
            await conn.execute("DELETE FROM heatmap_events WHERE org_id = $1::uuid", oid)
            await conn.execute("DELETE FROM event_schemas WHERE org_id = $1::uuid", oid)

            # connectors: type IN ('sheets_csv','csv_upload','webhook','js_sdk'), segment IN ('A','B')
            # NOTE: asyncpg codec calls json.dumps() automatically for JSONB — pass raw dicts, NOT json.dumps() strings
            await conn.executemany(
                "INSERT INTO connectors (org_id,type,name,segment,config,status,last_synced_at) VALUES ($1::uuid,$2,$3,$4,$5,$6,$7)",
                [(oid,"webhook","Stripe Revenue Webhook","B",{"events":["payment.succeeded","subscription.created"]},"active",NOW-timedelta(days=1)),
                 (oid,"csv_upload","Monthly Cohort CSV","A",{"schedule":"weekly","last_file":"cohort_may_2026.csv"},"active",NOW-timedelta(days=3)),
                 (oid,"js_sdk","Web SDK (Production)","A",{"site":"analytiq-phi.vercel.app"},"active",NOW-timedelta(hours=2))])

            # alert_rules: condition IN ('below','above','no_data'), channel IN ('slack','email')
            await conn.executemany(
                "INSERT INTO alert_rules (org_id,name,metric,condition,threshold,window_hours,channel,destination) VALUES ($1::uuid,$2,$3,$4,$5,$6,$7,$8)",
                [(oid,"DAU drops below 30","dau","below",30,24,"email","alerts@analytiq.io"),
                 (oid,"Daily revenue below $200","revenue_total","below",200,24,"slack","#alerts"),
                 (oid,"Error rate above 5%","error_rate","above",5,1,"slack","#ops")])

            await conn.executemany(
                "INSERT INTO funnels (org_id,name,steps) VALUES ($1::uuid,$2,$3)",
                [(oid,"Signup to Paid",["page_view","signup","onboarding_complete","purchase"]),
                 (oid,"Feature Adoption",["signup","feature_used","feature_used","purchase"])])

            await conn.executemany(
                "INSERT INTO feature_flags (org_id,name,description,enabled,rollout_pct,targeting) VALUES ($1::uuid,$2,$3,$4,$5,$6)",
                [(oid,"ai_copilot_beta","AI Copilot (beta)",True,25,[]),
                 (oid,"new_dashboard_v2","Redesigned dashboard",True,75,[]),
                 (oid,"dark_mode","Dark mode UI",True,50,[]),
                 (oid,"bulk_export","Bulk data export",True,10,[]),
                 (oid,"pdf_reports","PDF report attachments",True,100,[])])

            await conn.executemany(
                "INSERT INTO annotations (org_id,segment,date,label,color) VALUES ($1::uuid,$2,$3,$4,$5)",
                [(oid,"A",(NOW-timedelta(days=300)).date(),"Beta launch 🚀","#10b981"),
                 (oid,"A",(NOW-timedelta(days=210)).date(),"Product Hunt #1 🏆","#f59e0b"),
                 (oid,"B",(NOW-timedelta(days=160)).date(),"TechCrunch coverage 📰","#6366f1"),
                 (oid,"A",(NOW-timedelta(days=90)).date(),"Pricing update 💰","#ef4444"),
                 (oid,"A",(NOW-timedelta(days=30)).date(),"v2.0 Release 🎉","#3b82f6"),
                 (oid,"B",(NOW-timedelta(days=7)).date(),"Enterprise partnership 🤝","#8b5cf6")])

            # anomaly_events: include recent ones so summary cards (24h/7d) show non-zero
            await conn.executemany(
                "INSERT INTO anomaly_events (org_id,metric,value,baseline,std_dev,z_score,direction,severity,detected_at) VALUES ($1::uuid,$2,$3,$4,$5,$6,$7,$8,$9)",
                [(oid,"events_count",4500,650,85,45.3,"high","critical",NOW-timedelta(hours=3)),
                 (oid,"error_rate",12.5,2.1,0.8,12.9,"high","critical",NOW-timedelta(days=3)),
                 (oid,"events_count",4200,600,80,45.0,"high","critical",NOW-timedelta(days=210)),
                 (oid,"revenue_total",85,1800,220,-7.8,"low","critical",NOW-timedelta(days=45)),
                 (oid,"events_count",5800,900,110,44.5,"high","critical",NOW-timedelta(days=30))])

            await conn.executemany(
                "INSERT INTO scheduled_reports (org_id,name,metric,period,recipients,enabled,created_by,last_run_at) VALUES ($1::uuid,$2,$3,$4,$5,$6,$7::uuid,$8)",
                [(oid,"Weekly DAU Summary","dau","weekly",[DEMO_EMAIL],True,uid,NOW-timedelta(days=7)),
                 (oid,"Monthly Revenue Report","revenue_total","monthly",[DEMO_EMAIL],True,uid,NOW-timedelta(days=30))])

            # identify events — enables People page and Churn traits display
            _DEMO_PROFILES = [
                ("usr_power_001","alice.johnson@acmecorp.com","Alice Johnson","enterprise","Acme Corp","US"),
                ("usr_power_002","bob.smith@techco.io","Bob Smith","pro","TechCo","GB"),
                ("usr_power_003","priya.patel@startup.in","Priya Patel","pro","StartupIN","IN"),
                ("usr_power_004","carlos.m@globalinc.com","Carlos Mendez","enterprise","GlobalInc","DE"),
                ("usr_power_005","sarah.k@saasly.com","Sarah Kim","enterprise","SaaSly","SG"),
                ("usr_regular_001","james.w@freelance.io","James Wilson","starter","Freelance","AU"),
                ("usr_regular_002","emily.c@designstudio.co","Emily Chen","pro","DesignStudio","CA"),
                ("usr_regular_003","michael.b@analytics.co","Michael Brown","pro","AnalyticsCo","US"),
                ("usr_regular_004","olivia.d@marketers.io","Olivia Davis","starter","Marketers IO","FR"),
                ("usr_regular_005","noah.t@devtools.dev","Noah Taylor","pro","DevTools","US"),
                ("usr_regular_006","ava.m@cloudnine.io","Ava Martinez","starter","CloudNine","GB"),
                ("usr_regular_007","liam.a@fintech.co","Liam Anderson","enterprise","FintechCo","SG"),
                ("usr_regular_008","mia.t@healthtech.io","Mia Thomas","pro","HealthTech","AU"),
                ("usr_regular_009","ethan.j@edtech.co","Ethan Jackson","starter","EdTechCo","IN"),
                ("usr_regular_010","sophia.w@ecommerce.io","Sophia White","pro","eCommerce IO","US"),
                ("usr_occasional_001","mason.h@agency.co","Mason Harris","starter","Agency","CA"),
                ("usr_occasional_002","isabella.m@creative.io","Isabella Martin","starter","Creative IO","DE"),
                ("usr_churned_001","logan.t@oldco.com","Logan Thompson","starter","OldCo","US"),
                ("usr_churned_002","charlotte.g@legacy.io","Charlotte Garcia","pro","Legacy IO","GB"),
                ("usr_churned_003","elijah.m@pasttech.co","Elijah Moore","starter","PastTech","AU"),
            ]
            await conn.executemany(
                "INSERT INTO events (org_id,event_name,user_id,anonymous_id,properties,received_at) VALUES ($1::uuid,$2,$3,$4,$5,$6)",
                [(oid,"identify",uid_,None,
                  {"email":email,"name":name,"plan":plan,"company":company,"country":country},
                  NOW-timedelta(days=rng.randint(1,60)))
                 for uid_,email,name,plan,company,country in _DEMO_PROFILES])

            # heatmap_events — enables Heatmaps page
            _HMAP_PAGES = ["/dashboard","/events","/funnels","/people","/settings","/pricing"]
            _ELEMENTS   = ["button.btn-primary","a.nav-link","div.card","h1.page-title","span.badge","input.search"]
            hmap_rows = []
            for _ in range(300):
                pg  = rng.choice(_HMAP_PAGES)
                evt = rng.choices(["click","scroll"], weights=[60,40], k=1)[0]
                hmap_rows.append((
                    oid, pg, evt,
                    rng.randint(5,95) if evt=="click" else None,
                    rng.randint(5,95),
                    rng.choice(_ELEMENTS) if evt=="click" else None,
                    rng.choice(ALL_ACTIVE) if rng.random()<0.7 else None,
                    NOW - timedelta(days=rng.randint(0,29), hours=rng.randint(0,23)),
                ))
            await conn.executemany(
                "INSERT INTO heatmap_events (org_id,page_url,event_type,x_pct,y_pct,element,user_id,received_at) VALUES ($1::uuid,$2,$3,$4,$5,$6,$7,$8)",
                hmap_rows)

            # event_schemas — enables Schema Registry page
            await conn.executemany(
                "INSERT INTO event_schemas (org_id,event_name,properties,strict_mode) VALUES ($1::uuid,$2,$3,$4)",
                [(oid,"page_view",    {"page":"string","duration_s":"number","browser":"string","country":"string"},False),
                 (oid,"button_click", {"element_id":"string","page":"string","label":"string"},False),
                 (oid,"identify",     {"email":"string","name":"string","plan":"string","company":"string"},True),
                 (oid,"purchase",     {"plan":"string","amount":"number","billing":"string"},True),
                 (oid,"signup",       {"email":"string","source":"string"},True),
                 (oid,"feature_used", {"feature":"string","page":"string"},False),
                 (oid,"error",        {"message":"string","code":"number","page":"string"},False)])

    return {"status": "reseeded_misc", "org_id": oid}
