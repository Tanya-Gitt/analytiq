-- Unified Analytics Platform — PostgreSQL schema
-- Apply with: psql $DATABASE_URL -f db/schema.sql
-- Or via Alembic migration generated from this file.

-- ──────────────────────────────────────────────
-- Extensions
-- ──────────────────────────────────────────────
CREATE EXTENSION IF NOT EXISTS "pgcrypto";   -- gen_random_uuid()

-- ──────────────────────────────────────────────
-- Auth schema (required by Supabase GoTrue)
-- GoTrue's 00_init_auth_schema migration creates tables inside the auth
-- schema but does NOT create the schema itself — it must pre-exist.
-- Grant ALL so the analytics user (GoTrue's DB user) can run migrations.
-- ──────────────────────────────────────────────
CREATE SCHEMA IF NOT EXISTS auth;
-- Only grant if the analytics role exists (Docker Compose stack).
-- In test environments the role is 'postgres' and this is a no-op.
DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'analytics') THEN
    GRANT ALL ON SCHEMA auth TO analytics;
  END IF;
END $$;

-- ──────────────────────────────────────────────
-- Organizations  (not tenant-scoped; public read for auth layer)
-- ──────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS orgs (
  id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name       TEXT NOT NULL,
  api_key    TEXT UNIQUE NOT NULL DEFAULT encode(gen_random_bytes(24), 'hex'),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ──────────────────────────────────────────────
-- Users  (one user can belong to one org for MVP)
-- ──────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS users (
  id                     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id                 UUID NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
  email                  TEXT UNIQUE NOT NULL,
  password_hash          TEXT NOT NULL,      -- bcrypt
  failed_login_attempts  INT  NOT NULL DEFAULT 0,
  locked_until           TIMESTAMPTZ,        -- NULL = not locked
  created_at             TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS users_org ON users(org_id);

-- ──────────────────────────────────────────────
-- Segment A: generic event store
-- ──────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS events (
  id           BIGSERIAL PRIMARY KEY,
  org_id       UUID NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
  event_name   TEXT NOT NULL,
  user_id      TEXT,
  anonymous_id TEXT,
  properties   JSONB NOT NULL DEFAULT '{}',
  received_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
-- Queries filtered by event_name (top events chart, funnel)
CREATE INDEX IF NOT EXISTS events_org_name_ts
  ON events(org_id, event_name, received_at DESC);
-- Queries filtered by time only (events timeline, DAU charts)
CREATE INDEX IF NOT EXISTS events_org_ts
  ON events(org_id, received_at DESC);

-- ──────────────────────────────────────────────
-- Segment B: orders (standard e-commerce schema)
-- ──────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS orders (
  id                    BIGSERIAL PRIMARY KEY,
  org_id                UUID NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
  order_id              TEXT NOT NULL,
  order_date            DATE NOT NULL,
  customer_id           TEXT,
  product_id            TEXT,
  product_name          TEXT,
  channel               TEXT,
  quantity              INT  NOT NULL,
  price_per_unit        NUMERIC(10,2),
  cost_per_unit         NUMERIC(10,2),
  delivered             BOOLEAN,
  delivery_time_minutes INT,
  region                TEXT,
  promo_used            BOOLEAN,
  acquisition_source    TEXT,
  created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (org_id, order_id)
);
CREATE INDEX IF NOT EXISTS orders_org_date ON orders(org_id, order_date DESC);

-- ──────────────────────────────────────────────
-- Rate limits (token bucket state, survives restarts)
-- Not tenant-scoped; no RLS. One row per org.
-- ──────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS rate_limits (
  org_id         UUID PRIMARY KEY REFERENCES orgs(id) ON DELETE CASCADE,
  tokens         DOUBLE PRECISION NOT NULL DEFAULT 100.0,
  last_refill_at TIMESTAMPTZ      NOT NULL DEFAULT NOW()
);

-- ──────────────────────────────────────────────
-- Connectors
-- ──────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS connectors (
  id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id                UUID NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
  name                  TEXT NOT NULL,
  type                  TEXT NOT NULL
    CHECK (type IN ('sheets_csv', 'csv_upload', 'webhook', 'js_sdk')),
  segment               TEXT NOT NULL CHECK (segment IN ('A', 'B')),
  config                JSONB NOT NULL DEFAULT '{}',
  sync_interval_minutes INT NOT NULL DEFAULT 60,
  last_synced_at        TIMESTAMPTZ,
  last_error            TEXT,
  status                TEXT NOT NULL DEFAULT 'active'
    CHECK (status IN ('active', 'error', 'paused')),
  created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS connectors_org ON connectors(org_id, status);

-- ──────────────────────────────────────────────
-- Alert rules
-- ──────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS alert_rules (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id           UUID NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
  name             TEXT NOT NULL,
  metric           TEXT NOT NULL,
  condition        TEXT NOT NULL CHECK (condition IN ('below', 'above', 'no_data')),
  threshold        NUMERIC,
  window_hours     INT NOT NULL DEFAULT 24,
  channel          TEXT NOT NULL CHECK (channel IN ('slack', 'email')),
  destination      TEXT NOT NULL,
  state            TEXT NOT NULL DEFAULT 'OK' CHECK (state IN ('OK', 'TRIGGERED')),
  last_triggered_at TIMESTAMPTZ,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS alert_rules_org ON alert_rules(org_id);

-- ──────────────────────────────────────────────
-- Custom rows (non-standard CSV schemas)
-- ──────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS custom_rows (
  id           BIGSERIAL PRIMARY KEY,
  org_id       UUID NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
  connector_id UUID NOT NULL REFERENCES connectors(id) ON DELETE CASCADE,
  row_data     JSONB NOT NULL,
  imported_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
-- GIN index for key-existence lookups across the JSONB blob
CREATE INDEX IF NOT EXISTS custom_rows_row_data_gin
  ON custom_rows USING GIN (row_data);
-- Composite for org-scoped time-range queries
CREATE INDEX IF NOT EXISTS custom_rows_org_connector
  ON custom_rows(org_id, connector_id, imported_at DESC);
-- NOTE: expression indexes are created per-connector at connector setup time.
-- Example (sanitized column name required):
--   CREATE INDEX IF NOT EXISTS custom_rows_{hex_id}_date
--     ON custom_rows((row_data->>'date')::date) WHERE connector_id = '...';

-- ──────────────────────────────────────────────
-- Sync run history
-- ──────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS sync_runs (
  id            BIGSERIAL PRIMARY KEY,
  connector_id  UUID NOT NULL REFERENCES connectors(id) ON DELETE CASCADE,
  org_id        UUID NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
  status        TEXT NOT NULL DEFAULT 'running'
    CHECK (status IN ('running', 'success', 'failed')),
  started_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  finished_at   TIMESTAMPTZ,
  rows_upserted INT,
  error_message TEXT
);
CREATE INDEX IF NOT EXISTS sync_runs_connector
  ON sync_runs(connector_id, started_at DESC);

-- ──────────────────────────────────────────────
-- Helper: webhook connector lookup (bypasses RLS intentionally)
-- The webhook POST endpoint needs to fetch the connector's org_id and HMAC
-- secret BEFORE it can set app.org_id (chicken-and-egg). This SECURITY
-- DEFINER function runs as the schema owner and bypasses RLS safely.
-- Only exposes (org_id, config) for type='webhook' rows looked up by exact id.
-- ──────────────────────────────────────────────
CREATE OR REPLACE FUNCTION get_webhook_connector(p_id UUID)
  RETURNS TABLE(org_id UUID, config JSONB)
  LANGUAGE SQL
  SECURITY DEFINER
  STABLE
AS $$
  SELECT org_id, config
  FROM   connectors
  WHERE  id   = p_id
    AND  type = 'webhook';
$$;

-- ──────────────────────────────────────────────
-- Row-Level Security
-- All tenant tables are isolated by org_id.
-- SET LOCAL app.org_id = '<uuid>' must be called inside every transaction
-- that touches these tables (via FastAPI DI — see app/deps.py).
-- The 'true' flag on current_setting means unset → NULL (not error).
-- NULL != any UUID → zero rows visible. Safe by default.
-- ──────────────────────────────────────────────
ALTER TABLE events       ENABLE ROW LEVEL SECURITY;
ALTER TABLE orders       ENABLE ROW LEVEL SECURITY;
ALTER TABLE connectors   ENABLE ROW LEVEL SECURITY;
ALTER TABLE alert_rules  ENABLE ROW LEVEL SECURITY;
ALTER TABLE custom_rows  ENABLE ROW LEVEL SECURITY;
ALTER TABLE sync_runs    ENABLE ROW LEVEL SECURITY;
-- FORCE makes RLS apply to table owners / superusers too —
-- critical for tests that connect as 'postgres'.
ALTER TABLE events       FORCE ROW LEVEL SECURITY;
ALTER TABLE orders       FORCE ROW LEVEL SECURITY;
ALTER TABLE connectors   FORCE ROW LEVEL SECURITY;
ALTER TABLE alert_rules  FORCE ROW LEVEL SECURITY;
ALTER TABLE custom_rows  FORCE ROW LEVEL SECURITY;
ALTER TABLE sync_runs    FORCE ROW LEVEL SECURITY;

DO $$ BEGIN
  -- NULLIF coerces empty string → NULL so ""::uuid never throws.
  -- current_setting('app.org_id', true) returns "" when unset; NULLIF makes it NULL.
  -- NULL = any_uuid → NULL (falsy) → zero rows visible.  Safe by default.
  -- DROP + CREATE is idempotent (CREATE OR REPLACE POLICY is not standard SQL).
  DROP POLICY IF EXISTS org_isolation ON events;
  DROP POLICY IF EXISTS org_isolation ON orders;
  DROP POLICY IF EXISTS org_isolation ON connectors;
  DROP POLICY IF EXISTS org_isolation ON alert_rules;
  DROP POLICY IF EXISTS org_isolation ON custom_rows;
  DROP POLICY IF EXISTS org_isolation ON sync_runs;
  CREATE POLICY org_isolation ON events
    USING (org_id = NULLIF(current_setting('app.org_id', true), '')::uuid);
  CREATE POLICY org_isolation ON orders
    USING (org_id = NULLIF(current_setting('app.org_id', true), '')::uuid);
  CREATE POLICY org_isolation ON connectors
    USING (org_id = NULLIF(current_setting('app.org_id', true), '')::uuid);
  CREATE POLICY org_isolation ON alert_rules
    USING (org_id = NULLIF(current_setting('app.org_id', true), '')::uuid);
  CREATE POLICY org_isolation ON custom_rows
    USING (org_id = NULLIF(current_setting('app.org_id', true), '')::uuid);
  CREATE POLICY org_isolation ON sync_runs
    USING (org_id = NULLIF(current_setting('app.org_id', true), '')::uuid);
END $$;

-- ──────────────────────────────────────────────
-- App role — non-superuser that is SUBJECT to RLS.
-- The app (and tests) use SET LOCAL ROLE app_role inside each
-- org-scoped transaction so that the RLS policies actually fire.
-- The postgres superuser has BYPASSRLS and ignores all policies,
-- even with FORCE ROW LEVEL SECURITY.
-- ──────────────────────────────────────────────
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_role') THEN
    CREATE ROLE app_role;
  END IF;
END $$;
-- Schema-level access (required before table grants can be used)
GRANT USAGE ON SCHEMA public TO app_role;
-- Data-level access — covers all tables created above in this file
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO app_role;
GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO app_role;
-- rate_limits is not RLS-protected but app_role still needs access (covered above,
-- re-stated here for documentation clarity).
DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
             WHERE p.proname = 'get_webhook_connector' AND n.nspname = 'public') THEN
    EXECUTE 'GRANT EXECUTE ON FUNCTION get_webhook_connector(UUID) TO app_role';
  END IF;
END $$;
