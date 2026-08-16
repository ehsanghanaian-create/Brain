"""Basic local dashboard (FastAPI + Jinja2, no external assets). Bound to 127.0.0.1 by scripts/dashboard.py.
Functionality over design. All views are read-only and reuse src.graph.queries.
"""
from __future__ import annotations

import json
from urllib.parse import unquote

from fastapi import FastAPI, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from jinja2 import Environment, BaseLoader

from ..common.config import get_site, load_sites
from ..database.db import connect, rows
from ..graph import queries as Q

app = FastAPI(title="SEO Knowledge Graph — local dashboard", docs_url="/api/docs", redoc_url=None)

BASE = """<!doctype html><html lang="en"><head><meta charset="utf-8"><title>{{ title }} · SEO KG</title>
<style>
body{font-family:system-ui,Segoe UI,Tahoma,sans-serif;margin:0;background:#f7f7f8;color:#222}
header{background:#1f2937;color:#fff;padding:.6rem 1rem;display:flex;gap:1rem;align-items:center;flex-wrap:wrap}
header a{color:#cbd5e1;text-decoration:none;font-size:.95rem}header a.active,header a:hover{color:#fff}
main{padding:1rem;max-width:1400px;margin:auto}h1{font-size:1.3rem;margin:.2rem 0 1rem}
table{border-collapse:collapse;width:100%;background:#fff;font-size:.86rem}th,td{border:1px solid #e5e7eb;padding:.35rem .5rem;text-align:left;vertical-align:top}
th{background:#f1f5f9;position:sticky;top:0}tr:hover td{background:#fafafa}
.cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:.6rem;margin-bottom:1rem}
.card{background:#fff;border:1px solid #e5e7eb;border-radius:8px;padding:.6rem}.card b{display:block;font-size:1.4rem}.card span{color:#64748b;font-size:.8rem}
.badge{display:inline-block;padding:0 .4rem;border-radius:4px;font-size:.75rem;background:#e5e7eb}.high{background:#fecaca}.medium{background:#fde68a}.low{background:#d1fae5}
code{font-size:.8rem;word-break:break-all}.rtl{direction:rtl;text-align:right}.muted{color:#64748b}
form.f{display:flex;gap:.5rem;margin:.5rem 0;flex-wrap:wrap}input,select{padding:.3rem}
#g{width:100%;height:78vh;background:#fff;border:1px solid #e5e7eb}
</style></head><body><header><b>SEO KG</b>
{% for k,v in nav %}<a href="{{ v }}" class="{{ 'active' if k==title else '' }}">{{ k }}</a>{% endfor %}
<span style="margin-left:auto;color:#94a3b8;font-size:.8rem">site: {{ site_id }} · read-only · 127.0.0.1</span></header><main>{% block body %}{% endblock %}</main></body></html>"""

NAV = [("Overview", "/"), ("Pages", "/pages"), ("Categories", "/categories"), ("Graph", "/graph"), ("GSC", "/gsc"), ("Internal Links", "/links"),
       ("SEO Problems", "/problems"), ("SEO Opportunities", "/opportunities"), ("Entities", "/entities"), ("API", "/api/docs")]
env = Environment(loader=BaseLoader(), autoescape=True)


def render(title: str, body_tpl: str, site_id: str, **ctx) -> HTMLResponse:
    tpl = env.from_string(BASE.replace("{% block body %}{% endblock %}", body_tpl))
    return HTMLResponse(tpl.render(title=title, nav=NAV, site_id=site_id, unquote=unquote, **ctx))


def sid(site: str | None) -> str:
    return get_site(site).site_id


