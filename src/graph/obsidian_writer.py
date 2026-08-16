"""Write graph nodes as Obsidian markdown (frontmatter + wikilinks).

Rules:
- one file per graph node under the folder for its type; filenames are Windows-safe and unique
- a [[wikilink]] is written ONLY for a real edge (LINKS_TO, BELONGS_TO, ABOUT, OFFERS, TARGETS, RANKS_FOR, HAS_SCHEMA,
  HAS_PROBLEM, HAS_OPPORTUNITY, HAS_*). Inbound relationships are listed as plain text (Obsidian shows backlinks itself),
  so every graph edge in Obsidian corresponds to exactly one real relationship in SQLite.
- semantic/similarity relationships (internal-link *opportunities*) are listed as plain text, not wikilinks.
- frontmatter contains only real data; unknown values are null.
"""
from __future__ import annotations

import json
import logging
import re
import sqlite3
from collections import defaultdict
from pathlib import Path
from urllib.parse import unquote

import yaml

from ..common.config import SiteConfig
from ..database.db import rows
from .vault import VAULT_FOLDERS, ensure_vault

log = logging.getLogger("graph.obsidian")
_BAD = re.compile(r'[\\/:*?"<>|#^\[\]]+')


def safe_name(label: str, maxlen: int = 80) -> str:
    s = _BAD.sub(" ", unquote(label or "")).strip().strip(".")
    s = re.sub(r"\s+", " ", s)
    return (s[:maxlen].strip() or "untitled")


