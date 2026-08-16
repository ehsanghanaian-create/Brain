# SEO Knowledge Graph (local-first, read-only)

A local SEO knowledge graph for **emdadmodiran.com** (Phase 1; multi-site ready via `site_id`).

- **Sources:** WordPress REST API (read-only), a robots-respecting crawler, Google Search Console (cached locally)
- **Storage:** SQLite (`data/seo.db`) — the source of truth
- **Human interface:** Obsidian vault (`obsidian/SEO-Knowledge-Graph/`) with wikilinks and Graph View
- **AI interface:** Claude Desktop via a local **stdio MCP server** exposing read-only tools
- **Guarantee:** the target website is never modified. The code base has no write path to WordPress.

See `docs/architecture-validation-report.md` for the Phase 0/1 audit and every architecture decision,
and `docs/` for setup, WordPress, GSC, Obsidian, MCP, graph schema, and troubleshooting guides.

## Quick start (Windows)

```powershell
cd seo-knowledge-graph
python -m venv .venv
.venv\Scripts\pip install -e .[dev]
copy .env.example .env         # fill values (never commit .env)
.venv\Scripts\python scripts\preflight.py
.venv\Scripts\python scripts\sync-wordpress.py
.venv\Scripts\python scripts\crawl.py --max-urls 20   # validate, then --full
.venv\Scripts\python scripts\sync-gsc.py --days 1     # validate, then --days 30
.venv\Scripts\python scripts\build-graph.py
.venv\Scripts\python scripts\analyze.py
.venv\Scripts\python scripts\run-mcp.py                # (Claude Desktop launches this itself)
.venv\Scripts\python scripts\dashboard.py              # http://127.0.0.1:3000/
```

Status of each phase is tracked in `docs/phase-log.md`.
