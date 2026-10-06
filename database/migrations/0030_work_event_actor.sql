ALTER TABLE work_item_events ADD COLUMN actor_id INTEGER;
ALTER TABLE work_item_events ADD COLUMN actor_username TEXT;
CREATE INDEX IF NOT EXISTS idx_work_item_events_actor ON work_item_events(actor_id, created_at);
