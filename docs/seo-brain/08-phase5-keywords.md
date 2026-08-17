# SEO Brain — Phase 5: Keyword Intelligence

Date: 2026-08-17 · Existing contracts unchanged (new `/keywords/*` router, migration 0004) · Backend **63/63** · Live validation **79/79** · `tsc` clean · verified in the browser on the real site (import → GSC join → clusters → opportunities → graph).

## 1. Data model — migration `0004_keywords.sql`
| Table | Purpose |
|---|---|
| `keywords` | one row per normalized keyword per site: keyword, normalized, intent, cluster_id, topic, volume, difficulty, priority, target_url, status (`new/planned/in_progress/published/ignored`), source, notes |
| `keyword_clusters` | clusters/topics: name (representative keyword), topic (editable), keywords_count, method (`token_jaccard`, `manual`, `…+manual_topic`) |
| `keyword_imports` | audit trail of imports: file, format, counts, mapping, errors |
| `keyword_opportunities` | rule-based opportunities: kind (`improve_page / create_content / update_title / add_internal_links`), target_url, score, reason (fa), evidence JSON, status (`new/accepted/dismissed/done`), run_id — unique per (keyword, kind) |

## 2. Services — `seo_brain/brain/keywords/`
* **normalize.py** — Persian-aware normalization (Arabic ي/ك → Persian, digits, ZWNJ, diacritics, punctuation, case) + tokenizer with fa/en stop-words. Used everywhere (import de-dup, GSC join, clustering).
* **importer.py** — CSV / TSV / XLSX (Excel) / Google-Sheet export; delimiter sniffing; header auto-mapping via English **and Persian** aliases (`کلمه کلیدی`, `اینتنت`, `حجم`, `اولویت`, `صفحه هدف`, `وضعیت`…) with explicit override; enum aliases (تراکنشی→transactional, بالا→high, برنامه→planned…); Persian digits/thousand separators; in-file duplicate detection; `dry_run` preview; upsert by normalized keyword; import audit row; CSV template.
* **clustering.py** — deterministic, offline: **IDF-weighted Jaccard** on tokens (0.7) + rapidfuzz token-set ratio (0.3), greedy agglomeration by volume; ubiquitous tokens (e.g. «امداد خودرو» on a towing site) get ~0 weight so clusters form around discriminating tokens (model / city / service). Manual clusters (`m-*`) and **user-set topics** survive re-clustering.
* **service.py** — `enrich()` joins GSC (`gsc_query_page` aggregated per normalized query → clicks, impressions, CTR, impression-weighted position, top page); `topic_map()`; `analyze()` (rules below); `sync_graph()` upserts **KEYWORD** + **TOPIC** nodes and **CLUSTERED_IN** / **KEYWORD_TARGETS** edges (target = explicit target_url or GSC top page), removes stale ones.

### Opportunity rules (explainable, every row has `reason` + `evidence`)
| kind | condition | score drivers |
|---|---|---|
| `create_content` | no GSC data or best position > 20, and no target page | priority, volume |
| `improve_page` | position 4–20 with ≥ N impressions and a target/top page | impressions, closeness to page 1 |
| `update_title` | position ≤ 12, ≥ 20 impressions, CTR < 50 % of the expected CTR for that position | CTR gap, impressions |
| `add_internal_links` | position 4–25 and the target page has ≤ 3 internal inbound links (from `links`) | inbound deficit, impressions |

## 3. API (additive) — `/api/v1/sites/{id}/keywords`
`GET` list (paginated envelope + `counts`, filters `q,status,intent,priority,cluster_id,topic`, `sort/order`) · `POST` create (409 on duplicate) · `GET/PATCH/DELETE /{kid}` (detail carries GSC per-page rows + opportunities) · `GET /meta` · `GET /template.csv` · `POST /import` (multipart `file`, `dry_run`, optional `mapping` JSON) · `GET /imports` · `GET /clusters` · `POST /cluster?threshold&sync_graph` · `PATCH /clusters/{cid}` (name/topic) · `GET /topic-map` · `POST /analyze?min_impressions&sync_graph` · `GET /opportunities` (filters kind/status/keyword_id/min_score) · `PATCH /opportunities/{oid}` (status) · `POST /sync-graph`.
`DELETE /sites/{id}` now also clears the keyword tables. Contract §10 added; `openapi.v1.json` = 39 paths.

## 4. UI — `/dashboard/keywords` (Persian, RTL)
* Header actions: افزودن · **ورود فایل (CSV / Excel / Sheet)** — dialog with file picker, detected mapping (editable per column), badges (rows/valid/skipped/errors), preview, commit · **خوشه‌بندی** · **تحلیل فرصت‌ها** · همگام‌سازی گراف · link to the graph.
* KPIs: total, with GSC data, clusters, with target, new opportunities by kind.
* Tab **کلمات کلیدی**: filters (search, status, intent, priority, cluster chip), sortable columns, pagination; columns keyword · intent · cluster/topic · volume · difficulty · priority · target (falls back to GSC top page, muted) · status · **جایگاه · CTR · ایمپرشن · کلیک**; row → editor sheet (all fields, GSC per-page rows, opportunities, delete).
* Tab **خوشه‌ها و نقشه موضوعی**: cluster cards (editable topic, method, volume/impressions/clicks/avg position, member chips with position, targets), unclustered bucket.
* Tab **فرصت‌ها**: filters kind/status; kind badge, keyword, target, score, reason, evidence; accept / dismiss / done.
* Graph page: KEYWORD/TOPIC nodes appear in the SEO map (type family «کلمه کلیدی»), TOPIC also in the content map; keyword node details show GSC + related pages.

## 5. Verification
| Check | Result |
|---|---|
| Backend pytest | 63 passed (+6 phase-5: normalize/tokenize; CSV Persian headers dry-run→write→re-import updates; XLSX + mapping override + missing keyword column + empty file; CRUD/filters/409/422; IDF clustering groups by discriminating tokens & keeps manual cluster; end-to-end GSC join → 4 opportunity kinds asserted → status kept across re-analyze → topic-map → manual topic survives recluster → KEYWORD/TOPIC in graph view → delete cascades) |
| Live validation | 79/79 (+15 keyword checks) |
| Browser (real site) | table with live GSC (e.g. «امداد مدیران خودرو» #8.8 · 0.8٪ · ۱٬۵۲۳ · ۱۲); topic map cards; opportunities tab (7 → accept works); import dialog: file upload through the proxy, auto-mapping `Keyword/Intent/Volume/Priority/Target URL`, duplicate row skipped, commit → 8 keywords; re-cluster → «امداد خودرو چری» ×3, «امداد خودرو mvm» ×2 |
| tsc | 0 errors |

## 6. Notes
* Sample data: 8 real queries of emdadmodiran were imported during verification (they carry real GSC metrics) — delete them from the UI if you don't want them.
* Fixed along the way: proxy now forwards `arrayBuffer` (multipart uploads were being corrupted by `text()`); cluster topics were sticky across re-clustering (now only user-set topics are preserved, marked `+manual_topic`).
* GSC join is exact on normalized text; synonym-aware matching (mvm ↔ ام وی ام) is a Phase 9 (AI) improvement.
* Content Brain untouched. Next: **Phase 6 — Content Brain (Kanban pipeline)**.