# ---------------- HTML views ----------------
@app.get("/", response_class=HTMLResponse)
def overview(site: str | None = None):
    conn = connect()
    try:
        s = Q.get_site_summary(conn, sid(site))
    finally:
        conn.close()
    body = """<h1>Overview — {{ s.site.name }} <span class=muted>({{ s.site.url }})</span></h1>
<div class=cards>{% for k,v in s.counts.items() %}<div class=card><b>{{ v }}</b><span>{{ k.replace('_',' ') }}</span></div>{% endfor %}</div>
<p><b>GSC:</b> {{ s.gsc_status }} {% if s.gsc_date_range %}({{ s.gsc_date_range.d0 }} → {{ s.gsc_date_range.d1 }}){% endif %}</p>
<h3>Problems by type</h3><table><tr><th>type</th><th>count</th></tr>{% for k,v in s.problems_by_type.items() %}<tr><td><a href="/problems?type={{ k }}">{{ k }}</a></td><td>{{ v }}</td></tr>{% endfor %}</table>
<h3>Opportunities by type</h3><table><tr><th>type</th><th>count</th></tr>{% for k,v in s.opportunities_by_type.items() %}<tr><td><a href="/opportunities?type={{ k }}">{{ k }}</a></td><td>{{ v }}</td></tr>{% endfor %}</table>
<h3>Last runs</h3><table><tr><th>source</th><th>finished</th><th>status</th></tr>{% for k,v in s.last_runs.items() %}<tr><td>{{ k }}</td><td>{{ v.finished_at }}</td><td>{{ v.status }}</td></tr>{% endfor %}</table>"""
    return render("Overview", body, sid(site), s=s)


@app.get("/pages", response_class=HTMLResponse)
def pages(site: str | None = None):
    conn = connect()
    try:
        s = sid(site)
        data = rows(conn, """SELECT p.url, p.title, p.status_code, p.indexable, p.h1_count, p.word_count, p.internal_links_out, p.in_sitemap, p.depth, n.pagerank, n.node_type,
            (SELECT count(DISTINCT source_url) FROM links l WHERE l.site_id=p.site_id AND l.target_url=p.url AND l.is_internal=1 AND l.source_url!=p.url) inbound,
            (SELECT count(*) FROM seo_problems x WHERE x.site_id=p.site_id AND x.url=p.url) problems
            FROM pages p LEFT JOIN graph_nodes n ON n.site_id=p.site_id AND n.url=p.url AND n.node_type IN ('PAGE','POST','CATEGORY')
            WHERE p.site_id=? AND p.crawl_status='ok' ORDER BY n.pagerank DESC""", (s,))
    finally:
        conn.close()
    body = """<h1>Pages ({{ data|length }} crawled URLs)</h1><table><tr><th>type</th><th>URL</th><th>title</th><th>status</th><th>idx</th><th>H1s</th><th>words</th><th>in</th><th>out</th><th>sitemap</th><th>PR</th><th>problems</th></tr>
{% for r in data %}<tr><td>{{ r.node_type }}</td><td><a href="/page?url={{ r.url|urlencode }}"><code>{{ unquote(r.url) }}</code></a></td><td class=rtl>{{ r.title }}</td><td>{{ r.status_code }}</td><td>{{ r.indexable }}</td><td>{{ r.h1_count }}</td><td>{{ r.word_count }}</td><td>{{ r.inbound }}</td><td>{{ r.internal_links_out }}</td><td>{{ r.in_sitemap }}</td><td>{{ '%.3f'|format(r.pagerank or 0) }}</td><td>{{ r.problems }}</td></tr>{% endfor %}</table>"""
    return render("Pages", body, s, data=data)


