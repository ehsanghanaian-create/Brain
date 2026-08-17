# Setup (Windows 11)

## Prerequisites (verified 2026-08-16)

| Component | Required | Notes |
|---|---|---|
| Python 3.11–3.13 | yes | 3.13.0 installed; project venv `.venv` |
| Git | yes | 2.55 |
| Obsidian ≥ 1.13.1 | for viewing the graph | `winget install --id Obsidian.Obsidian -e` (installer is fetched from GitHub releases; slow networks may need a manual download of `Obsidian-1.13.7.exe`, SHA256 `F233DC24896B3F2D5F9E4B01111181A561D0760B2105F0A474024C5F3143A9BC`) |
| Claude Desktop | for MCP | installed (1.30096.5) |
| Node.js | **no** | not used by this architecture |

## Steps

```powershell
cd C:\Users\Lenovo\Documents\Plan\seo-knowledge-graph
python -m venv .venv
.venv\Scripts\python -m pip install -e .[dev]
.venv\Scripts\python backend\cli\setup.py --env --vault --db      # .env from template, vault folders, schema
notepad .env                                                   # fill credentials (never commit)
.venv\Scripts\python backend\cli\preflight.py                      # PASS/WARNING/FAIL table
```

Data pipeline (in order):

```powershell
.venv\Scripts\python backend\cli\sync-wordpress.py
.venv\Scripts\python backend\cli\crawl.py --max-urls 20            # validation crawl
.venv\Scripts\python backend\cli\crawl.py --full                   # after validation
.venv\Scripts\python backend\cli\sync-gsc.py --auth-only           # one-time browser consent (needs GOOGLE_CLIENT_ID/SECRET)
.venv\Scripts\python backend\cli\sync-gsc.py --days 1              # validation sync
.venv\Scripts\python backend\cli\sync-gsc.py --days 30             # after validation
.venv\Scripts\python backend\cli\build-graph.py --limit-pages 15   # first graph
.venv\Scripts\python backend\cli\build-graph.py                    # full graph (entities + analysis + Obsidian)
```

Interfaces:

```powershell
.venv\Scripts\python backend\cli\setup.py --claude-config          # registers MCP server (backs up config)
.venv\Scripts\python backend\cli\dashboard.py                      # http://127.0.0.1:3000/
.venv\Scripts\python -m pytest -q                              # unit + integration tests
```

Open the vault in Obsidian: *Open folder as vault* → `obsidian\SEO-Knowledge-Graph`. Graph View is a core plugin (enabled by the generated `.obsidian/core-plugins.json`); Dataview and Local REST API are optional community plugins.

## Refresh cycle

Re-run `sync-wordpress` → `crawl --full` → `sync-gsc --days 30` → `build-graph`. All steps are idempotent (upserts). Vault notes are regenerated (manual edits inside generated files are overwritten).

> **Note (2026-08-17):** paths in this document were rewritten after the SEO Brain Phase 1 restructure (`backend/seo_brain/`→`backend/seo_brain/`, `backend/cli/`→`backend/cli/`, `mcp/`→`backend/mcp_server/`). Historical commit references are unchanged.
