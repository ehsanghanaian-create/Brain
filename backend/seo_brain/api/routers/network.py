"""Brain network map (settings → «شبکهٔ Brain»): how SEO Brain connects to its AI writers, to every site (WordPress),
each site to its Google data (Search Console / GA4) and how the sites link to one another — one read-only snapshot."""
from __future__ import annotations

from collections import Counter
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends
from sqlalchemy import Engine, text

from ...ai.config import ProviderConfigRepository
from ..deps import engine

router = APIRouter(prefix="/network", tags=["network"])
BRAIN = "brain"


def _host(url: str | None) -> str:
    h = (urlsplit(url or "").hostname or "").lower()
    return h[4:] if h.startswith("www.") else h


@router.get("")
def network(eng: Engine = Depends(engine)) -> dict:
    nodes: list[dict] = [{"id": BRAIN, "kind": "brain", "label": "SEO Brain", "status": "ok", "meta": {}}]
    edges: list[dict] = []
    for p in ProviderConfigRepository(eng).list():
        d = p.to_dict()
        status = "ok" if d["configured"] and (d.get("last_test") or {}).get("ok") else ("warn" if d["configured"] else "off")
        nid = f"provider:{p.id}"
        nodes.append({"id": nid, "kind": "provider", "label": d["kind_label"], "status": status,
                      "meta": {"name": p.name, "kind": p.kind, "model": p.default_model, "configured": d["configured"], "key_days_left": d.get("key_days_left"), "key_expired": d.get("key_expired")}})
        edges.append({"id": f"{BRAIN}->{nid}", "source": BRAIN, "target": nid, "kind": "ai", "label": "نویسندهٔ هوش مصنوعی", "status": status, "weight": 3 if status == "ok" else 1})
    with eng.connect() as cx:
        sites = cx.execute(text("SELECT site_id, name, canonical_url, wp_url, mode, gsc_property, ga4_property FROM sites ORDER BY site_id")).all()
        conns = {(r[0], r[1]): r[2] for r in cx.execute(text("SELECT site_id, kind, status FROM site_connections")).all()}
        posts = {r[0]: int(r[1]) for r in cx.execute(text("SELECT site_id, COUNT(*) FROM posts GROUP BY site_id")).all()}
        external = cx.execute(text("SELECT site_id, target_url FROM links WHERE is_internal=0")).all()
    hosts: dict[str, str] = {}
    for s in sites:
        for u in (s[2], s[3]):
            h = _host(u)
            if h:
                hosts.setdefault(h, s[0])
    cross: Counter[tuple[str, str]] = Counter()
    for site_id, target in external:
        t = hosts.get(_host(target))
        if t and t != site_id:
            cross[(site_id, t)] += 1
    for sid, name, canonical, wp_url, mode, gsc_prop, ga4_prop in sites:
        nid = f"site:{sid}"
        wp_status = conns.get((sid, "wordpress"))
        st = "ok" if (wp_url and wp_status == "ok") else ("warn" if wp_url else "off")
        nodes.append({"id": nid, "kind": "site", "label": name or sid, "status": st,
                      "meta": {"site_id": sid, "url": canonical, "wp_url": wp_url, "mode": mode, "posts": posts.get(sid, 0), "wordpress": wp_status}})
        edges.append({"id": f"{BRAIN}->{nid}", "source": BRAIN, "target": nid, "kind": "wp", "label": "وردپرس", "status": st, "weight": 2 if st == "ok" else 1})
        for kind, prop, label in (("gsc", gsc_prop, "Search Console"), ("ga4", ga4_prop, "GA4")):
            cst = conns.get((sid, kind))
            status = "ok" if cst == "ok" else ("warn" if prop else "off")
            cid = f"{kind}:{sid}"
            nodes.append({"id": cid, "kind": kind, "label": label, "status": status, "meta": {"site_id": sid, "property": prop, "status": cst}})
            edges.append({"id": f"{nid}->{cid}", "source": nid, "target": cid, "kind": kind, "label": label, "status": status, "weight": 2 if status == "ok" else 1})
    for (a, b), n in sorted(cross.items()):
        edges.append({"id": f"site:{a}=>site:{b}", "source": f"site:{a}", "target": f"site:{b}", "kind": "backlink", "label": f"{n} لینک", "status": "ok", "weight": n})
    return {"nodes": nodes, "edges": edges,
            "counts": {"providers": sum(1 for n in nodes if n["kind"] == "provider"), "sites": len(sites), "cross_links": len(cross)}}