@app.get("/page", response_class=HTMLResponse)
def page(url: str, site: str | None = None):
    conn = connect()
    try:
        d = Q.get_page_seo_data(conn, sid(site), url)
    finally:
        conn.close()
    body = """<h1 class=rtl>{{ d.label }}</h1><p><code>{{ d.url }}</code> · type {{ d.type }} · pagerank {{ d.pagerank }} · vault: <code>{{ d.vault_path }}</code></p>
<h3>Crawl</h3><pre style="white-space:pre-wrap;background:#fff;padding:.5rem;border:1px solid #e5e7eb">{{ crawl }}</pre>
<h3>Entities</h3><table><tr><th>type</th><th>entity</th><th>score</th><th>title</th><th>h1</th><th>mentions</th></tr>{% for e in d.entities %}<tr><td>{{ e.type }}</td><td class=rtl>{{ e.entity }}</td><td>{{ e.score }}</td><td>{{ e.in_title }}</td><td>{{ e.in_h1 }}</td><td>{{ e.mentions }}</td></tr>{% endfor %}</table>
<h3>Internal links in ({{ d.internal_links_in.count }}, contextual {{ d.internal_links_in.body_count }})</h3><table><tr><th>source</th><th>anchor</th><th>nav</th></tr>{% for l in d.internal_links_in.sources %}<tr><td><code>{{ l.url }}</code></td><td class=rtl>{{ l.anchor }}</td><td>{{ l.nav }}</td></tr>{% endfor %}</table>
<h3>Internal links out</h3><table><tr><th>target</th><th>anchor</th><th>nav</th></tr>{% for l in d.internal_links_out %}<tr><td><code>{{ l.url }}</code></td><td class=rtl>{{ l.anchor }}</td><td>{{ l.nav }}</td></tr>{% endfor %}</table>
<h3>GSC</h3><pre>{{ gsc }}</pre>
<h3>Problems</h3><table><tr><th>type</th><th>severity</th><th>detail</th></tr>{% for p in d.problems %}<tr><td>{{ p.type }}</td><td><span class="badge {{ p.severity }}">{{ p.severity }}</span></td><td><code>{{ p.detail }}</code></td></tr>{% endfor %}</table>
<h3>Opportunities</h3><table><tr><th>type</th><th>score</th><th>related</th><th>reason</th></tr>{% for o in d.opportunities %}<tr><td>{{ o.type }}</td><td>{{ '%.2f'|format(o.score or 0) }}</td><td><code>{{ o.related }}</code></td><td>{{ o.reason }}</td></tr>{% endfor %}</table>"""
    if not d:
        return HTMLResponse("<p>not found</p>", status_code=404)
    return render("Pages", body, sid(site), d=d, crawl=json.dumps(d["crawl"], ensure_ascii=False, indent=1), gsc=json.dumps(d["gsc"], ensure_ascii=False, indent=1))


@app.get("/categories", response_class=HTMLResponse)
def categories(site: str | None = None):
    conn = connect()
    try:
        st = Q.get_site_structure(conn, sid(site))
    finally:
        conn.close()
    body = """<h1>Categories & structure</h1>{% macro tree(items, lvl) %}<ul>{% for c in items %}<li><b class=rtl>{{ c.category }}</b> <span class=muted>({{ c.post_count }} posts) <code>{{ c.url }}</code></span>
<ul>{% for p in c.posts %}<li class=rtl><a href="/page?url={{ p.url|urlencode }}">{{ p.title }}</a></li>{% endfor %}</ul>{{ tree(c.children, lvl+1) }}</li>{% endfor %}</ul>{% endmacro %}
{{ tree(st.category_tree, 0) }}<h3>Pages</h3><ul>{% for p in st.pages %}<li class=rtl><a href="/page?url={{ p.url|urlencode }}">{{ p.title }}</a> <span class=muted>({{ p.word_count }} words)</span></li>{% endfor %}</ul>
<h3>Custom post types</h3><p>{{ st.custom_post_types or 'none' }}</p>"""
    return render("Categories", body, sid(site), st=st)


@app.get("/entities", response_class=HTMLResponse)
def entities(site: str | None = None):
    conn = connect()
    try:
        s = sid(site)
        data = {t: Q.list_entities(conn, s, t) for t in ("SERVICE", "BRAND", "MODEL", "LOCATION")}
    finally:
        conn.close()
    body = """<h1>Entities (extracted from real content)</h1>{% for t, items in data.items() %}<h3>{{ t }}</h3><table><tr><th>name</th><th>aliases</th><th>parent</th><th>source</th><th>pages</th><th>evidence</th></tr>
{% for e in items %}<tr><td class=rtl>{{ e.name }}</td><td class=rtl>{{ e.aliases|join(', ') }}</td><td>{{ e.parent }}</td><td>{{ e.source }}</td><td>{{ e.pages|length }}</td><td><code>{{ e.evidence|tojson }}</code></td></tr>{% endfor %}</table>{% endfor %}"""
    return render("Entities", body, s, data=data)


