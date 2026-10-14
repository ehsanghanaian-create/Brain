# Independent organic rank snapshots

SEO Brain stores observed organic SERP positions separately from Search Console average position. The first market is Iran (`country=ir`, `language=fa`); mobile is the default device. Every observation records its provider, date, device, result depth, matching URL, and sampled competitors. Missing data is never displayed as rank zero.

## Provider and budget

The default provider is SerpKite. Its [documented free grant](https://serpkite.com/docs/credits-and-billing) is 1,000 credits per verified account each month, plus a one-time signup grant. A real-time search costs one credit at depth 10 and two at depth 20. At 323 keywords per day, depth 10 needs about 9,690 credits in a 30-day month, so a free account cannot cover all keywords daily. The default cap of 30 keywords per day is a rotating pilot; unmeasured keywords remain explicitly unmeasured. The provider may also apply a free-account daily cap. SerpKite's [batch lane](https://serpkite.com/docs/guides/rank-tracking) halves the credit cost, but this first integration uses the simpler real-time API and does not claim batch pricing.

Alternative providers supported by the same dashboard: `SERPAPI_API_KEY` for SerpApi, or `DATAFORSEO_LOGIN` and `DATAFORSEO_PASSWORD` for DataForSEO. Configure one secret on the backend host, never in the frontend or repository. Set the matching provider in the Rank Tracking settings. No provider is called without a configured secret.

The backend scheduler checks every ten minutes and enqueues one run per site after 06:00 Asia/Tehran. The selected keywords rotate by oldest recorded observation. It is safe to retry the scheduler: a unique site/date key prevents duplicate daily runs. The page shows partial, blocked, and quota errors, plus the number checked. An operator can trigger the day's run after credentials are configured. Change `max_keywords_per_run` only after checking the provider balance and intended spend. For full daily coverage at 323 keywords, raise it to at least 323 and ensure the account has sufficient credits. No purchase or automatic recharge is configured by SEO Brain.

## Verification

Run `PYTHONPATH=backend python -m pytest -q backend/tests/analysis/test_serp_rank.py` and type-check the frontend. After deployment, verify `/api/v1/sites/<site-id>/rank-tracking/overview` returns `provider_ready`, the correct keyword count, and no fabricated ranks. After the first real run, verify the provider's request ledger against `serp_rank_runs.provider_requests`, inspected URLs, and the recorded date/device. A live result can vary by location and time; it is a scoped snapshot, not a universal Google rank.
