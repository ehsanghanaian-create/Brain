# sample-site — fake example data for SEO Brain

Everything here is **invented** (domain `example.com`, brand "Example Auto Care"). It exists so a fresh clone can be exercised
end-to-end without any real client data. Nothing in this folder is read automatically; copy what you need.

| File | Use |
|---|---|
| `site.yaml` | Per-site config template → copy to `config/site.yaml` (git-ignored) and edit. |
| `keywords.sample.csv` | Keyword import format (`POST /api/v1/sites/{id}/keywords/import`). |
| `site-memory.sample.json` | Site Brain memory (`PUT /api/v1/sites/{id}/memory`) — business rules, tone, CTA rules, forbidden claims. |
| `content-plan.sample.csv` | Content Strategy Planner import (Phase 8.5). |

Create the site through the API or the UI (Sites → افزودن سایت):

```bash
curl -X POST http://127.0.0.1:8000/api/v1/sites -H "Content-Type: application/json" \
  -d '{"site_id":"example-site","name":"Example Auto Care","canonical_url":"https://example.com/","language":"fa-IR","country":"IR"}'
```

Real data (crawl, Search Console, graph, drafts, AI ledger) is written under `data/` and `data/sites/<site_id>/`, which are git-ignored.
