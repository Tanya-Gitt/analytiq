-- ── Feature Flags + A/B Experimentation ──────────────────────────────────────

CREATE TABLE IF NOT EXISTS feature_flags (
  id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id      UUID        NOT NULL,
  name        TEXT        NOT NULL,           -- slug: 'new-checkout', 'dark-mode'
  description TEXT        NOT NULL DEFAULT '',
  enabled     BOOLEAN     NOT NULL DEFAULT false,
  rollout_pct SMALLINT    NOT NULL DEFAULT 0
              CHECK (rollout_pct BETWEEN 0 AND 100),
  targeting   JSONB       NOT NULL DEFAULT '[]',
  -- targeting is a list of rules:
  -- [{"attribute":"plan","operator":"eq","value":"pro"},...]
  -- operators: eq | neq | contains | gt | lt
  created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (org_id, name)
);

CREATE INDEX IF NOT EXISTS feature_flags_org ON feature_flags(org_id);

-- Automatically bump updated_at on every update
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN NEW.updated_at = NOW(); RETURN NEW; END; $$;

DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_trigger WHERE tgname = 'feature_flags_updated_at'
  ) THEN
    CREATE TRIGGER feature_flags_updated_at
      BEFORE UPDATE ON feature_flags
      FOR EACH ROW EXECUTE FUNCTION set_updated_at();
  END IF;
END $$;

GRANT SELECT, INSERT, UPDATE, DELETE ON feature_flags TO app_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON feature_flags TO app_user;

ALTER TABLE feature_flags ENABLE ROW LEVEL SECURITY;
ALTER TABLE feature_flags FORCE  ROW LEVEL SECURITY;

CREATE POLICY feature_flags_org ON feature_flags
  USING (org_id::text = current_setting('app.org_id', true));
