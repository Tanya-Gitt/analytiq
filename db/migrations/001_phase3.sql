-- Phase 3 migrations: share_tokens + annotations
-- Run once; idempotent (IF NOT EXISTS throughout).

-- ── share_tokens ──────────────────────────────────────────────────────────────
-- A share token lets anyone with the URL view a read-only snapshot of the
-- dashboard for a specific org + segment + time window, without logging in.
-- token: 32-char hex (128-bit entropy from gen_random_bytes(16))
-- expires_at: NULL = never expires; set by the creator
-- label: optional human-readable name shown on the public page

CREATE TABLE IF NOT EXISTS share_tokens (
    id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id      UUID        NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
    token       TEXT        NOT NULL UNIQUE DEFAULT encode(gen_random_bytes(16), 'hex'),
    segment     TEXT        NOT NULL CHECK (segment IN ('A', 'B')),
    days        INT         NOT NULL DEFAULT 30 CHECK (days BETWEEN 1 AND 365),
    label       TEXT        NOT NULL DEFAULT '',
    expires_at  TIMESTAMPTZ,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS share_tokens_org ON share_tokens(org_id);
CREATE INDEX IF NOT EXISTS share_tokens_token ON share_tokens(token);

-- RLS on share_tokens:
--   SELECT: open when app.org_id is unset (public token lookup by 32-char hex);
--           restricted to owning org when app.org_id is set (authenticated list).
--   INSERT/UPDATE/DELETE: always require org context.
-- The open SELECT is safe because tokens are unguessable (128-bit random hex).
ALTER TABLE share_tokens ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
  DROP POLICY IF EXISTS org_isolation       ON share_tokens;
  DROP POLICY IF EXISTS share_tokens_select ON share_tokens;
  DROP POLICY IF EXISTS share_tokens_insert ON share_tokens;
  DROP POLICY IF EXISTS share_tokens_update ON share_tokens;
  DROP POLICY IF EXISTS share_tokens_delete ON share_tokens;

  CREATE POLICY share_tokens_select ON share_tokens FOR SELECT
      USING (
          NULLIF(current_setting('app.org_id', true), '') IS NULL
          OR org_id = NULLIF(current_setting('app.org_id', true), '')::uuid
      );

  CREATE POLICY share_tokens_insert ON share_tokens FOR INSERT
      WITH CHECK (org_id = NULLIF(current_setting('app.org_id', true), '')::uuid);

  CREATE POLICY share_tokens_update ON share_tokens FOR UPDATE
      USING (org_id = NULLIF(current_setting('app.org_id', true), '')::uuid)
      WITH CHECK (org_id = NULLIF(current_setting('app.org_id', true), '')::uuid);

  CREATE POLICY share_tokens_delete ON share_tokens FOR DELETE
      USING (org_id = NULLIF(current_setting('app.org_id', true), '')::uuid);
END $$;

-- ── annotations ───────────────────────────────────────────────────────────────
-- A dated label that appears as a ReferenceLine on the dashboard charts.
-- date: which day the annotation marks (shown on x-axis)
-- label: short text shown in the tooltip
-- color: CSS hex or named colour for the reference line

CREATE TABLE IF NOT EXISTS annotations (
    id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id      UUID        NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
    segment     TEXT        NOT NULL CHECK (segment IN ('A', 'B')),
    date        DATE        NOT NULL,
    label       TEXT        NOT NULL CHECK (char_length(label) BETWEEN 1 AND 120),
    color       TEXT        NOT NULL DEFAULT '#6366f1',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS annotations_org_seg ON annotations(org_id, segment, date);

ALTER TABLE annotations ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
  DROP POLICY IF EXISTS org_isolation ON annotations;
  CREATE POLICY org_isolation ON annotations
    USING (org_id = NULLIF(current_setting('app.org_id', true), '')::uuid);
END $$;

-- ── Grant access to app_role ───────────────────────────────────────────────────
GRANT SELECT, INSERT, UPDATE, DELETE ON share_tokens TO app_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON annotations  TO app_role;
