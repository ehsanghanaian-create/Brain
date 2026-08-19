# SEO Brain — Phase 2 (dashboard foundation) report

Date: 2026-08-17 · Scope: prerequisites (Node + disk) → starter → RTL/Persian/dark shell → menu → API integration → real overview/sites pages → verification.
Preceded by Phase 1.5 (`03-phase1.5-api-validation.md`, 47/47) and the contract (`04-frontend-contract.md`).

## 1. Prerequisites — how they were resolved

| Requirement | Finding | Resolution |
|---|---|---|
| Disk | `C:` 0.58 GB free — cannot host `node_modules`; `D:` 140 GB free | **Everything Node-related lives on D:** — `D:\nodejs` (runtime), `D:\seo-brain\pnpm-store`, `D:\seo-brain\frontend` (the whole frontend project). The repo exposes it as `frontend/` through a **directory junction**, so git, paths and docs are unchanged. |
| Node.js | not installed | Installed **Node v24.19.0 LTS (Krypton) + npm 11.17** from the official zip (`SHA-256 57f71ab3…` verified against `SHASUMS256.txt`), no admin; user PATH updated. pnpm 11.22 via corepack (`PNPM_HOME=D:\seo-brain\pnpm`). |
| pnpm store on C: | first install ignored `store-dir` (pnpm keeps the store on the *project's* drive) and filled C: to 0 MB | store deleted from C:; project moved to D:; `frontend/.npmrc` pins `store-dir` on D: (verified: `pnpm store path` → `D:\seo-brain\pnpm\store\v11`, no `C:\Users\…\.pnpm-store`). My Obsidian installer copy (331 MB) was also removed from Temp. |

C: after cleanup ≈ 450 MB free — still low, but the frontend no longer touches it (Next build cache is on D: too).

## 2. What was built

* Starter cloned (`Kiranism/next-shadcn-dashboard-starter`, Next 16.2 / React 19 / Tailwind 4 / shadcn), then stripped: Clerk auth, chat + AI-chat demos, Sentry, notifications, examples, extra themes, product/user demo pages, mock APIs, starter docs. Kanban feature kept for Phase 6.
* **Shell**: `lang="fa" dir="rtl"`, dark theme default, Vazirmatn (next/font) wired through the theme's `--font-sans`, logical CSS (`ms/me/ps`) in header/sidebar, Persian aria labels, ⌘K search + breadcrumbs driven by the same nav config.
* **Menu** (`src/config/nav-config.ts`): داشبورد · سایت‌ها · گراف دانش · کلمات کلیدی · مغز محتوا · تقویم محتوایی · مدل‌های AI · لینک‌سازی داخلی · فرصت‌های سئو · گزارش‌ها · تنظیمات — grouped, with descriptions for the help system.
* **API integration** per contract: `app/api/backend/[...path]/route.ts` proxy (adds `X-API-Token` server-side, passes `X-Request-ID`, returns backend errors verbatim, 503 envelope when the backend is down); `lib/api/client.ts` typed wrapper (`ApiError`, `settle()`); `lib/api/schema.d.ts` **generated** from `docs/seo-brain/openapi.v1.json` (`pnpm api:types`).
* **Pages**: `/dashboard/overview` (KPIs from live backend: sites, nodes, edges, backend version/migrations; per-site mode; node-type composition), `/dashboard/sites` (table: name, domain, lang/country, GSC property, mode, workspace), `/dashboard/settings` (backend URL/token status/health + how-to), 8 roadmap pages (graph, keywords, content, calendar, ai-models, internal-linking, opportunities, reports) stating phase + planned features. Info sidebar = future help panel (Persian default text).
* Dev tooling: `.claude/launch.json` (backend on 8000, frontend on 3000 via `frontend/scripts/dev-server.cjs`), `pnpm typecheck` clean.

## 3. Verification (live, both servers running)

| Check | Result |
|---|---|
| `tsc --noEmit` | 0 errors |
| `GET /dashboard/{overview,sites,graph,settings,keywords}` | 200 |
| Proxy `GET /api/backend/health` | 200 `{"status":"ok","version":"0.2.0",…}` |
| Proxy `GET /api/backend/sites/example-site/graph/summary` | 200 · 91 nodes / 356 edges |
| Proxy error passthrough `GET /api/backend/sites/nope` | 404 with the contract envelope + `request_id` |
| DOM (browser pane) | `dir=rtl`, `lang=fa`, `.dark`, 11 Persian menu items, sites row `نمونه سایت … sc-domain:example.com … دستی`, KPIs `۱ / ۹۱ / ۳۵۶ / v0.2.0 · sqlite`, `document.fonts` → Vazirmatn loaded |
| Console | no errors from the current build (two stale 500s from the very first mis-configured start remained in the console buffer) |

## 4. Deviations / notes

* Frontend on D: via junction is a workstation-specific arrangement (documented in `frontend/README.md`); on a server (Phase 19) it is just a normal directory.
* `frontend/.npmrc` contains an absolute D: store path — harmless elsewhere (pnpm falls back), but should become relative/removed when the repo moves.
* Two 500s appear in the browser console history from the first start (Next resolved the project dir relative to cwd → fixed by `scripts/dev-server.cjs`); no errors after the fix.
* Not done yet (next phases): Add-Site wizard (3), React Flow graph (4), TanStack Query hooks + SSE (used from Phase 3/8), help content (18).

## 5. Next: Phase 3 — Sites management (wizard, per-site workspace, GSC/GA4 connection tests)
