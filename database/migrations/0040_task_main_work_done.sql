-- Record completion of the main assignment separately from its remaining steps.
ALTER TABLE work_items ADD COLUMN main_work_done INTEGER NOT NULL DEFAULT 0
    CHECK (main_work_done IN (0,1));
UPDATE work_items SET main_work_done=1 WHERE status='verified';