class ObsidianWriter:
    def __init__(self, conn: sqlite3.Connection, site: SiteConfig, vault: Path):
        self.conn, self.site, self.sid, self.vault = conn, site, site.site_id, vault
        self.nodes: dict[str, dict] = {}
        self.path_of: dict[str, str] = {}   # node_id -> vault-relative path without .md

    def link(self, node_id: str, alias: str | None = None) -> str:
        p = self.path_of.get(node_id)
        if not p:
            return alias or node_id
        return f"[[{p}|{alias or self.nodes[node_id]['label']}]]"

    def _assign_paths(self):
        used: set[str] = set()
        for nid, n in sorted(self.nodes.items(), key=lambda kv: (kv[1]["node_type"], kv[1]["label"])):
            folder = VAULT_FOLDERS.get(n["node_type"], "99-Reports")
            base = safe_name(n["label"])
            if n["node_type"] in ("PAGE", "POST", "CATEGORY") and n["url"]:
                seg = unquote(n["url"]).rstrip("/").split("/")[-1] or "home"
                if n["url"] == self.site.canonical_url:
                    base = f"{base} (home)"
                cand = f"{folder}/{base}"
                if cand.lower() in used:
                    cand = f"{folder}/{base} [{safe_name(seg, 40)}]"
            else:
                cand = f"{folder}/{base}"
            i = 2
            while cand.lower() in used:
                cand = f"{folder}/{base} ({i})"
                i += 1
            used.add(cand.lower())
            self.path_of[nid] = cand

    def write(self, clean: bool = True) -> dict:
        ensure_vault(self.vault)
        self.nodes = {n["node_id"]: {**n, "props": json.loads(n["props"] or "{}")} for n in rows(self.conn, "SELECT * FROM graph_nodes WHERE site_id=?", (self.sid,))}
        edges = rows(self.conn, "SELECT * FROM graph_edges WHERE site_id=?", (self.sid,))
        out_e = defaultdict(list)
        in_e = defaultdict(list)
        for e in edges:
            e["props"] = json.loads(e["props"] or "{}")
            out_e[e["source_id"]].append(e)
            in_e[e["target_id"]].append(e)
        self._assign_paths()
        if clean:
            for folder in VAULT_FOLDERS.values():
                d = self.vault / folder
                if d.exists():
                    for f in d.glob("*.md"):
                        f.unlink()
        written = 0
        for nid, n in self.nodes.items():
            md = self._render(n, out_e[nid], in_e[nid])
            p = self.vault / (self.path_of[nid] + ".md")
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(md, encoding="utf-8")
            self.conn.execute("UPDATE graph_nodes SET vault_path=? WHERE site_id=? AND node_id=?", (self.path_of[nid] + ".md", self.sid, nid))
            written += 1
        self._reports()
        self.conn.commit()
        log.info(f"obsidian: wrote {written} notes to {self.vault}")
        return {"written": written, "vault": str(self.vault)}

    # -------------------------------------------------------------------------------
    def _fm(self, n: dict) -> dict:
        p = n["props"]
        t = n["node_type"]
        fm = {"type": t.lower(), "site_id": self.sid, "node_id": n["node_id"], "label": n["label"]}
        if t in ("PAGE", "POST", "CATEGORY"):
            fm.update({
                "url": unquote(n["url"]) if n["url"] else None, "title": p.get("title"), "status_code": p.get("status_code"),
                "indexable": p.get("indexable"), "indexability_reason": p.get("indexability_reason"),
                "canonical": unquote(p["canonical"]) if p.get("canonical") else None,
                "h1_count": p.get("h1_count"), "word_count": p.get("word_count"), "language": p.get("language"),
                "internal_links_in": p.get("internal_links_in"), "internal_links_out": p.get("internal_links_out"),
                "external_links_out": p.get("external_links_out"), "in_sitemap": p.get("in_sitemap"), "depth": p.get("depth"),
                "gsc_clicks": p.get("gsc_clicks"), "gsc_impressions": p.get("gsc_impressions"), "gsc_ctr": p.get("gsc_ctr"),
                "gsc_position": p.get("gsc_position"), "pagerank": n.get("pagerank"), "community": n.get("community"),
                "schema_types": p.get("schema_types"), "last_crawled": p.get("last_crawled"), "last_gsc_sync": p.get("last_gsc_sync"),
                "wp_id": p.get("wp_id"), "wp_type": p.get("wp_type"), "modified_gmt": p.get("modified_gmt"),
            })
            if t == "CATEGORY":
                fm.update({"taxonomy": p.get("taxonomy"), "slug": p.get("slug"), "post_count": p.get("count")})
        elif t in ("BRAND", "MODEL", "SERVICE", "LOCATION"):
            fm.update({"aliases": p.get("aliases") or [], "source": p.get("source")})
        elif t == "QUERY":
            fm.update({"query": n["label"], "clicks": p.get("clicks"), "impressions": p.get("impressions"), "ctr": p.get("ctr"),
                       "position": p.get("position"), "pages_count": p.get("pages_count"), "importance_reason": p.get("importance_reason")})
        elif t == "SCHEMA":
            fm.update({"schema_type": n["label"], "pages": p.get("pages"), "sitewide": p.get("sitewide")})
        elif t == "SEO_PROBLEM":
            fm.update({"problem_type": n["node_id"].split(":", 1)[1], "severity": p.get("severity"), "count": p.get("count")})
        elif t == "SEO_OPPORTUNITY":
            fm.update({"opportunity_type": n["node_id"].split(":", 1)[1], "count": p.get("count"), "avg_score": p.get("avg_score")})
        elif t == "SITE":
            fm.update({"url": n["url"], "language": p.get("language")})
        return fm

    def _render(self, n: dict, out_edges: list, in_edges: list) -> str:
        fm = self._fm(n)
        p = n["props"]
        t = n["node_type"]
        lines = ["---", yaml.safe_dump(fm, allow_unicode=True, sort_keys=False, default_flow_style=False).strip(), "---", ""]
        lines.append(f"# {n['label']}")
        if n["url"]:
            lines.append(f"\n`{unquote(n['url'])}`")
        by_type = defaultdict(list)
        for e in out_edges:
            by_type[e["edge_type"]].append(e)
        in_by = defaultdict(list)
        for e in in_edges:
            in_by[e["edge_type"]].append(e)

        def sec(title, items):
            if items:
                lines.append(f"\n## {title}")
                lines.extend(items)

        if t in ("PAGE", "POST", "CATEGORY"):
            meta = []
            if p.get("title"):
                meta.append(f"- **Title:** {p['title']}")
            if p.get("meta_description"):
                meta.append(f"- **Meta description:** {p['meta_description']}")
            if p.get("h1"):
                meta.append("- **H1:** " + " | ".join(p["h1"][:8]))
            meta.append(f"- **Status:** {p.get('status_code')} · **Indexable:** {p.get('indexable')} ({p.get('indexability_reason')}) · **Words:** {p.get('word_count')}")
            if p.get("excerpt"):
                meta.append(f"- **Excerpt:** {p['excerpt']}")
            sec("Overview", meta)
            sec("Belongs to", [f"- {self.link(e['target_id'])}" for e in by_type["BELONGS_TO"]])
            sec("About (entities)", [f"- {self.link(e['target_id'])} — {'title' if e['props'].get('in_title') else ('h1' if e['props'].get('in_h1') else str(e['props'].get('mentions')) + ' mentions')}" for e in by_type["ABOUT"]])
            sec("Offers", [f"- {self.link(e['target_id'])}" for e in by_type["OFFERS"]])
            sec("Targets (location)", [f"- {self.link(e['target_id'])}" for e in by_type["TARGETS"]])
            sec("Ranks for (important queries)", [f"- {self.link(e['target_id'])} — pos {e['props'].get('position')}, {e['props'].get('impressions')} impr, {e['props'].get('clicks')} clicks" for e in sorted(by_type["RANKS_FOR"], key=lambda e: -e["weight"])])
            outl = sorted(by_type["LINKS_TO"], key=lambda e: (e["props"].get("nav_only", False), -e["weight"]))
            sec("Internal links out (real)", [f"- {self.link(e['target_id'])}" + (" *(nav)*" if e["props"].get("nav_only") else "") + (f" — anchor: {e['props'].get('anchors')[:80]}" if e["props"].get("anchors") else "") for e in outl])
            inl = sorted(in_by["LINKS_TO"], key=lambda e: (e["props"].get("nav_only", False), -e["weight"]))
            sec("Internal links in (real, listed without wikilinks)", [f"- {self.nodes[e['source_id']]['label']}" + (" *(nav)*" if e["props"].get("nav_only") else "") for e in inl])
            sec("Structured data (page-specific)", [f"- {self.link(e['target_id'])}" for e in by_type["HAS_SCHEMA"]])
            sec("SEO problems", [f"- {self.link(e['target_id'])}" for e in by_type["HAS_PROBLEM"]])
            sec("SEO opportunities", [f"- {self.link(e['target_id'])} (score {round(e['weight'], 2)})" for e in by_type["HAS_OPPORTUNITY"]])
            # semantic suggestions (NOT wikilinks)
            opps = rows(self.conn, "SELECT related_url, score, reason, detail FROM seo_opportunities WHERE site_id=? AND opp_type='internal_link' AND url=? ORDER BY score DESC LIMIT 10", (self.sid, n["url"]))
            sec("Suggested internal links (semantic — not real links yet)", [f"- → {unquote(o['related_url'])} (score {o['score']:.2f}) — {o['reason']}" for o in opps])
        elif t in ("BRAND", "MODEL", "SERVICE", "LOCATION"):
            if p.get("aliases"):
                lines.append(f"\n**Aliases:** {', '.join(p['aliases'])}")
            sec("Belongs to", [f"- {self.link(e['target_id'])}" for e in by_type["BELONGS_TO"]])
            sec("Sub-entities", [f"- {self.link(e['source_id'])}" for e in in_by["BELONGS_TO"]])
            rel = in_by["ABOUT"] + in_by["OFFERS"] + in_by["TARGETS"]
            sec("Pages about this (listed; edges come from the pages)", [f"- {self.nodes[e['source_id']]['label']} — `{unquote(self.nodes[e['source_id']]['url'] or '')}`" for e in sorted(rel, key=lambda e: -e["weight"])])
            ev = p.get("evidence") or []
            sec("Extraction evidence", [f"- `{json.dumps(x, ensure_ascii=False)}`" for x in ev[:12]])
        elif t == "QUERY":
            sec("Ranking pages (edges come from pages)", [f"- {self.nodes[e['source_id']]['label']} — pos {e['props'].get('position')}, {e['props'].get('impressions')} impr" for e in sorted(in_by["RANKS_FOR"], key=lambda e: -e["weight"])])
        elif t == "SCHEMA":
            sec("Used by", [f"- {self.nodes[e['source_id']]['label']}" for e in in_by["HAS_SCHEMA"]])
        elif t == "SEO_PROBLEM":
            ptype = n["node_id"].split(":", 1)[1]
            items = rows(self.conn, "SELECT url, severity, related_url, detail FROM seo_problems WHERE site_id=? AND problem_type=? ORDER BY url", (self.sid, ptype))
            sec(f"Affected pages ({len(items)})", [f"- `{unquote(i['url'])}` — {i['severity']} — `{i['detail'][:160]}`" for i in items])
        elif t == "SEO_OPPORTUNITY":
            otype = n["node_id"].split(":", 1)[1]
            items = rows(self.conn, "SELECT url, related_url, query, score, reason, confidence FROM seo_opportunities WHERE site_id=? AND opp_type=? ORDER BY score DESC LIMIT 100", (self.sid, otype))
            sec(f"Items ({len(items)}, top 100 by score)", [f"- {i['score']:.2f} · `{unquote(i['url'])}`" + (f" → `{unquote(i['related_url'])}`" if i["related_url"] else "") + (f" · query: {i['query']}" if i["query"] else "") + f" — {i['reason']} (confidence {i['confidence']})" for i in items])
        elif t == "SITE":
            sec("Categories", [f"- {self.link(e['target_id'])}" for e in by_type["HAS_CATEGORY"]])
            sec("Pages", [f"- {self.link(e['target_id'])}" for e in sorted(by_type["HAS_PAGE"], key=lambda e: self.nodes[e['target_id']]['label'])])
            sec("Posts", [f"- {self.link(e['target_id'])}" for e in sorted(by_type["HAS_POST"], key=lambda e: self.nodes[e['target_id']]['label'])])
            sec("Tags", [f"- {self.link(e['target_id'])}" for e in by_type["HAS_TAG"]])
            sec("Site-wide structured data", [f"- {self.link(e['target_id'])}" for e in by_type["HAS_SCHEMA"]])
            ents = [nid for nid, x in self.nodes.items() if x["node_type"] in ("BRAND", "MODEL", "SERVICE", "LOCATION")]
            sec("Entities (index)", [f"- {self.nodes[e]['node_type']}: {self.link(e)}" for e in sorted(ents, key=lambda e: (self.nodes[e]['node_type'], self.nodes[e]['label']))])
            probs = [nid for nid, x in self.nodes.items() if x["node_type"] == "SEO_PROBLEM"]
            sec("SEO problem types", [f"- {self.link(e)} ({self.nodes[e]['props'].get('count')})" for e in sorted(probs)])
            opps = [nid for nid, x in self.nodes.items() if x["node_type"] == "SEO_OPPORTUNITY"]
            sec("SEO opportunity types", [f"- {self.link(e)} ({self.nodes[e]['props'].get('count')})" for e in sorted(opps)])
        return "\n".join(lines) + "\n"

    def _reports(self):
        c, sid = self.conn, self.sid
        inv = {
            "total_urls_crawled": c.execute("SELECT count(*) FROM pages WHERE site_id=? AND crawl_status='ok'", (sid,)).fetchone()[0],
            "indexable": c.execute("SELECT count(*) FROM pages WHERE site_id=? AND indexable=1", (sid,)).fetchone()[0],
            "non_indexable": c.execute("SELECT count(*) FROM pages WHERE site_id=? AND indexable=0", (sid,)).fetchone()[0],
            "wp_pages": c.execute("SELECT count(*) FROM posts WHERE site_id=? AND type='page'", (sid,)).fetchone()[0],
            "wp_posts": c.execute("SELECT count(*) FROM posts WHERE site_id=? AND type='post'", (sid,)).fetchone()[0],
            "wp_cpt_items": c.execute("SELECT count(*) FROM posts WHERE site_id=? AND type NOT IN ('post','page')", (sid,)).fetchone()[0],
            "categories": c.execute("SELECT count(*) FROM categories WHERE site_id=?", (sid,)).fetchone()[0],
            "tags": c.execute("SELECT count(*) FROM tags WHERE site_id=?", (sid,)).fetchone()[0],
            "taxonomies": c.execute("SELECT count(*) FROM taxonomies WHERE site_id=?", (sid,)).fetchone()[0],
            "internal_links": c.execute("SELECT count(*) FROM links WHERE site_id=? AND is_internal=1", (sid,)).fetchone()[0],
            "external_links": c.execute("SELECT count(*) FROM links WHERE site_id=? AND is_internal=0", (sid,)).fetchone()[0],
            "redirects": c.execute("SELECT count(*) FROM pages WHERE site_id=? AND redirect_chain IS NOT NULL AND redirect_chain!='[]'", (sid,)).fetchone()[0],
            "canonical_targets": c.execute("SELECT count(DISTINCT canonical) FROM pages WHERE site_id=? AND canonical IS NOT NULL", (sid,)).fetchone()[0],
            "duplicate_content_hashes": c.execute("SELECT count(*) FROM (SELECT content_hash FROM pages WHERE site_id=? AND content_hash IS NOT NULL GROUP BY content_hash HAVING count(*)>1)", (sid,)).fetchone()[0],
            "orphan_pages": c.execute("SELECT count(*) FROM seo_problems WHERE site_id=? AND problem_type='orphan'", (sid,)).fetchone()[0],
            "graph_nodes": len(self.nodes),
            "graph_edges": c.execute("SELECT count(*) FROM graph_edges WHERE site_id=?", (sid,)).fetchone()[0],
            "gsc_rows": c.execute("SELECT count(*) FROM gsc_daily WHERE site_id=?", (sid,)).fetchone()[0],
        }
        md = ["---", f"type: report\nsite_id: {sid}\nreport: site-inventory", "---", "", f"# Site Inventory — {self.site.name}", ""]
        md += [f"- **{k.replace('_', ' ')}:** {v}" for k, v in inv.items()]
        (self.vault / "99-Reports" / "Site Inventory.md").write_text("\n".join(md) + "\n", encoding="utf-8")
        probs = rows(c, "SELECT problem_type, severity, count(*) n FROM seo_problems WHERE site_id=? GROUP BY 1,2 ORDER BY 2,1", (sid,))
        md = ["---", f"type: report\nsite_id: {sid}\nreport: seo-problems", "---", "", "# SEO Problems", "", "| type | severity | count |", "|---|---|---|"]
        md += [f"| [[11-Problems/{safe_name(p['problem_type'].replace('_',' '))}\\|{p['problem_type']}]] | {p['severity']} | {p['n']} |" for p in probs]
        (self.vault / "99-Reports" / "SEO Problems.md").write_text("\n".join(md) + "\n", encoding="utf-8")
        opps = rows(c, "SELECT opp_type, count(*) n, round(avg(score),3) s FROM seo_opportunities WHERE site_id=? GROUP BY 1", (sid,))
        md = ["---", f"type: report\nsite_id: {sid}\nreport: seo-opportunities", "---", "", "# SEO Opportunities", "", "| type | count | avg score |", "|---|---|---|"]
        md += [f"| [[12-Opportunities/{safe_name(o['opp_type'].replace('_',' '))}\\|{o['opp_type']}]] | {o['n']} | {o['s']} |" for o in opps]
        (self.vault / "99-Reports" / "SEO Opportunities.md").write_text("\n".join(md) + "\n", encoding="utf-8")
