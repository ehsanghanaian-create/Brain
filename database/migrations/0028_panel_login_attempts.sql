CREATE TABLE IF NOT EXISTS panel_login_attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL,
    attempted_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_panel_login_attempts_user_time
    ON panel_login_attempts(username, attempted_at);
