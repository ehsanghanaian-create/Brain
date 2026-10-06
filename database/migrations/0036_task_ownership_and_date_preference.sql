-- Keep personal task ownership and archive entire subtask trees together.
ALTER TABLE work_items ADD COLUMN deleted_root_id INTEGER REFERENCES work_items(id);
CREATE INDEX IF NOT EXISTS idx_work_items_deleted_root ON work_items(deleted_root_id);
ALTER TABLE panel_users ADD COLUMN date_calendar TEXT NOT NULL DEFAULT 'jalali'
    CHECK (date_calendar IN ('jalali','gregorian'));

-- Repair active descendants left visible after a parent was previously archived.
WITH RECURSIVE orphaned(root_id, child_id, removed_at) AS (
    SELECT parent.id, child.id, parent.deleted_at
    FROM work_items parent JOIN work_items child ON child.parent_id=parent.id
    WHERE parent.deleted_at IS NOT NULL AND child.deleted_at IS NULL
    UNION ALL
    SELECT orphaned.root_id, child.id, orphaned.removed_at
    FROM orphaned JOIN work_items child ON child.parent_id=orphaned.child_id
    WHERE child.deleted_at IS NULL
)
UPDATE work_items
SET deleted_at=(SELECT removed_at FROM orphaned WHERE child_id=work_items.id LIMIT 1),
    deleted_root_id=(SELECT root_id FROM orphaned WHERE child_id=work_items.id LIMIT 1)
WHERE id IN (SELECT child_id FROM orphaned);
