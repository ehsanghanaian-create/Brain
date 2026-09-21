# WordPress taxonomy sync writer lock — 2026-09-21

Live resync of kermanmootor and a scheduled emdadmodiran-com sync failed with
`sqlite3.OperationalError: database is locked`. The taxonomy loop acquired a
SQLite writer lock before calling the progress hook, whose pipeline state write
uses another connection. It also retained the lock during REST requests.

Progress and term fetching now run before the short taxonomy/term write burst.
Failed transactions roll back before writing failure status. Existing content,
credentials, and site configuration are preserved.

Build from repository root:

```sh
docker build -f deploy/seo-brain/wp-sync-lock-fix/Dockerfile -t seo-brain-backend:20260921-wp-sync-lock-v1 .
```

This patch layers on the Google grant/refresh repair. Retain compose volumes and
save the previous compose file for rollback. Verify targeted WordPress tests,
backend health, and successful live sync before treating failed runs as repaired.
