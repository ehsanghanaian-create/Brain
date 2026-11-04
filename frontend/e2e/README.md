# UI release checks

`pnpm test:e2e` starts an isolated synthetic API and the dashboard on loopback ports 18121/18120. CI runs the production build; local runs use webpack development mode. Install Chromium with `pnpm exec playwright install chromium` first, or set `UI_QA_CHROME=1` to use installed Chrome. No Google credentials, database, WordPress access or paid SERP requests are required.

Covered tasks: overview navigation and source freshness at 320/375/768/1024/1440 px, Escape and focus return in the mobile menu, readable graph direction and keyboard selection, source failure, calendar failure/retry, named filters, keyboard opening of calendar articles, stale response after switching sites, and discoverable settings. Axe covers applicable WCAG A/AA rules in the checked states; this is not a full accessibility conformance audit.

For an authorized live/candidate **read-only** smoke run, set `UI_QA_BASE_URL` to the private frontend tunnel. The suite blocks all browser mutations. The second synthetic-site race test is skipped in live mode; it must pass in the isolated suite. Do not upload live traces/screenshots to public CI: they can contain business data. CI artifacts contain synthetic data only.

This suite does not establish task comprehension, SUS, conversion improvement, physical-device compatibility, screen-reader usability, or permissions across real users. Those need the participant sessions and role matrix in `docs/seo-brain/ux-ui-study-protocol-2026-11-04.md`. Do not call automated passes a completed user study. Draft creation, publication and paid rank checks are not exercised against production.
