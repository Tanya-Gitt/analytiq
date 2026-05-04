# TODOS — Unified Analytics Platform

Generated from /plan-eng-review on 2026-04-25. Items deferred from Phase 1 MVP.

---

## ~~TODO-1: Dashboard query caching~~ ✅ DONE

Implemented in `app/routers/dashboard.py`:
- `cachetools.TTLCache(maxsize=200, ttl=300)` keyed by `(org_id, endpoint, days)`
- `invalidate_org_cache(org_id)` called by `sync_connector()` after a successful upsert

---

## ~~TODO-2: Rate limiting state should survive app restarts~~ ✅ DONE

Implemented in `app/routers/ingest.py`:
- Postgres-backed token bucket via `rate_limits` table
- `SELECT FOR UPDATE` serialises concurrent requests correctly
- Survives restarts; correct under horizontal scale

---

## TODO-3: Additional schema templates (subscriptions, support tickets)

**What**: Add 1-2 pre-defined schema templates alongside `orders`: `subscriptions` (SaaS MRR tracking: plan, MRR, churn_date, trial_end) and `support_tickets` (ticket_id, created_at, resolved_at, category, severity). Each template gets its own set of auto-generated dashboard charts.

**Why**: The `orders` table is specific to e-commerce. SaaS companies and support teams with different data shapes currently fall through to `custom_rows` JSONB, which requires more manual setup. Pre-built templates reduce onboarding friction for non-ecommerce users.

**Pros**: Broader market fit. Each template is ~50 lines of SQL + chart config + test coverage. Directly addresses the "first 5 orgs with non-orders data" scenario.

**Cons**: More schemas to maintain. Adds Alembic migration complexity. Risk of premature generalization before knowing which schemas real users actually need.

**Context**: Identified as an Open Design Question in the CEO plan. The CEO plan explicitly recommends "start with `orders` + `custom_rows`. Add templates as the second most-requested schema type becomes clear from real users."

**Depends on / blocked by**: First 5 real org signups and their actual data shapes. Do not implement until there are 2+ orgs actively requesting a specific schema.
