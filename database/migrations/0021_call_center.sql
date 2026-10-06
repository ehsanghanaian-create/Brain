-- Operator directory and completed-call ledger. Imported spreadsheet rows are deduplicated by import_key.
CREATE TABLE IF NOT EXISTS panel_users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    role TEXT NOT NULL CHECK (role IN ('admin', 'analyst', 'call_center')),
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS call_center_calls (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    site_id TEXT,
    occurred_at TEXT,
    customer_name TEXT NOT NULL DEFAULT '',
    phone TEXT NOT NULL DEFAULT '',
    warranty INTEGER NOT NULL DEFAULT 0,
    brand TEXT NOT NULL DEFAULT '',
    model TEXT NOT NULL DEFAULT '',
    region TEXT NOT NULL DEFAULT '',
    issue TEXT NOT NULL DEFAULT '',
    source TEXT NOT NULL DEFAULT 'unknown' CHECK (source IN ('seo', 'ads', 'direct', 'referral', 'unknown')),
    source_basis TEXT NOT NULL DEFAULT 'manual' CHECK (source_basis IN ('manual', 'customer', 'gclid', 'utm', 'import')),
    source_note TEXT NOT NULL DEFAULT '',
    campaign TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'new' CHECK (status IN ('new', 'follow_up', 'resolved', 'cancelled', 'unreviewed')),
    operator_id INTEGER REFERENCES panel_users(id) ON DELETE SET NULL,
    import_key TEXT UNIQUE,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_call_center_occurred ON call_center_calls(occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_call_center_source ON call_center_calls(source, occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_call_center_site ON call_center_calls(site_id, occurred_at DESC);