@app.get("/gsc", response_class=HTMLResponse)
def gsc(site: str | None = None, min_position: float | None = None, max_position: float | None = None, min_impressions: int = 0, order_by: str = "impressions"):
    conn = connect()
    try:
        s = sid(site)
        pages = Q.get_gsc_page_data(conn, s, None, min_position, max_position, min_impressions, order_by, 200)
        queries = Q.get_gsc_query_data(conn, s, None, None, min_impressions, min_position, max_position, False, order_by, 200)
    finally:
        conn.close()
    body = """<h1>Google Search Console (cached locally)</h1><p><b>Status:</b> {{ pages.status }} {{ pages.note or '' }}</p>
<form class=f>pos <input name=min_position value="{{ request_min or '' }}" size=3> – <input name=max_position value="{{ request_max or '' }}" size=3> min impr <input name=min_impressions value="{{ mi }}" size=5>
<select name=order_by><option>impressions</option><option>clicks</option><option>position</option><option>ctr</option></select><button>filter</button> <a href="/gsc?min_position=4&max_position=15">positions 4-15</a></form>
<h3>Pages</h3><table><tr><th>page</th><th>clicks</th><th>impr</th><th>CTR</th><th>pos</th><th>queries</th></tr>{% for r in pages.rows %}<tr><td><code>{{ r.page }}</code></td><td>{{ r.clicks }}</td><td>{{ r.impressions }}</td><td>{{ '%.2f%%'|format(r.ctr*100) }}</td><td>{{ r.position }}</td><td>{{ r.queries }}</td></tr>{% endfor %}</table>
<h3>Queries</h3><table><tr><th>query</th><th>clicks</th><th>impr</th><th>CTR</th><th>pos</th><th>pages</th><th>important</th></tr>{% for r in queries.rows %}<tr><td class=rtl>{{ r.query }}</td><td>{{ r.clicks }}</td><td>{{ r.impressions }}</td><td>{{ '%.2f%%'|format(r.ctr*100) }}</td><td>{{ r.position }}</td><td>{{ r.pages_count }}</td><td>{{ r.importance_reason or '' }}</td></tr>{% endfor %}</table>"""
    return render("GSC", body, s, pages=pages, queries=queries, request_min=min_position, request_max=max_position, mi=min_impressions)


@app.get("/links", response_class=HTMLResponse)
def links(site: str | None = None):
    conn = connect()
    try:
        s = sid(site)
        orphans = Q.find_orphans(conn, s, include_nav_only=True)
        opps = Q.find_internal_link_opportunities(conn, s, limit=100)
        matrix = rows(conn, "SELECT source_url, target_url, count(*) n, MIN(is_nav) nav FROM links WHERE site_id=? AND is_internal=1 AND source_url!=target_url GROUP BY 1,2 ORDER BY n DESC", (s,))
    finally:
        conn.close()
    body = """<h1>Internal links</h1><h3>Orphans / nav-only ({{ orphans|length }})</h3><table><tr><th>url</th><th>title</th><th>problem</th><th>severity</th><th>in sitemap</th></tr>
{% for o in orphans %}<tr><td><code>{{ o.url }}</code></td><td class=rtl>{{ o.title }}</td><td>{{ o.problem_type }}</td><td><span class="badge {{ o.severity }}">{{ o.severity }}</span></td><td>{{ o.in_sitemap }}</td></tr>{% endfor %}</table>
<h3>Internal linking opportunities (top {{ opps|length }})</h3><table><tr><th>score</th><th>source</th><th>→ target</th><th>anchor</th><th>reason</th><th>conf</th></tr>
{% for o in opps %}<tr><td>{{ '%.2f'|format(o.score) }}</td><td><code>{{ o.source_page }}</code></td><td><code>{{ o.target_page }}</code></td><td class=rtl>{{ o.potential_anchor }}</td><td>{{ o.reason }}</td><td>{{ o.confidence }}</td></tr>{% endfor %}</table>
<h3>Link matrix ({{ matrix|length }} distinct source→target)</h3><table><tr><th>source</th><th>target</th><th>count</th><th>nav-only</th></tr>{% for m in matrix %}<tr><td><code>{{ unquote(m.source_url) }}</code></td><td><code>{{ unquote(m.target_url) }}</code></td><td>{{ m.n }}</td><td>{{ m.nav }}</td></tr>{% endfor %}</table>"""
    return render("Internal Links", body, s, orphans=orphans, opps=opps, matrix=matrix)


