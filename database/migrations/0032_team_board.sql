-- Persistent card order and actionable checklist items for the project board.
ALTER TABLE work_items ADD COLUMN board_order REAL NOT NULL DEFAULT 0;
UPDATE work_items SET board_order = id * 1024 WHERE board_order = 0;
CREATE INDEX IF NOT EXISTS idx_work_items_board ON work_items(site_id,status,board_order,id);

CREATE TABLE IF NOT EXISTS work_checklist_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    site_id TEXT NOT NULL REFERENCES sites(site_id) ON DELETE CASCADE,
    work_item_id INTEGER NOT NULL REFERENCES work_items(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    done INTEGER NOT NULL DEFAULT 0 CHECK (done IN (0,1)),
    actor_id INTEGER REFERENCES panel_users(id) ON DELETE SET NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_work_checklist_item ON work_checklist_items(site_id,work_item_id,id);
