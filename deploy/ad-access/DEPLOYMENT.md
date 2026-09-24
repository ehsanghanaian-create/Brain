# Permanent repeated Ads entry rule — deployed 2026-09-14

Production service `ead-access.service` is enabled and running on `gearbox`.
Activated prospectively at 12:37 UTC; existing visitor history was skipped.
The existing Netafraz token was reused successfully; no new token is needed.

## Policy and scope

For modirankhodro-emdad.com, two distinct current-URL GCLIDs on navigate loads
received in strictly less than 60 seconds produce a permanent exact-IP deny
on Iran (195.28.168.48) and Europe (116.202.95.162). No expiry is set.
Reload, browser history, internal attribution, duplicate GCLID, heartbeat,
QA/test traffic and configured infrastructure ranges do not qualify.
Direct, organic and referral visits never enter the detector, regardless of
their visit or event count. Risk score and repeated non-Ads behavior are display
signals only and cannot create an automatic access decision.
This is an operational click-ID rule, not verification that Google billed a
click. Untagged and braid-only traffic cannot satisfy it. JavaScript/GTM must
execute to report an entry. The second page may already have been delivered
before denial takes effect. Previously downloaded/cached content cannot be revoked.

## Deployed architecture

GTM-K9DQ45T3 version 10 is Live: collector 1.0.3-origin-entry. Only tag 29
(ADS | Live IP & Behavior Collector v1) changed. Previous telemetry remains.
The collector posts fresh GCLIDs to `/_ead_entry.php` on the website origin.
Origin REMOTE_ADDR is authoritative; no browser-supplied IP or XFF is trusted.
The legacy SEO Brain collector observed a proxy/VPN IP for the same browser,
so its IP is deliberately not used for this rule.

Each origin has public `_ead_entry.php` and signed `_ead_access.php`, with
core.php, entry_core.php and config.php in private sibling `ead-access/`.
The bounded journal holds 1000 records; per-IP limit is 10 entries/minute.
The worker polls both journals with HMAC authentication, cursor/dedup and
separate SQLite storage; it delivers desired bans to both origins with retry.
Existing .htaccess content is preserved beneath an owned top rewrite block.
State, audit, pre-change backups and unblock tombstones are retained.
No SEO Brain backend container or source was replaced/restarted.

VPS paths:
- /opt/ead-access/worker.py and detector.py
- /etc/ead-access/config.json (0600; contains private origin keys)
- /var/lib/ead-access/state.db
- /var/lib/ead-access/origin-entries.db
- /etc/systemd/system/ead-access.service

Worker loop sleeps 0.5 seconds after each iteration. Actual latency includes
network calls and host rule propagation; this is not a subsecond guarantee.
Origin drift is reconciled every 30 seconds. Network timeouts pause delivery to
that origin for 180 seconds to avoid triggering a host rate ban. An origin outage is retried and
does not prevent attempting the other origin. A full journal gap is logged
and skipped; this bounded implementation cannot promise zero loss on a long
outage. A reset journal requires operator reconciliation.

## Validation

- 16 Python tests, 8 final collector JavaScript checks, 12 PHP entry checks
  and 17 PHP receiver checks passed.
- Both hosts reject unsigned control calls and ignore forged client-IP headers.
- Controlled test IP: first entry allowed; same GCLID on the second origin
  did not ban; second distinct GCLID under 60 seconds produced one decision.
- Root, Asian landing, Renault landing and robots.txt all returned 403 on
  both origins. Europe applied on the immediate check; Iran initially served
  200 and consistently returned 403 about 10 seconds after the second entry.
  This measured LiteSpeed delay is not an instantaneous enforcement claim.
- A real WebP image asset also returned 200 -> 403 -> 200 on both origins.
- Manual unblock restored all four paths to 200 on both hosts; no QA decision
  remained active. Tests did not click any paid advertisement.