@app.get("/problems", response_class=HTMLResponse)
def problems(site: str | None = None, type: str | None = None, severity: str | None = None):
    conn = connect()
    try:
        s = sid(site)
        d = Q.get_seo_problems(conn, s, type, severity, None, 500)
    finally:
        conn.close()
    body = """<h1>SEO Problems</h1><p>{% for k,v in d.summary.items() %}<a href="/problems?type={{ k }}"><span class="badge {{ v.severity }}">{{ k }} · {{ v.count }}</span></a> {% endfor %}</p>
<table><tr><th>type</th><th>severity</th><th>url</th><th>detail</th></tr>{% for p in d['items'] %}<tr><td>{{ p.type }}</td><td><span class="badge {{ p.severity }}">{{ p.severity }}</span></td><td><a href="/page?url={{ p.url|urlencode }}"><code>{{ p.url }}</code></a></td><td><code>{{ p.detail|tojson }}</code></td></tr>{% endfor %}</table>"""
    return render("SEO Problems", body, s, d=d)


@app.get("/opportunities", response_class=HTMLResponse)
def opportunities(site: str | None = None, type: str | None = None):
    conn = connect()
    try:
        s = sid(site)
        d = Q.get_seo_opportunities(conn, s, type, None, 0.0, 300)
    finally:
        conn.close()
    body = """<h1>SEO Opportunities</h1><p>{% for k,v in d.summary.items() %}<a href="/opportunities?type={{ k }}"><span class=badge>{{ k }} · {{ v.count }} (avg {{ v.avg_score }})</span></a> {% endfor %}</p>
<table><tr><th>type</th><th>score</th><th>url</th><th>related / query</th><th>reason</th><th>conf</th><th>breakdown</th></tr>{% for o in d['items'] %}<tr><td>{{ o.type }}</td><td>{{ '%.2f'|format(o.score or 0) }}</td><td><code>{{ o.url }}</code></td><td><code>{{ o.related_url }}</code> {{ o.query }}</td><td>{{ o.reason }}</td><td>{{ o.confidence }}</td><td><code>{{ o.score_breakdown|tojson }}</code></td></tr>{% endfor %}</table>"""
    return render("SEO Opportunities", body, s, d=d)


