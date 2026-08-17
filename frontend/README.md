# SEO Brain — frontend (Next.js)

Persian-first, RTL, dark-by-default dashboard for the SEO Brain backend (`../backend`, FastAPI `/api/v1`).
Base: [Kiranism/next-shadcn-dashboard-starter](https://github.com/Kiranism/next-shadcn-dashboard-starter) (Next 16, React 19, Tailwind 4, shadcn/ui, TanStack Query, Zustand, dnd-kit) with Clerk/Sentry/demo features stripped.

## Run (local)

```powershell
# backend first
..\.venv\Scripts\python ..\backend\cli\api.py            # http://127.0.0.1:8000
# frontend
copy env.example.txt .env.local                          # SEO_BRAIN_API_URL / SEO_BRAIN_API_TOKEN (server-side only)
pnpm install
pnpm dev                                                 # http://127.0.0.1:3000 → /dashboard/overview
```
On this workstation the whole `frontend/` directory physically lives on `D:\seo-brain\frontend` (C: is full) and is
exposed in the repo through a directory junction; Node 24 LTS is at `D:\nodejs`, pnpm store at `D:\seo-brain\pnpm-store`
(`.npmrc`). `scripts/dev-server.cjs` starts Next with the correct cwd (used by `.claude/launch.json`).

## Contract with the backend

* `docs/seo-brain/04-frontend-contract.md` — binding. Types are **generated**: `pnpm api:types` regenerates
  `src/lib/api/schema.d.ts` from `docs/seo-brain/openapi.v1.json`. Never hand-write API types.
* Browser → `/api/backend/*` (route handler proxy adds `X-API-Token` server-side) → backend `/api/v1/*`.
  Server components call the backend directly (`src/lib/api/client.ts`). Errors are always `ApiError`.

## Structure

```
src/app/dashboard/<area>/page.tsx   one route per menu item (overview, sites, graph, keywords, content, calendar,
                                    ai-models, internal-linking, opportunities, reports, settings)
src/config/nav-config.ts            Persian menu (sidebar + ⌘K + breadcrumbs share it)
src/components/seo-brain/           KpiCard, BackendError, RoadmapPage (placeholder for phases not yet built)
src/lib/api/                        client.ts (fetch wrapper), schema.d.ts (generated)
src/app/api/backend/[...path]/      proxy route
```
