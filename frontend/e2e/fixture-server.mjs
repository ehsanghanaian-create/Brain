// Deliberately synthetic data. Never connects to Google, WordPress or a production DB.
import http from 'node:http';
const now = new Date().toISOString();
const counts = { content: 4, crawled: 4, graph_nodes: 2, graph_edges: 1, keywords: 2, planned_content: 1, new_link_suggestions: 0, high_link_suggestions: 0 };
const site = { site_id: 'qa-site', name: 'سایت آزمایش رابط', canonical_url: 'https://example.test', wp_url: 'https://example.test', mode: 'manual', workspace_path: null, created_at: now, updated_at: now };
const portfolioSite = { ...site, state: 'ready', state_reason: '', next_action: 'بررسی فرصت‌های سئو', mission: { objective: 'افزایش فروش با دادهٔ قابل پیگیری', success_metric: 'سفارش تأییدشده' }, issues: [], setup_progress: 100, setup_steps: { wordpress_configured: true, content_synced: true, crawl_ready: true, graph_ready: true }, connections: {}, latest_sync: null, counts };
export function fixture(path) {
  if (path === '/health') return { status: 'ok', version: 'qa', database: 'synthetic', migrations: { applied: [], pending: [] } };
  if (path === '/sites') return [site, { ...site, site_id: 'qa-other', name: 'سایت آزمایش دوم' }];
  if (path === '/portfolio/overview') return { generated_at: now, totals: { ...counts, sites: 1, ready_sites: 1, needs_attention: 0 }, state_counts: { ready: 1, running: 0, attention: 0, partial: 0, not_started: 0 }, by_node_type: { PAGE: 1, QUERY: 1 }, sites: [portfolioSite], recent_activity: [] };
  if (path === '/portfolio/action-inbox') return { generated_at: now, counts: { issue: 0, keyword: 0, link: 0 }, total: 0, limit: 4, offset: 0, items: [], scope: 'fixture', ranking_note: '' };
  if (path === '/jobs' || path.endsWith('/content-plans/categories') || path === '/providers') return [];
  if (path.endsWith('/sync/status')) return { status: 'ready', coverage: { date_to: now.slice(0, 10) } };
  if (path.endsWith('/graph/view')) return { mode: { key: 'seo', title_fa: 'نقشه سئو', description_fa: '', layout: 'radial', group_by: 'none', node_types: ['PAGE','QUERY'], relation_types: ['RANKS_FOR'] }, nodes: [{ id: 'page-one', site_id: site.site_id, type: 'PAGE', metadata: { label: 'راهنمای خرید آزمایشی' } }, { id: 'query-one', site_id: site.site_id, type: 'QUERY', metadata: { label: 'پرسش خریدار آزمایشی' } }], edges: [{ source: 'page-one', target: 'query-one', site_id: site.site_id, relation_type: 'RANKS_FOR', weight: 1, metadata: {} }], truncated: false, total_nodes: 2, stats: { by_type: { PAGE: 1, QUERY: 1 }, by_relation: { RANKS_FOR: 1 } } };
  if (path.includes('/graph/node-details/')) { const page = path.endsWith('page-one'); return { id: page ? 'page-one' : 'query-one', type: page ? 'PAGE' : 'QUERY', label: page ? 'راهنمای خرید آزمایشی' : 'پرسش خریدار آزمایشی', url: null, page: { content_status: 'ok' }, keyword: {}, related: {}, edges: [], neighbors: [] }; }
  if (path.endsWith('/content-plans/calendar')) return { from: now.slice(0,10), to: now.slice(0,10), days: { [now.slice(0,10)]: [{ id: 1, title: 'مقالهٔ آزمایش صفحه‌کلید', status: 'planned', publish_date: now.slice(0,10) }] }, unscheduled: [], counts: { by_status: { planned: 1 }, total: 1 }, categories: [] };
  return null;
}
http.createServer((req, res) => {
  const path = new URL(req.url, 'http://localhost').pathname.replace(/^\/api\/v1/, '');
  // All mutation requests fail: even a regression cannot publish or consume paid credits.
  const data = req.method === 'GET' ? fixture(path) : null;
  res.writeHead(data === null ? 503 : 200, { 'Content-Type': 'application/json' });
  res.end(JSON.stringify(data ?? { error: { code: 'qa_unavailable', message: 'منبع آزمایشی در دسترس نیست' } }));
}).listen(18121, '127.0.0.1');
