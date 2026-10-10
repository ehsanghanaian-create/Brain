-- Manual work projects share the existing project boundary without entering SEO site inventory.
CREATE TABLE IF NOT EXISTS manual_projects (
    site_id TEXT PRIMARY KEY REFERENCES sites(site_id) ON DELETE CASCADE,
    created_by_id INTEGER REFERENCES panel_users(id) ON DELETE SET NULL,
    created_at TEXT NOT NULL
);

ALTER TABLE work_items ADD COLUMN created_by_id INTEGER REFERENCES panel_users(id) ON DELETE SET NULL;
ALTER TABLE work_items ADD COLUMN deleted_at TEXT;
ALTER TABLE work_items ADD COLUMN deleted_by_id INTEGER REFERENCES panel_users(id) ON DELETE SET NULL;

UPDATE work_items SET created_by_id=(
    SELECT e.actor_id FROM work_item_events e
    WHERE e.work_item_id=work_items.id AND e.event_type='created'
    ORDER BY e.id LIMIT 1
);
CREATE INDEX IF NOT EXISTS idx_work_items_creator ON work_items(created_by_id,deleted_at,created_at);
CREATE INDEX IF NOT EXISTS idx_work_items_archive ON work_items(deleted_at,status,site_id);

CREATE TABLE IF NOT EXISTS panel_notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES panel_users(id) ON DELETE CASCADE,
    work_item_id INTEGER REFERENCES work_items(id) ON DELETE CASCADE,
    kind TEXT NOT NULL,
    title TEXT NOT NULL,
    body TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    read_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_panel_notifications_user ON panel_notifications(user_id,read_at,id DESC);