- Fresh in-app browser loaded collector 1.0.3, recorded its actual website IP
  in the origin journal and production ingestion database, and retained
  legacy telemetry. Reload left the entry count at one.
- Existing Chrome cache temporarily kept collector 1.0.2; GTM response has
  max-age=900. Fresh-browser verification avoids claiming cached clients
  receive the new collector immediately.
- Service restart preserved cursors and state, resumed healthy, no errors.
- Europe non-owned htaccess content compared exactly with the before snapshot.
  Iran original content compared exactly after excluding the two concurrently added proxy-IP lines; a concurrent existing IP Htaccess Blocker writer
  added 37.27.241.43 to its own section. Our controller did not add those
  lines and they were left intact. Do not concurrently overwrite htaccess.

## Operator commands

Status:
`python3 /opt/ead-access/worker.py --config /etc/ead-access/config.json status`

Remove a rule-owned ban (durable cancellation on both origins):
`python3 /opt/ead-access/worker.py --config /etc/ead-access/config.json unblock --ip IP --reason "Operator reason"`

Inspect failures:
`journalctl -u ead-access.service --since "15 minutes ago"`

Stop new detection/delivery: set enabled=false in config.json (preserve all
other fields and keys), or stop ead-access.service. Existing bans persist.
Unblock remains available with detection disabled. It removes only rule-owned bans; independent legacy/plugin bans can still deny that IP. The permanent denylist has no configured size cap; review its growth and host performance operationally. Do not delete the state
DB to unblock: that loses the audit/cursors and leaves origin rules behind.
GTM version 9 is the previous collector rollback; rolling it back does not
remove existing bans. Origin code backups and owned markers support targeted
rollback without replacing unrelated website files.

## Manual WordPress IP blocks (added 2026-09-24)

The `ip-htaccess-blocker` plugin v1.2.2 writes exact-IP rewrite denies before
WordPress's terminal rewrite rules on the Iran origin. A separate
`ead-manual-sync.timer` runs every 60 seconds on `gearbox`: it fetches the
authoritative WordPress list through the existing backend connection and
delivers each manual decision to both origins over the signed control API.
Its durable state is `/var/lib/ead-access/manual-sync.json`; its latest result
is `/var/lib/ead-access/manual-sync-status.json`. A failed WordPress fetch never
unblocks existing decisions. Unblock and later reblock use distinct decision IDs.
At most three changes per origin are attempted in one run; Europe calls are
paced four seconds apart. Check `systemctl status ead-manual-sync.timer` and
the status JSON before claiming both origins are current.

The VPS-to-Europe HTTPS path timed out after a burst of initial manual rules
on 2026-09-24. The 47 then-current manual IPs were delivered to both origins
through a trusted operator host; the timer subsequently reported 47/47 and no
errors. The automatic detector's separate Europe health can still be degraded
until the VPS path recovers; the dashboard explicitly shows that condition.

QA campaigns beginning qa_origin/qa_access_signal should be excluded from
business reporting. Controlled enforcement entries used campaign
access_rule_validation_20260914 only in the origin journal before production
bootstrap, with separate QA state. No Google Ads exclusion/budget was changed.

## 24-hour Ads threshold automation — 2026-09-14

`seo-brain-ads-threshold-blocker-1` runs beside SEO Brain and calls the existing
WordPress security API with its stored Application Password. Within a rolling
24-hour window, an IP is permanently blocked when either count reaches three:

- three distinct fresh GCLIDs recorded by the website origin; or
- three unique `tel_click` events whose GCLID maps to exactly one origin IP.

Direct, organic, referral, reload, carried attribution, missing-GCLID and
ambiguous-GCLID/IP events cannot qualify. Risk score is not an input. The
website-origin journal is authoritative for the client IP; the legacy telemetry
IP is never used as the enforcement target. QA/test campaigns, private IPs and
configured infrastructure addresses/ranges are excluded.

