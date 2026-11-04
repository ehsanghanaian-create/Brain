# Salimore UI/UX implementation and release evidence

## Scope and brief

The main user is a manager deciding what to investigate or do next to increase organic sales. The three frequent jobs are inspecting observed keyword ranks, finding supported keyword/competitor opportunities, and identifying commercial pages needing work. The overview now exposes these three paths directly, preserving the selected site. Existing opaque surfaces and RTL typography are retained; the change does not introduce another theme or sample growth metrics.

The November 4 read-only production baseline inspected overview, sales, graph, rank tracking, research, calendar, reports and settings at 375 px. Axe found invalid breadcrumb list structure across these routes, unnamed calendar selects, insufficient contrast in tabs/report deltas/a graph score, and keyboard-inaccessible scrolling regions in rank/report tables. Desktop testing additionally exposed low-contrast sidebar group labels. Baseline screenshots and raw business-data observations are held privately outside Git.

## Implemented changes

- Named navigation stays expanded on first desktop visit; an existing collapsed preference is respected. Overview has three direct, site-aware growth routes.
- Graph offers a readable relationship list using the same sampled evidence and existing filters, explicit source/destination, and keyboard-selectable node details. It labels average positions separately from observed SERP ranks. The map remains available.
- Calendar shows explicit loading, failure and retry states. Failed fetches are not presented as an empty calendar. Request generations prevent old site/filter responses replacing the current view. Calendar filters have accessible names, list items are real keyboard buttons, and unscheduled cards can be opened without dragging.
- Shared breadcrumbs, table keyboard scrolling, native select RTL spacing/touch targets, tab contrast, report deltas, graph scores, and reduced-motion theme changes are corrected.
- Settings starts with actual user actions and connection state; technical diagnostics and the service graph are disclosed on demand.
- GitHub frontend validation now runs existing unit tests and the versioned Playwright/axe suite, in addition to typecheck/build. Failure artifacts use synthetic data.

## Verification boundaries

Versioned automated scenarios and run instructions are in `frontend/e2e/README.md`. A live read-only run must not start rank jobs, publish articles, modify team tasks, or use the other business's data. Production rollout changes the Salimore frontend only, with a fresh SQLite/configuration backup, a private candidate against the existing backend, and image-based rollback. Backend identity and existing data should be checked after rollout.

This is an implementation of observed fixes and repeatable release checks. Human task trials, actual screen-reader sessions, a full role/permission audit, physical devices, field Core Web Vitals and conversion impact remain separate, uncompleted evidence categories. No claim of platform-wide perfection or completed human usability testing is made.
