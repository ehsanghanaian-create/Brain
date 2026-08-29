const base = process.env.ADS_VERIFY_BASE || 'http://127.0.0.1:3000/api/backend/ads-data';

const [eventsResponse, ipsResponse, summaryResponse] = await Promise.all([
  fetch(`${base}/events?hours=1&limit=10`),
  fetch(`${base}/ips?hours=1&limit=20`),
  fetch(`${base}/summary?hours=1`)
]);
if (![eventsResponse, ipsResponse, summaryResponse].every((response) => response.ok)) {
  throw new Error(`API status ${eventsResponse.status}/${ipsResponse.status}/${summaryResponse.status}`);
}
const events = await eventsResponse.json();
const ips = await ipsResponse.json();
const summary = await summaryResponse.json();
const event = events.items?.[0] || {};
const ip = ips.items?.[0] || {};

for (const field of ['proxy_ip', 'ip_confidence', 'ip_resolution_version', 'ads_attribution']) {
  if (!(field in event)) throw new Error(`events API missing ${field}`);
}
for (const field of ['proxy_ip', 'ip_confidence', 'ip_resolution_version', 'google_ads_confirmed_events']) {
  if (!(field in ip)) throw new Error(`IPs API missing ${field}`);
}
if (!('google_ads_confirmed_events' in (summary.totals || {}))) {
  throw new Error('summary API missing Ads attribution totals');
}

console.log(JSON.stringify({
  api_ok: true,
  event_total: events.total,
  ip_count: ips.count,
  latest_confidence: event.ip_confidence,
  latest_resolution_version: event.ip_resolution_version,
  latest_ads_attribution: event.ads_attribution,
  dedicated_fields_present: true
}));