@app.get("/graph", response_class=HTMLResponse)
def graph(site: str | None = None):
    body = """<h1>Graph <span class=muted>(LINKS_TO / BELONGS_TO / ABOUT / OFFERS / TARGETS; drag nodes)</span></h1>
<form class=f id=f>types <input id=types value="PAGE,POST,CATEGORY,BRAND,MODEL,SERVICE,LOCATION" size=50> edges <input id=edges value="LINKS_TO,BELONGS_TO,ABOUT,OFFERS,TARGETS" size=40><button type=button onclick="load()">reload</button></form>
<canvas id=g></canvas><script>
const COL={SITE:'#e74c3c',PAGE:'#3498db',POST:'#5dade2',CATEGORY:'#f39c12',BRAND:'#8e44ad',MODEL:'#af7ac5',SERVICE:'#27ae60',LOCATION:'#1abc9c',QUERY:'#95a5a6',SCHEMA:'#7f8c8d',SEO_PROBLEM:'#c0392b',SEO_OPPORTUNITY:'#2ecc71'};
let N=[],E=[],drag=null;const cv=document.getElementById('g'),cx=cv.getContext('2d');
function resize(){cv.width=cv.clientWidth;cv.height=cv.clientHeight}window.onresize=resize;resize();
async function load(){const q=new URLSearchParams({node_types:document.getElementById('types').value,edge_types:document.getElementById('edges').value,limit:400});const d=await (await fetch('/api/subgraph?'+q)).json();
N=d.nodes.map((n,i)=>({...n,x:cv.width/2+Math.cos(i)*200*Math.random(),y:cv.height/2+Math.sin(i)*200*Math.random(),vx:0,vy:0}));const idx=Object.fromEntries(N.map((n,i)=>[n.node_id,i]));E=d.edges.filter(e=>e.source in idx&&e.target in idx).map(e=>({s:idx[e.source],t:idx[e.target],type:e.type}));}
function step(){for(let i=0;i<N.length;i++){for(let j=i+1;j<N.length;j++){const a=N[i],b=N[j];let dx=b.x-a.x,dy=b.y-a.y,d2=dx*dx+dy*dy+0.01,f=1800/d2;dx*=f;dy*=f;a.vx-=dx;a.vy-=dy;b.vx+=dx;b.vy+=dy;}}
for(const e of E){const a=N[e.s],b=N[e.t];let dx=b.x-a.x,dy=b.y-a.y,d=Math.sqrt(dx*dx+dy*dy)+0.01,f=(d-90)*0.01;dx=dx/d*f;dy=dy/d*f;a.vx+=dx;a.vy+=dy;b.vx-=dx;b.vy-=dy;}
for(const n of N){if(n===drag)continue;n.vx+=(cv.width/2-n.x)*0.002;n.vy+=(cv.height/2-n.y)*0.002;n.vx*=0.85;n.vy*=0.85;n.x+=n.vx;n.y+=n.vy;}
cx.clearRect(0,0,cv.width,cv.height);cx.strokeStyle='#cbd5e1';for(const e of E){const a=N[e.s],b=N[e.t];cx.beginPath();cx.moveTo(a.x,a.y);cx.lineTo(b.x,b.y);cx.stroke();}
for(const n of N){const r=6+Math.sqrt((n.pagerank||0)*400);cx.fillStyle=COL[n.type]||'#999';cx.beginPath();cx.arc(n.x,n.y,r,0,7);cx.fill();cx.fillStyle='#222';cx.font='11px sans-serif';cx.fillText(n.label.slice(0,28),n.x+r+2,n.y+4);}
requestAnimationFrame(step);}
cv.onmousedown=e=>{const r=cv.getBoundingClientRect(),x=e.clientX-r.left,y=e.clientY-r.top;drag=N.find(n=>(n.x-x)**2+(n.y-y)**2<150)||null;};cv.onmousemove=e=>{if(drag){const r=cv.getBoundingClientRect();drag.x=e.clientX-r.left;drag.y=e.clientY-r.top;}};cv.onmouseup=()=>drag=null;
load().then(step);</script>"""
    return render("Graph", body, sid(site))


# ---------------- JSON API (read-only, mirrors MCP tools) ----------------
def _api(fn, *a):
    conn = connect()
    try:
        return JSONResponse(fn(conn, *a))
    finally:
        conn.close()


@app.get("/api/summary")
def api_summary(site: str | None = None):
    return _api(Q.get_site_summary, sid(site))


@app.get("/api/subgraph")
def api_subgraph(site: str | None = None, node_types: str = "", edge_types: str = "", limit: int = 300):
    nt = [x for x in node_types.split(",") if x] or None
    et = [x for x in edge_types.split(",") if x] or None
    return _api(Q.get_subgraph, sid(site), nt, et, limit)


@app.get("/api/search")
def api_search(q: str, site: str | None = None, node_type: str | None = None, limit: int = 20):
    return _api(Q.search_graph, sid(site), q, node_type, limit)


@app.get("/api/node")
def api_node(ref: str, site: str | None = None):
    return _api(Q.get_node, sid(site), ref)


@app.get("/api/orphans")
def api_orphans(site: str | None = None, include_nav_only: bool = False):
    return _api(Q.find_orphans, sid(site), include_nav_only)


@app.get("/api/problems")
def api_problems(site: str | None = None, type: str | None = None, severity: str | None = None):
    return _api(Q.get_seo_problems, sid(site), type, severity, None, 500)


@app.get("/api/opportunities")
def api_opportunities(site: str | None = None, type: str | None = None):
    return _api(Q.get_seo_opportunities, sid(site), type, None, 0.0, 500)


@app.get("/api/sites")
def api_sites():
    return JSONResponse([{"site_id": s.site_id, "name": s.name, "url": s.canonical_url} for s in load_sites()])
