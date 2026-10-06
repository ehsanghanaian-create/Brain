-- Operator source corrections must not be overwritten by periodic reconciliation.
ALTER TABLE call_center_calls ADD COLUMN attribution_locked INTEGER NOT NULL DEFAULT 0;
