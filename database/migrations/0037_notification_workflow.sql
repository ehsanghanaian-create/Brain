ALTER TABLE panel_notifications ADD COLUMN audience TEXT NOT NULL DEFAULT 'assigned';
ALTER TABLE panel_notifications ADD COLUMN archived_at TEXT;
CREATE INDEX IF NOT EXISTS idx_panel_notifications_inbox
    ON panel_notifications(user_id,archived_at,audience,id DESC);
