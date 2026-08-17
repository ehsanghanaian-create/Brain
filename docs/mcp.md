# MCP server (Claude Desktop)

File: `backend/mcp_server/server.py` — Python `mcp` SDK **2.0.0** (`mcp.server.mcpserver.MCPServer`; verified against the installed package on 2026-08-16 — the older `mcp.server.fastmcp.FastMCP` import no longer exists in 2.x). Transport: **stdio** (no port; inherently local).

## Claude Desktop configuration (verified format, modelcontextprotocol.io/quickstart/user)

File: `%APPDATA%\Claude\claude_desktop_config.json`. `backend/cli/setup.py --claude-config` backs the file up (`claude_desktop_config.backup-<timestamp>.json`), preserves all existing keys/servers and adds:

```json
{
  "mcpServers": {
    "seo-knowledge-graph": {
      "command": "C:\\Users\\Lenovo\\Documents\\Plan\\seo-knowledge-graph\\.venv\\Scripts\\python.exe",
      "args": ["C:\\Users\\Lenovo\\Documents\\Plan\\seo-knowledge-graph\\mcp\\server.py"],
      "env": {"SEO_KG_ROOT": "C:\\Users\\Lenovo\\Documents\\Plan\\seo-knowledge-graph", "PYTHONUTF8": "1"}
    }
  }
}
```

* Absolute paths are required. No secrets are placed in this file (the server reads `.env` itself only for non-secret paths; MCP tools never return credentials).
* **Restart Claude Desktop completely** (quit from the tray icon) after changes.
* Verify: in a chat, click the "+ / connectors" control → *Manage connectors* → `seo-knowledge-graph` → tools listed. Ask: *"Call get_site_summary."*
* Logs: `%APPDATA%\Claude\logs\mcp.log` and `mcp-server-seo-knowledge-graph.log` (server stderr). Project log: `data/logs/mcp.jsonl`.
* Manual test without Claude: `.venv\Scripts\python -m pytest -q tests/integration` (drives the server with the official MCP client over stdio).

## Tools (all read-only; `read_only_hint=True`)

| Tool | Purpose |
|---|---|
| `get_site_summary` | counts, GSC status, last runs (start here) |
| `get_site_structure` | pages, category tree with posts, CPTs, entities |
| `get_categories`, `get_models`, `get_brands`, `get_services`, `get_locations` | taxonomy / entity lists with evidence |
| `search_graph` | FTS5 search over nodes |
| `get_node`, `get_neighbors`, `get_subgraph`, `find_path` | graph traversal (N-hop, paths, filtered subgraphs) |
| `find_orphans` | zero-inbound indexable pages (+ nav-only) |
| `find_cannibalization` | cannibalization **candidates** (needs GSC) |
| `find_internal_link_opportunities` | source → target, anchor, reason, confidence, breakdown |
| `get_gsc_page_data`, `get_gsc_query_data` | cached GSC (position ranges, impressions, CTR) |
| `get_page_seo_data` | everything about one page |
| `get_seo_problems`, `get_seo_opportunities` | analysis results with explainable scores |
| `list_sites` | configured sites |

Node references accept node ids, URLs (decoded or percent-encoded), or titles/labels.

## Security

stdio only · no `read_any_file` · no SQL passthrough · no delete/update/publish/edit/move/rename · outputs tested for secret leakage (`tests/integration/test_mcp_stdio.py`).

> **Note (2026-08-17):** paths in this document were rewritten after the SEO Brain Phase 1 restructure (`backend/seo_brain/`→`backend/seo_brain/`, `backend/cli/`→`backend/cli/`, `mcp/`→`backend/mcp_server/`). Historical commit references are unchanged.
