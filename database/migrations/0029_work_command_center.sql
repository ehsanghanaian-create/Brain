CREATE TABLE IF NOT EXISTS panel_teams (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    color TEXT NOT NULL DEFAULT '#1abb9c',
    description TEXT NOT NULL DEFAULT '',
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
ALTER TABLE panel_users ADD COLUMN team_id INTEGER REFERENCES panel_teams(id) ON DELETE SET NULL;
ALTER TABLE work_items ADD COLUMN team_id INTEGER REFERENCES panel_teams(id) ON DELETE SET NULL;
ALTER TABLE work_items ADD COLUMN priority TEXT NOT NULL DEFAULT 'normal'
    CHECK (priority IN ('critical','high','normal','low'));
ALTER TABLE work_items ADD COLUMN estimated_hours REAL;
CREATE INDEX IF NOT EXISTS idx_panel_users_team ON panel_users(team_id);
CREATE INDEX IF NOT EXISTS idx_work_items_team_due ON work_items(team_id,due_at);
CREATE INDEX IF NOT EXISTS idx_work_items_priority ON work_items(priority,status,due_at);
