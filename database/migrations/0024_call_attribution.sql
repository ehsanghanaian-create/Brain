-- A time-only match is a probable suggestion, never proof of caller identity.
ALTER TABLE call_center_calls ADD COLUMN attribution_event TEXT;
ALTER TABLE call_center_calls ADD COLUMN attribution_checked_at TEXT;
ALTER TABLE call_center_calls ADD COLUMN auto_attributed INTEGER NOT NULL DEFAULT 0;
CREATE INDEX IF NOT EXISTS idx_track_events_tel_time ON track_events(site_id, type, ts);
CREATE INDEX IF NOT EXISTS idx_ads_events_tel_time ON ads_click_events(site_id, event_type, received_at);
