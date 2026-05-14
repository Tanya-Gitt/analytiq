-- Migration 007: Platform features — GDPR, Audit Log, API Keys, Embed Tokens,
--                Archived Events, and Scheduled Reports.
--
-- All statements use IF NOT EXISTS / IF EXISTS guards so this file is
-- idempotent and safe to re-run on existing databases.

-- ── gdpr_opt_outs ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS gdpr_opt_outs (
    id          BIGSERIAL    PRIMARY KEY,
    org_id      UUID         NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
    user_id     TEXT         NOT NULL,
    opted_out_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (org_id, user_id)
);

CREATE INDEX IF NOT EXISTS gdpr_opt_outs_org ON gdpr_opt_outs(org_id);
CREATE INDEX IF NOT EXISTS gdpr_opt_outs_user ON gdpr_opt_outs(user_id);

ALTER TABLE gdpr_opt_outs ENABLE ROW LEVEL SECURITY;
ALTER TABLE gdpr_opt_outs FORCE  ROW LEVEL SECURITY;

CREATE POLICY gdpr_opt_outs_org ON gdpr_opt_outs
    USING (org_id = current_setting('app.org_id', true)::uuid);

-- ── audit_log ─────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS audit_log (
    id            BIGSERIAL    PRIMARY KEY,
    org_id        UUID         NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
    actor_email   TEXT,
    action        TEXT         NOT NULL,
    resource_type TEXT,
    resource_id   TEXT,
    metadata      JSONB        NOT NULL DEFAULT '{}',
    created_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS audit_log_org_ts  ON audit_log(org_id, created_at DESC);
CREATE INDEX IF NOT EXISTS audit_log_action  ON audit_log(action);

ALTER TABLE audit_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_log FORCE  ROW LEVEL SECURITY;

CREATE POLICY audit_log_org ON audit_log
    USING (org_id = current_setting('app.org_id', true)::uuid);

-- ── api_keys ──────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS api_keys (
    id           UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id       UUID         NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
    name         TEXT         NOT NULL,
    key_prefix   TEXT         NOT NULL,
    key_hash     TEXT         NOT NULL,
    scopes       TEXT[]       NOT NULL DEFAULT '{}',
    created_by   UUID         REFERENCES users(id) ON DELETE SET NULL,
    revoked      BOOLEAN      NOT NULL DEFAULT FALSE,
    last_used_at TIMESTAMPTZ,
    expires_at   TIMESTAMPTZ,
    created_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS api_keys_org     ON api_keys(org_id, revoked);
CREATE INDEX IF NOT EXISTS api_keys_prefix  ON api_keys(key_prefix);

ALTER TABLE api_keys ENABLE ROW LEVEL SECURITY;
ALTER TABLE api_keys FORCE  ROW LEVEL SECURITY;

CREATE POLICY api_keys_org ON api_keys
    USING (org_id = current_setting('app.org_id', true)::uuid);

-- ── embed_tokens ──────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS embed_tokens (
    id          UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id      UUID         NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
    token       TEXT         NOT NULL UNIQUE,
    name        TEXT         NOT NULL,
    widget_type TEXT         NOT NULL,
    config      JSONB        NOT NULL DEFAULT '{}',
    expires_at  TIMESTAMPTZ,
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS embed_tokens_org   ON embed_tokens(org_id);
CREATE INDEX IF NOT EXISTS embed_tokens_token ON embed_tokens(token);

ALTER TABLE embed_tokens ENABLE ROW LEVEL SECURITY;
ALTER TABLE embed_tokens FORCE  ROW LEVEL SECURITY;

CREATE POLICY embed_tokens_org ON embed_tokens
    USING (org_id = current_setting('app.org_id', true)::uuid);

-- ── archived_events ───────────────────────────────────────────────────────────
-- Mirror of `events` for tiered cold storage; same columns, no RLS needed
-- (archival runs as admin, queries scoped in app layer).
CREATE TABLE IF NOT EXISTS archived_events (
    id           BIGSERIAL    PRIMARY KEY,
    org_id       UUID         NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
    event_name   TEXT         NOT NULL,
    user_id      TEXT,
    anonymous_id TEXT,
    properties   JSONB        NOT NULL DEFAULT '{}',
    received_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS archived_events_org_ts
    ON archived_events(org_id, received_at DESC);

ALTER TABLE archived_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE archived_events FORCE  ROW LEVEL SECURITY;

CREATE POLICY archived_events_org ON archived_events
    USING (org_id = current_setting('app.org_id', true)::uuid);

-- ── scheduled_reports ─────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS scheduled_reports (
    id           UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id       UUID         NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
    name         TEXT         NOT NULL,
    metric       TEXT         NOT NULL,
    period       TEXT         NOT NULL,   -- 'daily' | 'weekly' | 'monthly'
    recipients   TEXT[]       NOT NULL DEFAULT '{}',
    enabled      BOOLEAN      NOT NULL DEFAULT TRUE,
    created_by   UUID         REFERENCES users(id) ON DELETE SET NULL,
    last_run_at  TIMESTAMPTZ,
    created_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS scheduled_reports_org ON scheduled_reports(org_id);

ALTER TABLE scheduled_reports ENABLE ROW LEVEL SECURITY;
ALTER TABLE scheduled_reports FORCE  ROW LEVEL SECURITY;

CREATE POLICY scheduled_reports_org ON scheduled_reports
    USING (org_id = current_setting('app.org_id', true)::uuid);

-- ── event_schemas (schema registry) ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS event_schemas (
    id          BIGSERIAL    PRIMARY KEY,
    org_id      UUID         NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
    event_name  TEXT         NOT NULL,
    properties  JSONB        NOT NULL DEFAULT '{}',
    strict_mode BOOLEAN      NOT NULL DEFAULT FALSE,
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    UNIQUE (org_id, event_name)
);

CREATE INDEX IF NOT EXISTS event_schemas_org ON event_schemas(org_id);

ALTER TABLE event_schemas ENABLE ROW LEVEL SECURITY;
ALTER TABLE event_schemas FORCE  ROW LEVEL SECURITY;

CREATE POLICY event_schemas_org ON event_schemas
    USING (org_id = current_setting('app.org_id', true)::uuid);

-- ── schema_violations ────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS schema_violations (
    id           BIGSERIAL    PRIMARY KEY,
    org_id       UUID         NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
    event_name   TEXT         NOT NULL,
    violation    TEXT         NOT NULL,
    sample_props JSONB,
    occurred_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS schema_violations_org_ts ON schema_violations(org_id, occurred_at DESC);

ALTER TABLE schema_violations ENABLE ROW LEVEL SECURITY;
ALTER TABLE schema_violations FORCE  ROW LEVEL SECURITY;

CREATE POLICY schema_violations_org ON schema_violations
    USING (org_id = current_setting('app.org_id', true)::uuid);

-- ── pii_redactions ───────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS pii_redactions (
    id               BIGSERIAL    PRIMARY KEY,
    org_id           UUID         NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
    event_name       TEXT         NOT NULL,
    fields_redacted  JSONB        NOT NULL DEFAULT '[]',
    sample_count     BIGINT       NOT NULL DEFAULT 1,
    last_seen_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    occurred_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    UNIQUE (org_id, event_name)
);

CREATE INDEX IF NOT EXISTS pii_redactions_org ON pii_redactions(org_id);

ALTER TABLE pii_redactions ENABLE ROW LEVEL SECURITY;
ALTER TABLE pii_redactions FORCE  ROW LEVEL SECURITY;

CREATE POLICY pii_redactions_org ON pii_redactions
    USING (org_id = current_setting('app.org_id', true)::uuid);

-- ── Grants (applied after table creation) ─────────────────────────────────────
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_role') THEN
        GRANT SELECT, INSERT, UPDATE, DELETE ON gdpr_opt_outs     TO app_role;
        GRANT SELECT, INSERT, UPDATE, DELETE ON audit_log         TO app_role;
        GRANT SELECT, INSERT, UPDATE, DELETE ON api_keys          TO app_role;
        GRANT SELECT, INSERT, UPDATE, DELETE ON embed_tokens      TO app_role;
        GRANT SELECT, INSERT, UPDATE, DELETE ON archived_events   TO app_role;
        GRANT SELECT, INSERT, UPDATE, DELETE ON scheduled_reports TO app_role;
        GRANT SELECT, INSERT, UPDATE, DELETE ON event_schemas     TO app_role;
        GRANT SELECT, INSERT, UPDATE, DELETE ON schema_violations TO app_role;
        GRANT SELECT, INSERT, UPDATE, DELETE ON pii_redactions    TO app_role;
        GRANT USAGE, SELECT ON SEQUENCE gdpr_opt_outs_id_seq      TO app_role;
        GRANT USAGE, SELECT ON SEQUENCE audit_log_id_seq          TO app_role;
        GRANT USAGE, SELECT ON SEQUENCE archived_events_id_seq    TO app_role;
        GRANT USAGE, SELECT ON SEQUENCE event_schemas_id_seq      TO app_role;
        GRANT USAGE, SELECT ON SEQUENCE schema_violations_id_seq  TO app_role;
        GRANT USAGE, SELECT ON SEQUENCE pii_redactions_id_seq     TO app_role;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_user') THEN
        GRANT SELECT, INSERT, UPDATE, DELETE ON gdpr_opt_outs     TO app_user;
        GRANT SELECT, INSERT, UPDATE, DELETE ON audit_log         TO app_user;
        GRANT SELECT, INSERT, UPDATE, DELETE ON api_keys          TO app_user;
        GRANT SELECT, INSERT, UPDATE, DELETE ON embed_tokens      TO app_user;
        GRANT SELECT, INSERT, UPDATE, DELETE ON archived_events   TO app_user;
        GRANT SELECT, INSERT, UPDATE, DELETE ON scheduled_reports TO app_user;
        GRANT SELECT, INSERT, UPDATE, DELETE ON event_schemas     TO app_user;
        GRANT SELECT, INSERT, UPDATE, DELETE ON schema_violations TO app_user;
        GRANT SELECT, INSERT, UPDATE, DELETE ON pii_redactions    TO app_user;
        GRANT USAGE, SELECT ON SEQUENCE gdpr_opt_outs_id_seq      TO app_user;
        GRANT USAGE, SELECT ON SEQUENCE audit_log_id_seq          TO app_user;
        GRANT USAGE, SELECT ON SEQUENCE archived_events_id_seq    TO app_user;
        GRANT USAGE, SELECT ON SEQUENCE event_schemas_id_seq      TO app_user;
        GRANT USAGE, SELECT ON SEQUENCE schema_violations_id_seq  TO app_user;
        GRANT USAGE, SELECT ON SEQUENCE pii_redactions_id_seq     TO app_user;
    END IF;
END $$;
