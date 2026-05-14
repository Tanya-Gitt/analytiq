"""
Unified Analytics Platform — FastAPI application entry point.

Services:
  app       → this file (uvicorn app.main:app)
  frontend  → Next.js (separate container, proxied by nginx)
  postgres  → PostgreSQL 16 with RLS
  auth      → Supabase GoTrue (JWT issuer)
  scheduler → APScheduler polling loop (scheduler/main.py)
  nginx     → reverse proxy (/api/* → here, /* → frontend)

RLS enforcement: all tenant data access goes through FastAPI DI in app/deps.py.
Never use middleware to set app.org_id — Starlette's call_next() breaks it.
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.database import close_pool, create_pool
from app.routers import alerts as alerts_router
from app.routers import annotations as annotations_router
from app.routers import anomalies as anomalies_router
from app.routers import api_keys as api_keys_router
from app.routers import audit as audit_router
from app.routers import auth as auth_router
from app.routers import churn as churn_router
from app.routers import connectors as connectors_router
from app.routers import copilot as copilot_router
from app.routers import dashboard as dashboard_router
from app.routers import embed as embed_router
from app.routers import export as export_router
from app.routers import flags as flags_router
from app.routers import funnels as funnels_router
from app.routers import gdpr as gdpr_router
from app.routers import heatmaps as heatmaps_router
from app.routers import ingest as ingest_router
from app.routers import paths as paths_router
from app.routers import people as people_router
from app.routers import reports as reports_router
from app.routers import seed as seed_router
from app.routers import schema_registry as schema_registry_router
from app.routers import setup as setup_router
from app.routers import share as share_router
from app.routers import sso as sso_router
from app.routers import storage as storage_router
from app.routers import stream as stream_router
from app.routers import system as system_router
from app.routers import team as team_router
from app.routers import warehouse as warehouse_router
from app.routers import webhook as webhook_router

_DEV_JWT_SECRETS = {
    "localdev_jwt_secret_replace_before_prod",
    "secret",
    "changeme",
    "dev",
    "test",
}


@asynccontextmanager
async def lifespan(app: FastAPI):  # pragma: no cover
    """Production startup/shutdown — tests override pool via dependency injection."""
    # ── Security preflight: refuse to start with a known-weak JWT_SECRET ──────
    import os as _os
    _jwt_secret = _os.environ.get("JWT_SECRET", "")
    if not _jwt_secret:
        raise RuntimeError(
            "STARTUP BLOCKED: JWT_SECRET is not set. "
            "Generate one with: python3 -c \"import secrets; print(secrets.token_hex(32))\""
        )
    if _jwt_secret.lower() in _DEV_JWT_SECRETS or len(_jwt_secret) < 32:
        raise RuntimeError(
            f"STARTUP BLOCKED: JWT_SECRET looks like a dev placeholder or is too short "
            f"(got {len(_jwt_secret)} chars, need ≥32). "
            "Generate a strong secret: python3 -c \"import secrets; print(secrets.token_hex(32))\""
        )
    # ─────────────────────────────────────────────────────────────────────────
    app.state.pool = await create_pool()
    yield
    await close_pool(app.state.pool)


app = FastAPI(
    title="Unified Analytics Platform",
    description="Self-hostable analytics: product events + revenue data, one dashboard.",
    version="0.1.0",
    lifespan=lifespan,
)

# ── CORS ──────────────────────────────────────────────────────────────────────
# ALLOWED_ORIGINS env var: comma-separated list of origins for the dashboard.
# Defaults to localhost:3000 for local dev.
# Per-org CORS for the JS SDK ingest endpoint is handled separately in
# app/routers/ingest.py (validates Origin against js_sdk connector config).
_raw_origins = os.environ.get("ALLOWED_ORIGINS", "http://localhost:3000")
_allowed_origins = [o.strip() for o in _raw_origins.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(auth_router.router,       prefix="/api/auth", tags=["auth"])
app.include_router(ingest_router.router,     prefix="/api",      tags=["ingest"])
app.include_router(webhook_router.router,    prefix="/api",      tags=["webhook"])
app.include_router(connectors_router.router, prefix="/api",      tags=["connectors"])
app.include_router(dashboard_router.router,  prefix="/api",      tags=["dashboard"])
app.include_router(export_router.router,     prefix="/api",      tags=["export"])
app.include_router(stream_router.router,     prefix="/api",      tags=["stream"])
app.include_router(alerts_router.router,     prefix="/api",      tags=["alerts"])
app.include_router(share_router.router,      prefix="/api",      tags=["share"])
app.include_router(annotations_router.router, prefix="/api",     tags=["annotations"])
app.include_router(team_router.router,        prefix="/api",      tags=["team"])
app.include_router(funnels_router.router,     prefix="/api",      tags=["funnels"])
app.include_router(sso_router.router,         prefix="/api/auth", tags=["sso"])
app.include_router(anomalies_router.router,   prefix="/api",      tags=["anomalies"])
app.include_router(copilot_router.router,     prefix="/api",      tags=["copilot"])
app.include_router(churn_router.router,       prefix="/api",      tags=["churn"])
app.include_router(flags_router.router,       prefix="/api",      tags=["flags"])
app.include_router(heatmaps_router.router,    prefix="/api",      tags=["heatmaps"])
app.include_router(people_router.router,      prefix="/api",      tags=["people"])
app.include_router(setup_router.router,       prefix="/api",      tags=["setup"])
app.include_router(warehouse_router.router,   prefix="/api",      tags=["warehouse"])
app.include_router(gdpr_router.router,             prefix="/api",      tags=["gdpr"])
app.include_router(audit_router.router,            prefix="/api",      tags=["audit"])
app.include_router(storage_router.router,          prefix="/api",      tags=["storage"])
app.include_router(paths_router.router,            prefix="/api",      tags=["paths"])
app.include_router(schema_registry_router.router,  prefix="/api",      tags=["schema"])
app.include_router(api_keys_router.router,         prefix="/api",      tags=["api-keys"])
app.include_router(reports_router.router,          prefix="/api",      tags=["reports"])
app.include_router(system_router.router,           prefix="/api",      tags=["system"])
app.include_router(embed_router.router,            prefix="/api",      tags=["embed"])
app.include_router(seed_router.router,             prefix="/api",      tags=["internal"])

# ── Static: JS SDK ────────────────────────────────────────────────────────────
# Serves sdk/analytics.js at /sdk/analytics.js
# The browser snippet: <script src="/sdk/analytics.js"></script>
_sdk_dir = Path(__file__).parent.parent / "sdk"
if _sdk_dir.is_dir():
    app.mount("/sdk", StaticFiles(directory=str(_sdk_dir)), name="sdk")


@app.get("/health")
@app.get("/api/health")
async def health():
    return {"status": "ok"}
