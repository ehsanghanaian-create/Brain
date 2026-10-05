-- Explicit business outcomes; completed calls, qualified leads and orders are distinct.
ALTER TABLE call_center_calls ADD COLUMN outcome TEXT NOT NULL DEFAULT 'pending'
    CHECK (outcome IN ('pending','qualified','unqualified','order','lost'));
ALTER TABLE call_center_calls ADD COLUMN order_value INTEGER;
ALTER TABLE call_center_calls ADD COLUMN follow_up_at TEXT;
ALTER TABLE call_center_calls ADD COLUMN source_confidence TEXT NOT NULL DEFAULT 'unknown'
    CHECK (source_confidence IN ('confirmed','probable','unknown'));
CREATE INDEX IF NOT EXISTS idx_call_center_outcome ON call_center_calls(site_id,outcome,occurred_at);
