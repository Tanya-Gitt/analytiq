-- Phase 4 migrations: team invites + custom funnels
-- Idempotent throughout (IF NOT EXISTS / ADD COLUMN IF NOT EXISTS).

-- ── Add role column to users ───────────────────────────────────────────────────
-- 'admin'  can invite/remove members and manage org settings
-- 'viewer' read-only access to dashboards
ALTER TABLE users
  ADD COLUMN IF NOT EXISTS role TEXT NOT NULL DEFAULT 'admin'
  CHECK (role IN ('admin', 'viewer'));

-- ── org_invites ────────────────────────────────────────────────────────────────
-- A pending invitation to join an org.
-- token: 32-char hex (128-bit entropy), the link credential
-- role: what role the invited user gets on accept
-- accepted_at: NULL = still pending
-- expires_at: invite link is valid for 7 days by default

CREATE TABLE IF NOT EXISTS org_invites (
    id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id      UUID        NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
    email       TEXT        NOT NULL,
    role        TEXT        NOT NULL DEFAULT 'viewer' CHECK (role IN ('admin', 'viewer')),
    token       TEXT        NOT NULL UNIQUE DEFAULT encode(gen_random_bytes(16), 'hex'),
    invited_by  UUID        REFERENCES users(id) ON DELETE SET NULL,
    accepted_at TIMESTAMPTZ,
    expires_at  TIMESTAMPTZ NOT NULL DEFAULT NOW() + INTERVAL '7 days',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS org_invites_org   ON org_invites(org_id);
CREATE INDEX IF NOT EXISTS org_invites_token ON org_invites(token);
CREATE INDEX IF NOT EXISTS org_invites_email ON org_invites(email);

ALTER TABLE org_invites ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
  -- SELECT: open when no org context (public invite lookup by token)
  --         restricted to owning org when context is set
  DROP POLICY IF EXISTS org_invites_select ON org_invites;
  DROP POLICY IF EXISTS org_invites_insert ON org_invites;
  DROP POLICY IF EXISTS org_invites_update ON org_invites;
  DROP POLICY IF EXISTS org_invites_delete ON org_invites;

  CREATE POLICY org_invites_select ON org_invites FOR SELECT
      USING (
          NULLIF(current_setting('app.org_id', true), '') IS NULL
          OR org_id = NULLIF(current_setting('app.org_id', true), '')::uuid
      );

  CREATE POLICY org_invites_insert ON org_invites FOR INSERT
      WITH CHECK (org_id = NULLIF(current_setting('app.org_id', true), '')::uuid);

  CREATE POLICY org_invites_update ON org_invites FOR UPDATE
      USING (org_id = NULLIF(current_setting('app.org_id', true), '')::uuid)
      WITH CHECK (org_id = NULLIF(current_setting('app.org_id', true), '')::uuid);

  CREATE POLICY org_invites_delete ON org_invites FOR DELETE
      USING (org_id = NULLIF(current_setting('app.org_id', true), '')::uuid);
END $$;

-- ── funnels ────────────────────────────────────────────────────────────────────
-- A user-defined ordered list of event steps.
-- steps: JSONB array of strings, e.g. ["page_view","add_to_cart","purchase"]
-- segment: 'A' only (funnels are event-based, not order-based)

CREATE TABLE IF NOT EXISTS funnels (
    id         UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id     UUID        NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
    name       TEXT        NOT NULL CHECK (char_length(name) BETWEEN 1 AND 120),
    steps      JSONB       NOT NULL DEFAULT '[]',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS funnels_org ON funnels(org_id);

ALTER TABLE funnels ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
  DROP POLICY IF EXISTS org_isolation ON funnels;
  CREATE POLICY org_isolation ON funnels
    USING (org_id = NULLIF(current_setting('app.org_id', true), '')::uuid);
END $$;

-- ── Grants ─────────────────────────────────────────────────────────────────────
GRANT SELECT, INSERT, UPDATE, DELETE ON org_invites TO app_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON funnels     TO app_role;
