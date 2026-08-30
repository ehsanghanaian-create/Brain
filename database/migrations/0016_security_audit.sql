-- 0016: audit trail for site security actions (IP block/unblock relayed to the site's WP plugin).
-- Brain never blocks on its own; every human-triggered relay is recorded here.
CREATE TABLE IF NOT EXISTS security_audit (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    site_id     TEXT NOT NULL,
    ip          TEXT NOT NULL,
    action      TEXT NOT NULL,              -- block | unblock
    reason      TEXT,
    ok          INTEGER NOT NULL DEFAULT 0, -- 1 = plugin confirmed
    status      TEXT,                       -- blocked | already_blocked | unblocked | already_unblocked | error
    message     TEXT,                       -- mapped error detail (never raw secrets)
    actor       TEXT NOT NULL DEFAULT 'human',
    created_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_security_audit_site ON security_audit(site_id, created_at DESC);
