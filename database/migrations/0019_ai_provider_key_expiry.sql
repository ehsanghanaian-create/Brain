-- 0019: AI provider keys can be time-limited (e.g. 7-day Claude keys pasted in the panel).
-- An expired key is treated as absent, so routing falls back to the next configured provider (Grok, Gemini, …)
-- until a fresh key is entered. Idempotent: the migration runner skips "duplicate column" errors.
ALTER TABLE ai_providers ADD COLUMN key_set_at TEXT;
ALTER TABLE ai_providers ADD COLUMN key_expires_at TEXT;
