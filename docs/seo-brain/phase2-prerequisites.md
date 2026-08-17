# Report: prerequisites before Phase 2 (UI dashboard)

Date: 2026-08-17 · Requested at Phase 1 approval: "Before Phase 2, report Node.js requirement and disk cleanup requirement."

## 1. Node.js requirement — **NOT MET**

| Item | Status | Needed for |
|---|---|---|
| Node.js | not installed (`node`, `npm`, `pnpm` absent from PATH) | Next.js 15 (starter `Kiranism/next-shadcn-dashboard-starter`), shadcn/ui CLI, Tailwind build, React Flow, OpenAPI → TypeScript client generation |
| Version | Node **20 LTS or 22 LTS** (Next.js 15 requires ≥ 18.18; starter is tested on 20/22) | |
| Package manager | pnpm (starter default) — installed via `corepack enable` (bundled with Node) | |
| Footprint | Node installer ≈ 30 MB, installed ≈ 120 MB; `frontend/node_modules` for the starter ≈ **600–900 MB**; `.next` build cache ≈ 200–500 MB | |

**What I need from you:** permission to download the official Node LTS Windows installer (`nodejs.org/dist/…/node-vXX-x64.msi`), verify its SHA-256 against `SHASUMS256.txt` from the same release (same procedure as the Obsidian install), and install it for the current user (no admin required with the MSI per-user option; otherwise the UAC prompt is yours). Alternative: `winget install OpenJS.NodeJS.LTS` — but winget stalled on this network for the Obsidian download.

## 2. Disk cleanup requirement — **NOT MET (blocking)**

| Measurement (2026-08-17 15:30) | Value |
|---|---|
| Free space on `C:` | **≈ 615 MB** (observed range over the last two days: 82 MB … 2.6 GB — the drive is at capacity and other processes churn it) |
| Project footprint | `.venv` 266 MB · code + docs + vault < 20 MB · `data/` (SQLite, raw JSON, logs) ≈ 15 MB |
| Obsidian app | 374 MB (installed) |
| Temp left by this work | `Obsidian-1.13.7.exe` installer, 331 MB, in the session scratchpad — **can be deleted now** (verified & installed) |
| `%LOCALAPPDATA%\Temp` total | ≈ 420 MB (includes the installer above) |

**Minimum to start Phase 2:** ≥ **3 GB free** (Node + node_modules + Next build cache + headroom for pnpm store).
**Comfortable for the whole roadmap** (Phase 17 PDF engine, Docker images in Phase 19): ≥ **10 GB**, or move the repository to another drive.

Options (your decision):
1. Free space on `C:` (Storage Sense / Disk Cleanup, large downloads, old Windows update cache) until ≥ 3 GB free — I can delete only what I created (the 331 MB installer copy) without asking; I will not touch your files.
2. Move the repository to another drive (e.g. `D:\Plan\seo-knowledge-graph`): a `git clone`/copy, re-create `.venv`, re-run `backend/cli/setup.py --claude-config` (MCP path) and re-register the Obsidian vault path. ~15 minutes, fully reversible.
3. Put only `frontend/` (and the pnpm store) on another drive via `PNPM_HOME`/`store-dir` — works, but splits the repo across drives.

## 3. Everything else for Phase 2 is ready

* Backend API is running-capable on `127.0.0.1:8000` with OpenAPI at `/api/openapi.json` (the TS client will be generated from it).
* CORS already allows `http://localhost:3000`.
* Menu → router mapping is defined in `01-architecture.md §5`; graph endpoints already return the React-Flow-friendly node/edge shape.

**Phase 2 starts as soon as (a) Node install is approved and (b) ≥ 3 GB is free or the repo is relocated.**
