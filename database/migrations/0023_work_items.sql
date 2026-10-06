-- Site-scoped SEO action ledger. Events are append-only; the operator directory is not authentication.
CREATE TABLE IF NOT EXISTS work_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    site_id TEXT NOT NULL REFERENCES sites(site_id),
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    kind TEXT NOT NULL DEFAULT 'manual' CHECK (kind IN ('manual','issue','opportunity','content')),
    source_id INTEGER,
    url TEXT,
    query TEXT,
    status TEXT NOT NULL DEFAULT 'new' CHECK (status IN
        ('new','triaged','approved','assigned','in_progress','review','published',
         'measurement_pending','verified','blocked','rejected','deferred')),
    owner_id INTEGER REFERENCES panel_users(id) ON DELETE SET NULL,
    due_at TEXT,
    blocked_reason TEXT,
    verification_note TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_work_items_site_status ON work_items(site_id,status,due_at);
CREATE INDEX IF NOT EXISTS idx_work_items_site_owner ON work_items(site_id,owner_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_work_items_source ON work_items(site_id,kind,source_id);

CREATE TABLE IF NOT EXISTS work_item_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    site_id TEXT NOT NULL REFERENCES sites(site_id),
    work_item_id INTEGER NOT NULL REFERENCES work_items(id) ON DELETE CASCADE,
    event_type TEXT NOT NULL,
    before_json TEXT,
    after_json TEXT NOT NULL,
    note TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_work_item_events_item ON work_item_events(site_id,work_item_id,id);
