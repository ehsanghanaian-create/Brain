# Final report — SEO Knowledge Graph for emdadmodiran.com

Date: 2026-08-17 · Repository: `seo-knowledge-graph/` (git, 5 commits + this one) · Runtime: Python 3.13, Windows 11.

## 1. What was built

A local-first, read-only SEO knowledge graph, per the plan's 13 phases:

| Layer | Delivered | Evidence |
|---|---|---|
| Ingestion | WordPress REST snapshot (GET only), robots-aware crawler, URL normalizer, GSC connector (code complete, live sync blocked — see §3) | `src/wordpress`, `src/crawler`, `src/normalizer`, `src/gsc`; `data/raw/` |
| Storage | SQLite with FTS5, 28 tables, `site_id` on every row, sync/crawl run tables | `src/database/schema.sql`, `data/seo.db` |
| Analysis | Entity extraction from real content (3 brands, 3 models, 1 service, 1 location) and 9 SEO problem types + internal-link opportunities, each explainable | `src/analysis` |
| Graph | networkx builder with PageRank + Louvain; **45 nodes / 298 edges** built only from real relationships | `src/graph/builder.py`, `graph_nodes`/`graph_edges` |
| Obsidian | Vault with 14 folders, 49 notes; wikilinks == graph edges; Obsidian 1.13.7 installed, vault registered, Dataview installed, Graph View verified | `obsidian/SEO-Knowledge-Graph`, `docs/screenshots/obsidian-graph-view.png` |
| MCP | `mcp` SDK 2.0 stdio server, 21 read-only tools, registered in Claude Desktop config (with backup) | `mcp/server.py`, `docs/mcp.md` |
| Dashboard | FastAPI on 127.0.0.1:3000, 9 pages + JSON API | `src/dashboard/app.py` |
| Tests | 27 passing (unit + MCP integration + 10 acceptance tests) | `pytest -q` |
| Docs | architecture, validation report, setup, wordpress, gsc, obsidian, mcp, graph-schema, troubleshooting, phase log | `docs/` |

## 2. Real data currently in the graph

* Site: 1 · Pages crawled: 19 (all HTTP 200; the whole discoverable site) · WordPress posts/pages: 14 · Categories: 4 with content · Media: 62
* Internal links: 172 (nav vs body distinguished) · External links: 12 · Schema.org entities: 117 (7 distinct types)
* Nodes: SITE 1, PAGE 4, POST 11, CATEGORY 4, BRAND 3, MODEL 3, SERVICE 1, LOCATION 1, SCHEMA 7, SEO_PROBLEM 9, SEO_OPPORTUNITY 1
* Edges: LINKS_TO 88, HAS_PROBLEM 57, HAS_SCHEMA 44, ABOUT 29, BELONGS_TO 24, OFFERS 14, HAS_OPPORTUNITY 14, HAS_POST 11, TARGETS 9, HAS_PAGE 4, HAS_CATEGORY 4
* SEO problems: 57 — images_missing_alt 19, multiple_h1 11, missing_meta_description 8, duplicate_h1 4, duplicate_title 4, no_body_inbound_links 4, orphan 3, low_inbound_links 3, missing_h1 1
* Internal-link opportunities: 86 (scored, with breakdown)
* GSC rows: 0 (blocked, §3) → QUERY nodes 0; GSC-based analyses report `NO_GSC_DATA` explicitly rather than guessing.

## 3. Blocked / requires the user

1. **Google Search Console (Phase 8 live sync)** — needs a Google Cloud OAuth *Desktop* client. Put `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` in `.env`, then:
   ```powershell
   .venv\Scripts\python scripts\sync-gsc.py --auth-only     # browser consent, refresh token saved to tokens/
   .venv\Scripts\python scripts\sync-gsc.py --days 1        # validation
   .venv\Scripts\python scripts\sync-gsc.py --days 30
   .venv\Scripts\python scripts\build-graph.py              # adds QUERY nodes, TARGETS/RANKS_FOR edges, GSC analyses
   ```
   Full walkthrough: `docs/gsc.md`.
2. **Claude Desktop restart** — the MCP server is registered; Claude Desktop must be restarted once to load it. Then ask Claude e.g. "list orphan pages on emdadmodiran" (tools: `docs/mcp.md`).
3. **Obsidian first-open prompt** — Obsidian may ask to trust community plugins (Dataview) for this vault; click *Trust*. The optional Local REST API plugin was not installed (needs an in-app generated key; nothing depends on it).
4. **WordPress app password (optional)** — without it only public REST endpoints are used (menus/authors unavailable). Add `WP_USERNAME`/`WP_APP_PASSWORD` to `.env` if wanted.

## 4. Deviations from the original plan (and why)

* **Graph engine:** obra/knowledge-graph was rejected after audit (dormant, broken MCP entrypoint, exposes write tools, no licence) in favour of `networkx` + SQLite FTS5 in the same Python process. Zero Node.js dependency; fully read-only. Details: `docs/architecture-validation-report.md`.
* **Obsidian install path:** winget stalled on the slow GitHub release host; the installer was fetched with a resumable download, its size and SHA-256 verified against the GitHub release digest, then installed silently.
* **Crawler cap** validated at 20, then raised to 500 in `config/site.yaml`; the site has only 19 discoverable URLs so both runs cover it fully.

## 5. Safety / read-only guarantees (verified)

* No HTTP write verbs anywhere in the codebase (acceptance test 10 greps for them). WordPress `modified` timestamps before/after all runs: 0 of 14 changed.
* MCP tools carry `readOnlyHint`; no file/SQL/credential tools; stdio only.
* Secrets: `.env`, `tokens/`, `*.db`, `data/raw/` git-ignored; masked in logs.
* Dashboard binds 127.0.0.1 only.

## 6. Environment risks noticed

* **Disk space on C: is critically low** (observed between 82 MB and 2.6 GB free during this work). Project footprint is ~250 MB (venv). Consider freeing space before running larger crawls or long GSC histories.
* Preflight: `python scripts\preflight.py` → 18 PASS / 9 WARNING / 1 FAIL (the FAIL is the missing GSC client credentials).

## 7. How to keep it fresh

```powershell
.venv\Scripts\python scripts\sync-wordpress.py
.venv\Scripts\python scripts\crawl.py --full
.venv\Scripts\python scripts\sync-gsc.py --days 30      # once credentials exist
.venv\Scripts\python scripts\build-graph.py             # rebuilds graph, vault notes, reports
```
Everything is idempotent (upserts keyed by URL/ID and `site_id`); a second site is a new entry in `config/site.yaml`.
