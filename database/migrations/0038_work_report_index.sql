CREATE INDEX IF NOT EXISTS idx_work_item_events_report
    ON work_item_events(created_at,site_id,actor_id);
