# Atria SEO remediation pilot

The pilot is limited to `gearboxemdad`. The Problems page and graph detail panel expose **رفع مشکل** for each of the 14 problem types emitted by `analysis.seo`. A versioned playbook in `backend/seo_brain/remediation/playbooks.py` supplies the diagnostic and verification steps. Atria may suggest values only for allowlisted methods; it never receives WordPress credentials or arbitrary command execution.

## Setup

1. In **مدل‌های AI**, add a provider of kind `atria`, set the API key, leave the default base URL `https://api.atria-asi.ai/v1` and model `Atria-Dawn-Preview`, then test the connection. The probe sends a tiny Chat Completions request. The key stays in SecretStore.
2. Apply its recommended `seo_remediation` task route for `gearboxemdad` (or set that route explicitly). The remediation service refuses another provider or an implicit fallback.
3. Configure a dedicated WordPress service user and its Application Password in the site's connection settings. Grant that user edit access to the *specific* posts/pages and custom post types that SEO Brain may repair. The pilot requires the `emdad-headless` REST metadata fields for title, description, canonical and noindex writes. A generic `edit_posts` check is insufficient for a custom post type or a particular post.
4. Run migration `0020_seo_remediation.sql` through the existing migration runner. This branch is based on the current `origin/main`; reconcile it with the deployed backend and frontend images before release.

## API and execution

- `GET /api/v1/sites/{site_id}/remediation/problems` lists stable issue keys with pagination.
- `POST /api/v1/sites/{site_id}/remediation/problems/{issue_key}/proposals` gathers cached and rendered evidence, asks Atria for bounded suggestions, and persists a proposal for 30 minutes.
- `POST /api/v1/sites/{site_id}/remediation/runs` takes `proposal_id`, `method_id`, `evidence_hash`, an idempotency key, and `uncertain_confirmed`. Selecting a confident method queues it immediately; uncertain methods require a second confirmation.
- `GET /api/v1/sites/{site_id}/remediation/runs/{run_id}` shows status. `POST .../resume` continues a WordPress run after its connection is configured, while the proposal and evidence remain fresh. `POST .../verify` repeats read-only verification. `POST .../rollback` restores the saved WordPress fields if no later edit has changed the resource.

The executor checks the current issue, page hash, WordPress resource identity and modification time. It snapshots the original fields, performs one allowlisted REST write, inspects the public HTML, crawls affected pages, and reruns the analysis. A run is verified only when the selected problem disappears from the updated detector output. A stale, ambiguous or unavailable operation stops with an explicit status; the Atria proposal remains available for inspection.
Snapshots, verification results and successful rollback reports are also recorded as separate private audit events linked to the run.

## Site access and permission checks

SEO Brain uses a separate credential for each boundary. The Atria key only generates suggestions. The WordPress Application Password authenticates REST edits. A future Next.js release connector needs its own repository and deployment credentials; WordPress access cannot replace that connector. Do not grant the model any of these credentials.

For each WordPress method, proposal generation performs an authenticated, read-only `GET /wp-json/wp/v2/types/{type}` followed by `GET /wp-json/wp/v2/{rest_base}/{id}?context=edit`. This checks access to the actual post, including custom post types, and verifies that the requested `title.raw`, `content.raw`, or `emdad_*` meta field is exposed. The method card reports this result. SEO Brain probes again when the user queues or resumes a run, and checks the field once more immediately before the write. A 401, 403, missing REST type or missing meta field becomes **نیازمند اتصال**, retaining the proposal and an actionable error. The read-only check cannot guarantee a later `POST` will be allowed; a rejected write is also reported as **نیازمند اتصال**.

The site administrator should configure the service user's WordPress role or custom capabilities for each supported content type and field. In particular, the site's REST meta registration and `auth_callback` must expose `emdad_meta_title`, `emdad_meta_description`, `emdad_canonical`, and `emdad_noindex` where those methods are offered. The existing site connection page checks the generic WordPress login; the remediation card gives the more precise per-resource result. Avoid using a full Administrator account unless the site's own capability model makes it necessary. After changing permissions, select **بررسی اتصال و ادامه** while the proposal is still fresh, or generate a new proposal.

## Current connector boundary

The pilot can edit matching WordPress posts, pages and public custom post types through their discovered REST base: metadata, title, bounded body heading/link/content/alt operations. It does not execute raw PHP, shell commands, arbitrary model code or writes to nonmatching URLs. Methods owned by the Next.js template, global navigation or sitemap are stored with `needs_connection`. Their release connector must be added and validated against the actual `gearboxemdad` repository before those methods can run. The UI reports this boundary on each method card.

Ownership rules were checked against the deployed `gearboxemdad` release `r20260830-symptomlinks`: car brand/model H1 and canonical are generated by Next.js, and car model indexability uses `emdad_model_indexable`. The pilot blocks WordPress title/canonical/noindex methods where those fields cannot own the rendered output. A source-controlled release connector is still needed for those cases.
