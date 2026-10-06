-- Project labels and personal, reusable board views.
CREATE TABLE IF NOT EXISTS work_labels (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    site_id TEXT NOT NULL REFERENCES sites(site_id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    color TEXT NOT NULL DEFAULT '#64748b',
    created_at TEXT NOT NULL,
    UNIQUE(site_id,name)
);
CREATE INDEX IF NOT EXISTS idx_work_labels_site ON work_labels(site_id,name);

CREATE TABLE IF NOT EXISTS work_item_labels (
    work_item_id INTEGER NOT NULL REFERENCES work_items(id) ON DELETE CASCADE,
    label_id INTEGER NOT NULL REFERENCES work_labels(id) ON DELETE CASCADE,
    site_id TEXT NOT NULL REFERENCES sites(site_id) ON DELETE CASCADE,
    created_at TEXT NOT NULL,
    PRIMARY KEY(work_item_id,label_id)
);
CREATE INDEX IF NOT EXISTS idx_work_item_labels_site ON work_item_labels(site_id,label_id,work_item_id);

CREATE TABLE IF NOT EXISTS work_saved_views (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES panel_users(id) ON DELETE CASCADE,
    site_id TEXT NOT NULL REFERENCES sites(site_id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    config_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(user_id,site_id,name)
);
CREATE INDEX IF NOT EXISTS idx_work_saved_views_user_site ON work_saved_views(user_id,site_id,id);
