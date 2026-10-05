-- A site is the project boundary; assignments and execution details extend the existing work ledger.
CREATE TABLE IF NOT EXISTS site_assignments (
    site_id TEXT NOT NULL REFERENCES sites(site_id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES panel_users(id) ON DELETE CASCADE,
    responsibility TEXT NOT NULL DEFAULT 'contributor'
        CHECK (responsibility IN ('lead','contributor','viewer')),
    created_at TEXT NOT NULL,
    PRIMARY KEY (site_id,user_id)
);
CREATE INDEX IF NOT EXISTS idx_site_assignments_user ON site_assignments(user_id,site_id);

ALTER TABLE work_items ADD COLUMN parent_id INTEGER REFERENCES work_items(id) ON DELETE SET NULL;
ALTER TABLE work_items ADD COLUMN start_at TEXT;
ALTER TABLE work_items ADD COLUMN progress_percent INTEGER NOT NULL DEFAULT 0
    CHECK (progress_percent BETWEEN 0 AND 100);
ALTER TABLE work_items ADD COLUMN milestone_id INTEGER REFERENCES work_milestones(id) ON DELETE SET NULL;
CREATE INDEX IF NOT EXISTS idx_work_items_parent ON work_items(site_id,parent_id);
CREATE INDEX IF NOT EXISTS idx_work_items_schedule ON work_items(site_id,start_at,due_at);

CREATE TABLE IF NOT EXISTS work_milestones (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    site_id TEXT NOT NULL REFERENCES sites(site_id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    due_at TEXT,
    description TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_work_milestones_site_due ON work_milestones(site_id,due_at);

CREATE TABLE IF NOT EXISTS work_dependencies (
    work_item_id INTEGER NOT NULL REFERENCES work_items(id) ON DELETE CASCADE,
    depends_on_id INTEGER NOT NULL REFERENCES work_items(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL,
    PRIMARY KEY (work_item_id,depends_on_id),
    CHECK (work_item_id <> depends_on_id)
);
CREATE INDEX IF NOT EXISTS idx_work_dependencies_target ON work_dependencies(depends_on_id);

CREATE TABLE IF NOT EXISTS work_time_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    site_id TEXT NOT NULL REFERENCES sites(site_id) ON DELETE CASCADE,
    work_item_id INTEGER NOT NULL REFERENCES work_items(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES panel_users(id),
    minutes INTEGER NOT NULL CHECK (minutes BETWEEN 1 AND 1440),
    work_date TEXT NOT NULL,
    note TEXT NOT NULL DEFAULT '',
    actor_id INTEGER REFERENCES panel_users(id) ON DELETE SET NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_work_time_item ON work_time_entries(site_id,work_item_id,work_date);
CREATE INDEX IF NOT EXISTS idx_work_time_user ON work_time_entries(user_id,work_date);
