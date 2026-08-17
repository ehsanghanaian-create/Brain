# Google Search Console connector

Status (2026-08-17): **LIVE — connected to `sc-domain:emdadmodiran.com` (siteOwner), 30-day sync done, graph rebuilt.** See `gsc-integration-report.md`.

## One-time setup (you)

1. Google Cloud Console → create/select a project → *APIs & Services → Library* → enable **Google Search Console API**.
2. *OAuth consent screen* → External, Testing; add the Google account that owns the GSC property as a test user.
3. *Credentials → Create credentials → OAuth client ID → Application type: Desktop app*. Copy client ID + secret into `.env`:
   ```
   GOOGLE_CLIENT_ID=...
   GOOGLE_CLIENT_SECRET=...
   GSC_PROPERTY=https://emdadmodiran.com/      # or sc-domain:emdadmodiran.com
   ```
4. `python backend/cli/sync-gsc.py --auth-only` → a browser opens once (loopback `127.0.0.1`, random port), you consent, the refresh token is written to `tokens/gsc_token.json` (git-ignored).
5. `python backend/cli/sync-gsc.py --list-sites` shows the properties the account can see; `resolve_property()` accepts URL-prefix or Domain form automatically.

## Sync behaviour

* `--days 1` first (validation), then `--days 30` (config `gsc.lookback_days`), or explicit `--start/--end`.
* Dimensions: `date, query, page, country, device` (config). Rows per request ≤ 25 000, paginated with `startRow`.
* Data lag: window ends at `today − 3 days`.
* Raw responses → `data/raw/gsc/<site_id>/sa_<start>_<end>_<dims>_p<n>.json`.
* Storage: `gsc_daily` (unique per date/page/query/country/device, upsert → re-sync is idempotent) → `gsc_query_page` (aggregated, impression-weighted position) → `queries` (+ `is_important` flag: impressions ≥ 50, clicks ≥ 5, position ≤ 10 with ≥ 5 impressions, or ranking on ≥ 2 pages — thresholds in `config/site.yaml → graph`).
* Retry with exponential backoff on 429/5xx; 401/403 stops with `AUTH_FAILED`.

## Quota strategy

Claude never calls GSC. All tools (`get_gsc_page_data`, `get_gsc_query_data`, cannibalization, striking distance, CTR) read SQLite. Run the sync on a schedule (e.g. Windows Task Scheduler daily: `.venv\Scripts\python backend\cli\sync-gsc.py --days 30 --non-interactive` followed by `build-graph.py`).

## Not implemented (hooks only)

URL Inspection API (would need a queue table, priority, rate limit of 2 000/day, cache), GA4, Google Ads.
