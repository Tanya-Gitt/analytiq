-- ── Heatmap click + scroll events ────────────────────────────────────────────
-- Separate table (not events) for efficient aggregation queries.
-- Populated by the JS SDK via POST /api/heatmap.

CREATE TABLE IF NOT EXISTS heatmap_events (
  id          BIGSERIAL   PRIMARY KEY,
  org_id      UUID        NOT NULL,
  page_url    TEXT        NOT NULL,   -- normalised: pathname only, query stripped
  event_type  TEXT        NOT NULL,   -- 'click' | 'scroll'
  x_pct       SMALLINT,              -- 0-100: % across viewport width  (clicks only)
  y_pct       SMALLINT,              -- 0-100: % down document height   (clicks + scroll)
  element     TEXT,                  -- CSS selector of clicked element (clicks only)
  user_id     TEXT,
  received_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS heatmap_events_org_url
  ON heatmap_events(org_id, page_url, received_at DESC);

GRANT SELECT, INSERT ON heatmap_events TO app_role;
GRANT SELECT, INSERT ON heatmap_events TO app_user;
GRANT USAGE, SELECT ON SEQUENCE heatmap_events_id_seq TO app_role;
GRANT USAGE, SELECT ON SEQUENCE heatmap_events_id_seq TO app_user;

ALTER TABLE heatmap_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE heatmap_events FORCE  ROW LEVEL SECURITY;

DROP POLICY IF EXISTS heatmap_events_org ON heatmap_events;
CREATE POLICY heatmap_events_org ON heatmap_events
  USING (org_id::text = current_setting('app.org_id', true));
