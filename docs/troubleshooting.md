# Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `preflight.py` → `Python dependencies FAIL` | not running inside the venv | use `.venv\Scripts\python backend\cli\preflight.py` or `pip install -e .[dev]` |
| `sync-gsc.py` prints `BLOCKED: GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET missing` | no OAuth client configured | follow `docs/gsc.md` §one-time setup |
| `sync-gsc.py` → `property ... not found ...; available: [...]` | account lacks access or property string differs | set `GSC_PROPERTY` to one of the listed values (URL-prefix vs `sc-domain:`) |
| GSC 403 `insufficientPermissions` | account is not a user of the property | add the account in Search Console → Settings → Users |
| Crawl shows `skipped_robots` | URL disallowed by robots.txt | expected; do not bypass |
| Crawl `crawled=0` | site unreachable / WAF | check `data/logs/crawl.jsonl`; UA is `SEO-KG-Crawler/0.1` |
| Claude Desktop does not show the server | config not loaded / wrong paths | fully quit Claude Desktop (tray) and restart; check `%APPDATA%\Claude\logs\mcp-server-seo-knowledge-graph.log`; run `python mcp\server.py` manually — it must wait silently on stdin |
| MCP tool returns `NO_GSC_DATA` | GSC not synced | run `sync-gsc.py`, then `build-graph.py` |
| Persian filenames look garbled in a shell | console code page | run with `PYTHONUTF8=1` (already set in the Claude config `env`) |
| Obsidian graph shows unresolved links | vault opened at the wrong root | open `obsidian/SEO-Knowledge-Graph` itself as the vault (folder containing `.obsidian`) |
| Duplicate nodes suspected | URL variants | check `backend/seo_brain/normalizer/url.py` tests; builder validation prints `dup urls` |
| `winget install Obsidian` stalls | GitHub release asset host is slow on this network | download `Obsidian-1.13.7.exe` manually, verify SHA256 `F233DC24…3143A9BC`, run it (or `/S` for silent) |
| Logs contain a secret | should never happen | `mask_secrets()` masks env values + token patterns; report if seen |
