"""SEO Brain data layer (SQLAlchemy Core + repositories).

* `engine.py`      – engine factory driven by DATABASE_URL (default: SQLite at data/seo.db)
* `migrate.py`     – forward-only SQL migrations from database/migrations/NNNN_*.sql
* `tables.py`      – SQLAlchemy Core Table definitions (Postgres-compatible types)
* `repositories/`  – one repository per aggregate; the ONLY place that knows table columns

The legacy module `seo_brain.database` (raw sqlite3) is still used by the v0.1 ingestion / graph
builder code and is migrated to repositories incrementally (see docs/seo-brain/02-phase1-implementation.md).
"""
