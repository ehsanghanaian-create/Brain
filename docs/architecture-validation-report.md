# Architecture Validation Report — Phase 0/1

Project: Local SEO Knowledge Graph for `emdadmodiran.com`
Date: 2026-08-16
Scope: environment audit, dependency audit, target-site audit, API connectivity, architecture decisions.
Nothing on the target website was modified. All requests were `GET` only.

---

## 1. Local environment (Phase 1)

| Component | Status | Detail | Fix / Note |
|---|---|---|---|
| OS | PASS | Windows 11 Enterprise 10.0.26100, AMD64 | — |
| Shell | PASS | Windows PowerShell 5.1 (+ Git Bash) | Scripts will be `.ps1` + `.sh` |
| Git | PASS | 2.55.0.windows.4 (`C:\Program Files\Git`) | — |
| Python | PASS | 3.13.0 (default `python`), 3.14.0a2 also present via `py` | Use **3.13.0** (3.14 is alpha). Project venv `.venv/` |
| pip | PASS | 24.3.1; PyPI reachable | — |
| SQLite (Python) | PASS | 3.45.3, **FTS5 enabled**, JSON1 enabled | Sufficient for full-text search |
| Node.js / npm | **NOT INSTALLED** | not on PATH, not in registry | winget offers `OpenJS.NodeJS.LTS 24.19.0`. **Not required by the chosen architecture** (see §5). Not installing unless a Node component is chosen. |
| Obsidian | **NOT INSTALLED** | no install, no `%APPDATA%\obsidian`, no `.obsidian` vault anywhere in Documents/Desktop/Claude/OneDrive | winget offers `Obsidian.Obsidian 1.13.7` (≥ 1.13.1 required by Local REST API plugin). Will install in Phase 3 (safe, official winget package). |
| Claude Desktop | PASS | v1.30096.5 at `%LOCALAPPDATA%\AnthropicClaude`; config `%APPDATA%\Claude\claude_desktop_config.json` **exists** (preferences only, no `mcpServers` key yet) | Config will be backed up before editing (Phase 10) |
| winget | PASS | 1.29.280 | Used for Obsidian install |
| GitHub | PASS | github.com + api.github.com reachable | — |
| npm registry | PASS | reachable (informational) | — |
| Google APIs | PASS (network) | `googleapis.com` discovery for `searchconsole v1` reachable | Credentials missing → see §4.3 |
| Working directory | PASS | `C:\Users\Lenovo\Documents\Plan` (empty, not a git repo) | Project root will be `Plan\seo-knowledge-graph\` |

Python packages present: only `requests`. All others will be installed into a project venv.

---

## 2. Dependency audit — GitHub repositories

### 2.1 `obra/knowledge-graph` — **REJECTED as a dependency**

Facts (source: GitHub API, README, `package.json`, `src/**` on `main`, fetched 2026-08-16):

- TypeScript/Node ESM, run via `npx tsx`; not published to npm; no releases, no tags; version 0.1.0.
- Created 2026-03-21, **last commit 2026-03-22**; 14+ open issues/PRs, bug-fix PRs unmerged → dormant.
- MCP server (stdio) exists but **`tools/list` crashes** out of the box (zod v4 vs SDK 1.27.1; issues #2/#7, PR #4 unmerged).
- Ships **write tools** (`kg_create_node`, `kg_annotate_node`, `kg_add_link`) with an unpatched path-traversal bug (#5). Violates our read-only requirement unless forked and stripped.
- License: README says MIT, **no LICENSE file** (`license: null` in API; PR #15 unmerged).
- Native deps: `better-sqlite3`, `sqlite-vec`; first-run download of a Hugging Face model; Windows untested (XDG default data dir).
- Node-only API; no Python interface. Input model is markdown files + `[[wikilinks]]` only.

Conclusion: the graph algorithms it offers (BFS neighbors, all-simple-paths, Louvain communities, betweenness, PageRank, FTS5 search) are all thin wrappers over `graphology` and SQLite. Re-implementing them in Python with `networkx` + SQLite FTS5 is lower risk than vendoring an unmaintained, currently-broken Node project with licensing ambiguity and write tools.

**Decision:** implement the graph layer in Python (`networkx` ≥ 3.x for PageRank / Louvain / shortest & simple paths / N-hop; SQLite FTS5 for full-text search). Semantic search is **deferred** (architecture hook only; can add `sentence-transformers` locally later). This keeps the whole stack in one runtime and removes the Node.js requirement.

### 2.2 `coddingtonbear/obsidian-local-rest-api` — **ACCEPTED as OPTIONAL**

Facts (source: GitHub API, `manifest.json`, `docs/openapi.yaml`, README on `main`, fetched 2026-08-16):

- Obsidian community plugin id `obsidian-local-rest-api`, latest **5.1.0 (2026-08-01)**, actively maintained (multiple releases Jun–Aug 2026), MIT, desktop-only.
- `minAppVersion` **1.13.1** → compatible with Obsidian 1.13.7 from winget.
- Default bind host **127.0.0.1**, HTTPS 27124 (self-signed cert), optional HTTP 27123 (off by default). Bearer API key auth.
- Endpoints: `/vault/*` GET/PUT/POST/PATCH/DELETE, `/search/simple/`, `/search/` (JsonLogic), `/tags/`, `/commands/`, `/open/`, built-in MCP at `/mcp/`. Frontmatter read (`application/vnd.olrapi.note+json`) and JSON-body PATCH supported. Dataview DQL search endpoint is gone (JsonLogic only).
- Claude Desktop cannot connect to its HTTP MCP directly (needs `npx mcp-remote`, i.e. Node).

Conclusion: the vault is a plain folder; the Python generator will **write markdown directly** (no runtime dependency on Obsidian being open). The REST API is useful only for live-Obsidian features (open a note, fuzzy search, tags). It is therefore **optional**: `OBSIDIAN_API_URL/KEY` stay in `.env.example`, a thin read-only client is provided, and every feature works without it.

---

## 3. Target website audit — `https://emdadmodiran.com/`

| Item | Finding |
|---|---|
| HTTP | 200, server `LiteSpeed`, `text/html; charset=UTF-8`, no `X-Robots-Tag` |
| Language | `<html lang="fa-IR">`, `og:locale fa_IR`; Persian slugs (percent-encoded in REST `link`/sitemap; must be decoded/normalized consistently) |
| CMS | WordPress; Elementor 4.2.2 (Pro), Yoast SEO v28.2, theme Hello Elementor |
| Site name | امداد مدیران — "عاملیت امداد خودرو مدیران خودرو تهران" |
| Timezone (WP) | `Atlantic/Azores`, gmt_offset 0 (⚠ posts' `date` vs `date_gmt` differ; store both) |
| robots.txt | Yoast block: `Disallow: /wp-admin/, /?s=, /*/feed/, /page/*/?s=, /search/, /wp-json/, /?rest_route=`; `Allow: /wp-admin/admin-ajax.php`; `Sitemap: https://emdadmodiran.com/sitemap_index.xml` |
| Sitemap | Yoast index → `post-sitemap.xml` (11), `page-sitemap.xml` (3), `category-sitemap.xml` (4) = **18 URLs** |
| Homepage | title present, canonical `https://emdadmodiran.com/`, no robots meta (indexable), **0 × H1** (Elementor layout), 1 Yoast `ld+json` graph (WebPage/ImageObject/BreadcrumbList/WebSite/Organization), 37 internal `<a>` hrefs, no hreflang |
| Category archives | 200, canonical self, no robots meta → indexable |

**robots.txt compliance note:** `/wp-json/` is disallowed for crawlers. The **crawler will never fetch `/wp-json/`** (robots-respecting). The WordPress connector is an API client using the documented REST API (public read endpoints), which is the intended programmatic access path; this is separate from HTML crawling and will be rate-limited and read-only. This distinction will be documented in `docs/wordpress.md`.

### 3.1 WordPress REST API (`/wp-json/`)

- Root discovery: PASS. Namespaces: `wp/v2`, `yoast/v1`, `elementor/*`, `oembed/1.0`, `wp-site-health/v1`, `wp-block-editor/v1`, `wp-abilities/v1`.
- Authentication advertised: **Application Passwords** (`/wp-admin/authorize-application.php`) → matches requirement §12.
- Public (unauthenticated) read access works: `posts`, `pages`, `categories`, `tags`, `media`, `types`, `taxonomies`, `search`.
- Requires auth (401/403): `users`, `elementor_library`, `menu-items`, `menus`. Menus would help the link graph but the crawler captures nav links from HTML anyway → **not blocking**.
- `yoast_head_json` is exposed per post/page: title, description, canonical, robots directives, OG, and the full `schema` graph → the connector can capture SEO metadata without HTML parsing (crawler still validates the rendered HTML).

Content inventory (real, 2026-08-16):

| Type | Count | Notes |
|---|---|---|
| Pages | 3 | `/` (450), `/mvm/` (514 "امداد خودرو ام وی ام"), `/mvm2/` (515 "امداد خودرو چری") — all `parent=0` |
| Posts | 11 | permalinks `/%category%/%postname%/`; ~780 words for sampled post |
| Categories | 5 | `modiran-emdad`(6) → `emdad-mvm`(7), `cherry-emdad`(8); `blog`(3); `دسته‌بندی نشده`(1, empty) |
| Tags | 0 | tag taxonomy exists but unused |
| Media | 62 | attachments |
| Custom Post Types (public content) | **none** | Only core + Elementor internal types (`elementor_library`, `e-floating-buttons`, `elementor_snippet`) — not content pages |
| Custom taxonomies | **none** | `nav_menu`, `wp_pattern_category` only |

Entities visible in real content/taxonomy (to be **extracted, not hard-coded**): brands مدیران خودرو / MVM (ام وی ام) / چری (Chery); models تیگو 5, تیگو 7, فونیکس, X33 (image); location تهران; service امداد خودرو (roadside assistance).

Implication: the site is small (~18 canonical URLs + home). The mandated 20-URL first crawl will cover essentially the entire site; the "full crawl" then adds anything discovered via links (pagination, media pages, feeds are excluded by robots).

### 3.2 Google Search Console

- API endpoint reachable. Python client libs available on PyPI (`google-api-python-client`, `google-auth-oauthlib`).
- **BLOCKED on credentials:** no OAuth client (`client_secret*.json`) exists locally and none was provided. Required from the user before Phase 8:
  1. Google Cloud project → enable **Google Search Console API**.
  2. OAuth consent screen (External/Testing is fine; add the Google account that owns the GSC property as a test user).
  3. OAuth Client ID of type **Desktop app** → put `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` in `.env` (or place the JSON in `credentials/`).
  4. Confirm the exact property string (`GSC_PROPERTY`): `https://emdadmodiran.com/` (URL-prefix) or `sc-domain:emdadmodiran.com` (Domain property). The list-sites step will show what the account actually has.
  5. The first `sync-gsc` run opens a browser once for consent; the refresh token is stored locally under `tokens/` (git-ignored).
- Everything else in Phase 8 (connector, 1-day test, 30-day configurable lookback, quota strategy) will be implemented and unit-tested; the live test is BLOCKED until credentials arrive.

### 3.3 Obsidian Local REST API

- Cannot be tested until Obsidian is installed and the plugin enabled (Phase 3). Marked OPTIONAL (see §2.2).

---

## 4. Blockers & required user inputs

| # | Item | Blocking? | Needed by |
|---|---|---|---|
| B1 | Google OAuth Desktop client (ID + secret) + GSC property confirmation | **Yes, for live GSC only** | Phase 8 live test |
| B2 | WordPress Application Password (username + app password) | No — public endpoints suffice for MVP; auth adds menus/authors | Optional |
| B3 | Obsidian installation via winget (`Obsidian.Obsidian`) | Will be performed in Phase 3 (safe, official). Say so if you'd rather install manually. | Phase 3 |
| B4 | Node.js | **Not required** by the chosen architecture. Will not be installed. | — |

---

## 5. Validated architecture (decisions)

```
CLAUDE DESKTOP ──stdio MCP──▶ mcp/server.py (Python, FastMCP, read-only tools)
                                   │
                    ┌──────────────┼──────────────┐
                    ▼              ▼              ▼
              src/graph/     src/analysis/    src/database/
              (networkx +    (SEO rules,      (SQLite data/seo.db,
               FTS5 search)   scoring)         FTS5, indexes)
                    ▲              ▲              ▲
                    └──────────────┼──────────────┘
                                   │
                          data ingestion (Python)
             ┌───────────────┬─────┴──────────┬────────────────┐
             ▼               ▼                ▼                ▼
   src/wordpress/     src/crawler/       src/gsc/        (future: GA4, Ads,
   REST client        robots-aware       OAuth + cached   backlinks, PageSpeed
   (read-only)        HTML crawler       Search Analytics  — interfaces only)
             └───────────────┴─────┬──────────┴──┘
                                   ▼
                          src/normalizer/ (URL identity)
                                   ▼
                              SQLite (source of truth)
                                   ▼
                     src/graph/obsidian_writer.py  ──▶  obsidian/SEO-Knowledge-Graph/ (markdown + wikilinks)
                                                          ▲ Obsidian Graph View (human)
                                                          │ optional: Local REST API (read)
```

| Concern | Decision | Rationale |
|---|---|---|
| Runtime | **Python 3.13 only**, project venv | One runtime; MCP SDK, Google libs, networkx, FTS5 all Python; avoids Node native modules |
| Graph engine | `networkx` + SQLite (nodes/edges tables + FTS5) | obra/knowledge-graph rejected (§2.1); networkx provides PageRank, Louvain, paths, N-hop |
| Semantic search | Deferred (interface hook) | Not required for acceptance tests; avoids model downloads in MVP |
| MCP transport | stdio, launched by Claude Desktop with absolute venv python path | Official Claude Desktop pattern; no network port; inherently localhost |
| Obsidian | Direct file writes; REST API optional | Vault is a folder; no dependency on Obsidian being open |
| Dashboard | Python (FastAPI/uvicorn or stdlib) bound to `127.0.0.1:3000` | No Node needed; functionality over UI |
| `package.json` | **Omitted** (deviation from §43) | No Node component; will be added only if one is introduced |
| Storage | `data/seo.db` (SQLite, WAL), `data/raw/{wordpress,crawler,gsc}/` JSON | As specified |
| Multi-site | `site_id` on every table/node; `config/site.yaml` per site | As specified |
| Read-only guarantee | WP client has **only GET** methods; MCP exposes only `get_*/find_*/search_*` tools; no `write/delete/update` code paths to WordPress anywhere | §55 |
| Secrets | `.env` (git-ignored), masked in logs, never returned by MCP tools | §63 |

Claude Desktop MCP config format (verified from modelcontextprotocol.io/quickstart/user, 2026-08-16): file `%APPDATA%\Claude\claude_desktop_config.json`, key `mcpServers.<name>.{command,args,env}`, absolute paths, full app restart required, logs in `%APPDATA%\Claude\logs\mcp*.log`. Existing config will be backed up and merged, not overwritten.

---

## 6. Phase gate

| Check | Result |
|---|---|
| Environment inspected | DONE |
| Repos inspected against current source | DONE (both) |
| Target site / REST / robots / sitemap inspected | DONE |
| GSC connectivity requirements determined | DONE (credentials BLOCKED — B1) |
| Architecture validated | DONE (with 2 changes: graph engine → Python/networkx; Node not required) |
| Any target-site modification | NONE |

**PHASE 0/1 STATUS: PASS (with blockers B1 noted). Proceeding to Phase 2 (scaffold).**
