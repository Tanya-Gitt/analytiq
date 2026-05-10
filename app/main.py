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
from app.routers import auth as auth_router
from app.routers import connectors as connectors_router
from app.routers import dashboard as dashboard_router
from app.routers import export as export_router
from app.routers import ingest as ingest_router
from app.routers import webhook as webhook_router


@asynccontextmanager
async def lifespan(app: FastAPI):  # pragma: no cover
    """Production startup/shutdown — tests override pool via dependency injection."""
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
app.include_router(alerts_router.router,     prefix="/api",      tags=["alerts"])

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
