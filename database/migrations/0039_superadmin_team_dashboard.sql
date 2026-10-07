ALTER TABLE panel_users ADD COLUMN is_superadmin INTEGER NOT NULL DEFAULT 0;
UPDATE panel_users SET is_superadmin=1 WHERE username='manager' AND role='admin';