The service reads both databases read-only, stores durable decisions and retry
state in `/var/lib/ead-threshold/threshold.db`, and connects only to the internal
backend network. Its config is `/etc/ead-access/threshold.json` and contains no
credential. The API token is supplied from the existing production environment.
The WordPress audit reason begins `Auto Ads rule:`; the dashboard uses this to
show `مسدود خودکار · دائمی` separately from a manual/plugin block.

At activation, no production IP met the new origin-verified criterion. A
documentation-only TEST-NET IP was blocked and unblocked through the complete
internal API/Application-Password/plugin path; it was removed immediately.
Six focused threshold tests and the complete 25-test Python suite passed.
Compose rollback: `/opt/seo-brain/compose.production.before-ads-threshold.yaml`.

This conservative join needs a GCLID recorded after origin journaling became
live. Older telemetry-only attacks and braid-only Ads cannot be safely mapped
to the website-observed IP, so they are not auto-blocked by this rule.

## Repeat-visitor rule — 2026-09-24

The threshold worker now also blocks the origin-observed IP of a visitor after
their second distinct fresh Ads GCLID. The same first-party visitor ID must
appear in two `landing` events with `fresh_ads_entry` and `navigate`, each
correlated within 120 seconds to a unique website-origin IP/GCLID observation.
The second entry may be days after the first; the rule reads retained origin
history rather than the rolling 24-hour threshold. If the visitor changes IP,
the second entry's IP is the one blocked. Two different visitor IDs sharing an
IP do not trigger this new rule. Reloads, carried attribution, ambiguous GCLIDs,
QA traffic and protected IPs remain excluded. The pre-existing 60-second
origin rule and three-entry/three-phone-click 24-hour rule remain active.

Production `visitor_rule_start` in `/etc/ead-access/threshold.json` was set at
activation so old pairs were not retroactively blocked. The existing
`seo-brain-ads-threshold-blocker-1` container was restarted with the updated
worker; its state database and previous blocks were retained. Host backups
use suffix `.before-repeat-20260924141347`. Local rule suite: 30 tests passed.
At deployment, the container was running with no recent errors and the new
visitor rule had no pending candidate. This rule blocks site access after the
second paid landing is observed; it cannot prevent the second ad click's charge
or identify visitors whose browser attribution is missing or reset.


## Dashboard status integration — 2026-09-14

The worker now exports an atomic sanitized snapshot to
/var/lib/ead-access/dashboard/status.json. Only that directory is mounted
read-only in the frontend at /app/access-status; keys and SQLite state are
not exposed. GET /api/ads-data/access-status is protected by the same gateway
as the dashboard (unauthenticated probe: 401), private/no-store, fixed path.

The UI refreshes status every 5 seconds and rejects snapshots older than
30 seconds. Permanent blocked, pending/unknown and legacy plugin blocks are
separate labels. The automatic counter is independent of risk scores.
A confirmed label means recent acknowledgements from both origins, not a
new HTTP probe for every listed IP; the prior measured host delay applies.
Exact-IP association requires v3 and trusted/direct confidence. Session rows
without this provenance use only unique approved GCLID association; proxy IP
is never substituted as the actual blocked origin IP. Ambiguity stays unknown.

The frontend release was built from the exact previous live source tree,
with existing manual plugin controls preserved. Local dashboard source had
other pre-existing differences, so it was not used as the full live replacement.
Backend image and collector were preserved. Frontend compose rollback backup:
/opt/seo-brain/compose.production.before-access-status.yaml.

Volume investigation: at the read-only audit, the site's last 24h had 475
records: 168 heartbeat,88 landing,88 page_view,70 exit,34 scroll,27 tel_click,
25 visitor IDs and35 sessions. These are events, not475paid clicks. Some recent
QA campaigns were generated by this deployment; retain audit data and do not
interpret them as attacks. At verification, there were zero automatic bans;
existing plugin bans were visibly labelled next to matching dashboard users.
