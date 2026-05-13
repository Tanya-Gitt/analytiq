-- Phase 5 migrations: SSO / OAuth 2.0 / OIDC
-- Idempotent throughout (IF NOT EXISTS / ADD COLUMN IF NOT EXISTS).

-- ── users: make password_hash nullable (SSO users have no password) ────────────
ALTER TABLE users
  ALTER COLUMN password_hash DROP NOT NULL;

-- ── users: SSO identity columns ───────────────────────────────────────────────
ALTER TABLE users
  ADD COLUMN IF NOT EXISTS sso_provider TEXT,   -- 'google' | 'github' | 'oidc'
  ADD COLUMN IF NOT EXISTS sso_sub      TEXT;   -- subject from OIDC id_token / GitHub user id

-- Unique index: one user row per provider+sub per org
CREATE UNIQUE INDEX IF NOT EXISTS users_sso_sub
  ON users(org_id, sso_provider, sso_sub)
  WHERE sso_provider IS NOT NULL;

-- ── sso_configs: per-org OIDC configuration (Okta, Azure AD, Keycloak, …) ─────
CREATE TABLE IF NOT EXISTS sso_configs (
  id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id         UUID NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
  provider       TEXT NOT NULL DEFAULT 'oidc',     -- 'google' | 'github' | 'oidc'
  client_id      TEXT NOT NULL,
  client_secret  TEXT NOT NULL,                     -- stored encrypted at rest (app-level AES)
  discovery_url  TEXT,                              -- OIDC discovery base URL (NULL for github)
  enabled        BOOLEAN NOT NULL DEFAULT TRUE,
  created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE(org_id, provider)
);

-- ── oauth_states: short-lived PKCE / CSRF state storage (no Redis needed) ─────
CREATE TABLE IF NOT EXISTS oauth_states (
  state       TEXT PRIMARY KEY,                     -- random 32-byte hex
  provider    TEXT NOT NULL,
  org_id      UUID REFERENCES orgs(id) ON DELETE CASCADE,  -- NULL for new-user flows
  redirect_to TEXT NOT NULL DEFAULT '/dashboard',
  created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  expires_at  TIMESTAMPTZ NOT NULL DEFAULT NOW() + INTERVAL '10 minutes'
);

-- Auto-clean expired states (runs on any cleanup job; app also ignores expired)
CREATE INDEX IF NOT EXISTS oauth_states_expires ON oauth_states(expires_at);
