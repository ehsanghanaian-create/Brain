ALTER TABLE panel_users ADD COLUMN username TEXT;
ALTER TABLE panel_users ADD COLUMN password_hash TEXT;
CREATE UNIQUE INDEX IF NOT EXISTS idx_panel_users_username ON panel_users(username);

CREATE TABLE IF NOT EXISTS panel_sessions (
    token_hash TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES panel_users(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    revoked_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_panel_sessions_user ON panel_sessions(user_id, expires_at);

CREATE TABLE IF NOT EXISTS panel_audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    actor_id INTEGER REFERENCES panel_users(id) ON DELETE SET NULL,
    actor_username TEXT NOT NULL,
    actor_role TEXT NOT NULL,
    method TEXT NOT NULL,
    path TEXT NOT NULL,
    status_code INTEGER NOT NULL,
    changed_fields TEXT NOT NULL DEFAULT '[]',
    request_id TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_panel_audit_actor_time ON panel_audit_log(actor_id, created_at DESC);
