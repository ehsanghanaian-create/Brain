# Salimore sculpted glass navigation

Preview: `/design/menu`. Direct responsive canvas: `/design/menu?canvas=1`.

## Current approved direction

The latest user-supplied palette image overrides earlier teal, cobalt and amber
experiments. Use exactly these five foundation colors, with translucent mixtures
and reflection layers derived from them:

| Token | Hex | Role |
| --- | --- | --- |
| Ivory | `#FFFCF2` | Light canvas and dark foreground |
| Stone | `#CCC5B9` | Secondary text, borders and neutral layering |
| Graphite | `#403D39` | Dark glass surface and light secondary text |
| Ink | `#252422` | Dark canvas, light foreground and orange-button text |
| Orange | `#EB5E28` | Primary actions, selected destinations and identity |

Preserve the sculpted fantasy/glass shape from the image the user approved for
coding: rounded split rail, reflective rims, translucent volume and tactile
controls. Additional user references specify a connected active-item cutout,
a polished double rim and paired raised/inset shadows. The selection connection
tracks the visible active row during scrolling and resizing. Do not flatten these
materials when changing palette. Backdrop blur
is verified in Chrome's computed styles (`blur(26px) saturate(1.45)` for the shell).
Reflection, border and opacity change between light/dark appearances; the core
orange stays `#EB5E28`. Semantic error colors are separate from branding.

## Navigation and behavior

`navigation-model.ts` derives all 22 destinations and exact titles from the
existing product inventory. `SalimoreShell` integrates this component into the
actual dashboard; the existing gateway still authenticates all routes. All 22
canonical destinations remain available, including five previously hidden only
from navigation. The old sidebar is retained in source but no longer rendered.

The same edge-mounted button collapses and reopens the menu, preserving its
position relative to the menu edge. Module navigation scrolls independently of
the workspace/account controls. Search has an external magnifier button and no
visible keyboard badge; the magnifier and Ctrl/Cmd+K open a grouped search dialog
containing the whole inventory. The inline field can filter the navigation.

The quick-add site form validates a name and domain and continues to the real
`/dashboard/sites/new` route, including from inside a device iframe. Non-sensitive
initial values travel in query parameters and prefill `SiteWizard` through server
props. It does not automatically create a site. Origins are normalized, credentials
and non-HTTP schemes rejected, and URL query/path/fragment data never forwarded.
Final creation and connection steps stay in the existing wizard.

Other preview task/site identity data are samples; no fake session or sign-out
operation is presented. The reusable `PearlMenu` accepts actual user/site data and
callbacks for integration. Light/dark mode uses the existing theme provider and
synchronizes between the preview host and its same-origin frame.

## Actual responsive device previews

The host uses a same-origin iframe with independent CSS viewport **width AND
height**, so svh/media queries and inner scrolling respond to each device. Scaling
fits only the visual presentation into the host, without changing the frame's
CSS viewport:

- Laptop: 1440 × 900
- iPad landscape: 1024 × 768
- iPad portrait: 768 × 1024
- Phone: 390 × 844

Chrome DOM measurements confirmed those exact frame viewports, no horizontal
page overflow, and different menu heights for each orientation. Tests also cover
label/destination preservation, presentation scaling, and site-draft handoff.
The add-site handoff was exercised from the frame through the actual wizard with
both name and domain preserved; final creation was deliberately not submitted.
This is browser/viewport QA, not a hardware Safari or human usability certification.

For glass implementation guidance, see
[MDN backdrop-filter](https://developer.mozilla.org/en-US/docs/Web/CSS/Reference/Properties/backdrop-filter)
and [WCAG contrast](https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html).
Palette authority is the user's five-swatch image, not an external kit.

Scrollbar chrome is hidden within the preview (menu, search results, workspace
and host page), while wheel, touch and keyboard scrolling remain native. A Chrome
trial confirmed the menu scrolled from 0 to 112px with computed scrollbar-width
`none`. The styling is scoped to this design route, not every operational page.


## Production integration (2026-11-05)

`SalimoreShell` receives a display-only account name from the authenticated
server cookie, loads actual sites, job runs and the action inbox through the
existing authenticated proxy, and scopes navigation to the selected site. It
never uses the cookie projection to authorize a request or assign a role. Logout
uses the existing `/auth/logout` gateway route. The prototype samples and fake
task actions are confined to `/design/menu`; operational actions point to the
real content calendar, site wizard, settings, help and processing history.

The desktop edge control uses the existing sidebar cookie/keyboard provider.
Mobile uses a modal sheet with Escape/focus return. Initial tablet widths use
the compact rail. The approved foundation tokens now live in
`styles/themes/salimore.css`; old theme selections migrate to Salimore while
retaining the light/dark preference. Semantic error and chart series colors
remain distinct for readable analytics.
