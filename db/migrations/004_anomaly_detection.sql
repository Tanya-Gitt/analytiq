-- Phase 6 migrations: statistical anomaly detection
-- Idempotent throughout (IF NOT EXISTS / ON CONFLICT DO UPDATE).

-- ── anomaly_baselines: per-org, per-metric, per (dow, hour) statistical model ─
-- DOW-adjusted baseline captures weekly seasonality without needing scipy:
--   Monday 14:00 events baseline ≠ Saturday 14:00 events baseline.
CREATE TABLE IF NOT EXISTS anomaly_baselines (
  id           BIGSERIAL PRIMARY KEY,
  org_id       UUID       NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
  metric       TEXT       NOT NULL,
  dow          SMALLINT   NOT NULL,   -- 0=Sunday … 6=Saturday (EXTRACT dow)
  hour         SMALLINT   NOT NULL,   -- 0–23
  mean         DOUBLE PRECISION NOT NULL,
  std_dev      DOUBLE PRECISION NOT NULL DEFAULT 0,
  sample_count INT        NOT NULL DEFAULT 0,
  computed_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE(org_id, metric, dow, hour)
);
CREATE INDEX IF NOT EXISTS anomaly_baselines_org ON anomaly_baselines(org_id, metric);

-- ── anomaly_events: detected deviations ───────────────────────────────────────
CREATE TABLE IF NOT EXISTS anomaly_events (
  id           BIGSERIAL PRIMARY KEY,
  org_id       UUID       NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
  metric       TEXT       NOT NULL,
  value        DOUBLE PRECISION NOT NULL,   -- observed value
  baseline     DOUBLE PRECISION NOT NULL,   -- expected (mean for that dow+hour)
  std_dev      DOUBLE PRECISION NOT NULL,
  z_score      DOUBLE PRECISION NOT NULL,   -- (value - mean) / std_dev
  direction    TEXT       NOT NULL,         -- 'high' | 'low'
  severity     TEXT       NOT NULL,         -- 'warning' (3–4σ) | 'critical' (>4σ)
  detected_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS anomaly_events_org_ts
  ON anomaly_events(org_id, detected_at DESC);

-- ── Grant permissions ─────────────────────────────────────────────────────────
GRANT SELECT, INSERT, UPDATE, DELETE ON anomaly_baselines TO app_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON anomaly_events    TO app_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON anomaly_baselines TO app_user;
GRANT SELECT, INSERT, UPDATE, DELETE ON anomaly_events    TO app_user;
GRANT USAGE, SELECT ON SEQUENCE anomaly_baselines_id_seq TO app_role;
GRANT USAGE, SELECT ON SEQUENCE anomaly_events_id_seq    TO app_role;
GRANT USAGE, SELECT ON SEQUENCE anomaly_baselines_id_seq TO app_user;
GRANT USAGE, SELECT ON SEQUENCE anomaly_events_id_seq    TO app_user;

-- RLS
ALTER TABLE anomaly_baselines ENABLE ROW LEVEL SECURITY;
ALTER TABLE anomaly_events    ENABLE ROW LEVEL SECURITY;
ALTER TABLE anomaly_baselines FORCE  ROW LEVEL SECURITY;
ALTER TABLE anomaly_events    FORCE  ROW LEVEL SECURITY;

DROP POLICY IF EXISTS anomaly_baselines_org ON anomaly_baselines;
CREATE POLICY anomaly_baselines_org ON anomaly_baselines
  USING (org_id::text = current_setting('app.org_id', true));
DROP POLICY IF EXISTS anomaly_events_org ON anomaly_events;
CREATE POLICY anomaly_events_org ON anomaly_events
  USING (org_id::text = current_setting('app.org_id', true));
