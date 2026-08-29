"""Evidence-only Content Knowledge Pack derived from the persisted knowledge graph."""
from __future__ import annotations

import hashlib
import json
from typing import Any

from sqlalchemy import Engine, and_, func, select

from ..db.repositories.base import dumps, loads, utcnow
from ..db.tables import content_knowledge_packs, graph_edges, graph_nodes


class ContentKnowledgePackService:
    """Build immutable, evidence-linked context for content generation."""

    PAGE_TYPES = {"PAGE", "POST", "CONTENT"}
    ENTITY_TYPES = {"BRAND", "MODEL", "SERVICE", "LOCATION", "ENTITY"}

    def __init__(self, engine: Engine):
        self.engine = engine

    @staticmethod
    def _node(row) -> dict[str, Any]:
        value = dict(row._mapping)
        props = loads(value.get("props"), {})
        safe_props = {k: props[k] for k in ("title", "slug", "description", "intent", "taxonomy", "count", "position", "impressions", "clicks", "schema_type", "severity")
                      if props.get(k) not in (None, "", [], {})}
        return {"node_id": value["node_id"], "type": value["node_type"], "label": value["label"],
                "url": value.get("url"), "pagerank": round(float(value.get("pagerank") or 0), 6),
                "community": value.get("community"), "facts": safe_props}

    def build(self, site_id: str) -> dict[str, Any]:
        with self.engine.connect() as cx:
            rows = cx.execute(select(graph_nodes).where(graph_nodes.c.site_id == site_id)).all()
            edges = cx.execute(select(graph_edges.c.source_id, graph_edges.c.target_id, graph_edges.c.edge_type)
                               .where(graph_edges.c.site_id == site_id)).all()
        nodes = [self._node(r) for r in rows]
        by_type: dict[str, list[dict[str, Any]]] = {}
        for node in nodes:
            by_type.setdefault(node["type"], []).append(node)
        for values in by_type.values():
            values.sort(key=lambda x: (-x["pagerank"], x["label"], x["node_id"]))
        degree: dict[str, int] = {}
        for source, target, _kind in edges:
            degree[source] = degree.get(source, 0) + 1
            degree[target] = degree.get(target, 0) + 1
        pages = [n for n in nodes if n["type"] in self.PAGE_TYPES and n.get("url")]
        pages.sort(key=lambda n: (-degree.get(n["node_id"], 0), -n["pagerank"], n["label"]))
        entities = [n for node_type in self.ENTITY_TYPES for n in by_type.get(node_type, [])]
        entities.sort(key=lambda n: (-n["pagerank"], n["label"]))
        categories = by_type.get("CATEGORY", [])[:40]
        queries = by_type.get("QUERY", [])[:40]
        warnings: list[str] = []
        if not nodes:
            warnings.append("گراف سایت هنوز داده‌ای ندارد؛ ابتدا همگام‌سازی سایت را اجرا کنید.")
        if not pages:
            warnings.append("صفحه یا نوشته قابل استناد در گراف پیدا نشد.")
        if not queries:
            warnings.append("داده Query از Search Console در گراف موجود نیست.")
        if not categories:
            warnings.append("دسته‌بندی وردپرس در گراف موجود نیست.")
        counts = {k: len(v) for k, v in sorted(by_type.items())}
        return {
            "site_id": site_id, "source": "knowledge_graph",
            "source_policy": "هر ادعا باید به node_id یا URL موجود در این بسته متکی باشد؛ نبود داده مجوز حدس‌زدن نیست.",
            "summary": {"nodes": len(nodes), "edges": len(edges), "types": counts},
            "taxonomy": {"categories": categories, "entities": entities[:60], "schemas": by_type.get("SCHEMA", [])[:30]},
            "search_demand": {"queries": queries},
            "content_inventory": {"authoritative_pages": pages[:40]},
            "seo_signals": {"problems": by_type.get("SEO_PROBLEM", [])[:30], "opportunities": by_type.get("SEO_OPPORTUNITY", [])[:30]},
            "internal_link_targets": [{**n, "connections": degree.get(n["node_id"], 0)} for n in pages[:24]],
            "warnings": warnings,
        }

    @staticmethod
    def render(pack: dict[str, Any]) -> str:
        def lines(items: list[dict[str, Any]], limit: int = 20) -> str:
            if not items:
                return "- داده‌ای موجود نیست"
            result = []
            for item in items[:limit]:
                ref = item.get("url") or item.get("node_id")
                facts = item.get("facts") or {}
                suffix = "؛ ".join(f"{k}={v}" for k, v in facts.items())
                result.append(f"- {item.get('label')} [{item.get('type')} | {ref}]" + (f" — {suffix}" if suffix else ""))
            return "\n".join(result)

        taxonomy = pack.get("taxonomy") or {}
        demand = pack.get("search_demand") or {}
        inventory = pack.get("content_inventory") or {}
        seo = pack.get("seo_signals") or {}
        warnings = pack.get("warnings") or []
        return "\n\n".join([
            "## Content Knowledge Pack (استخراج خودکار از گراف)",
            "قانون منبع: فقط از شواهد زیر استفاده کن. اگر شواهد کافی نیست، کمبود داده را اعلام کن و چیزی نساز.",
            "### دسته‌بندی‌ها\n" + lines(taxonomy.get("categories") or [], 30),
            "### موجودیت‌ها و خدمات\n" + lines(taxonomy.get("entities") or [], 40),
            "### تقاضای جستجو\n" + lines(demand.get("queries") or [], 30),
            "### صفحات مرجع و مقصد لینک داخلی\n" + lines(inventory.get("authoritative_pages") or [], 30),
            "### مشکلات و فرصت‌های سئو\n" + lines((seo.get("problems") or []) + (seo.get("opportunities") or []), 30),
            "### کمبودهای داده\n" + ("\n".join(f"- {w}" for w in warnings) if warnings else "- موردی ثبت نشده"),
        ])

    def rebuild(self, site_id: str) -> dict[str, Any]:
        pack = self.build(site_id)
        canonical = json.dumps(pack, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:24]
        now = utcnow()
        with self.engine.begin() as cx:
            existing = cx.execute(select(content_knowledge_packs).where(and_(content_knowledge_packs.c.site_id == site_id,
                                                                             content_knowledge_packs.c.hash == digest))).first()
            if existing:
                return self._public(dict(existing._mapping))
            version = int(cx.execute(select(func.max(content_knowledge_packs.c.version)).where(content_knowledge_packs.c.site_id == site_id)).scalar() or 0) + 1
            pid = int(cx.execute(content_knowledge_packs.insert().values(site_id=site_id, version=version, hash=digest, status="ready", pack=dumps(pack),
                                                                         rendered=self.render(pack), source_counts=dumps(pack["summary"]), warnings=dumps(pack["warnings"]),
                                                                         created_at=now, updated_at=now)).inserted_primary_key[0])
            row = cx.execute(select(content_knowledge_packs).where(content_knowledge_packs.c.id == pid)).first()
        return self._public(dict(row._mapping))

    @staticmethod
    def _public(value: dict[str, Any], include_rendered: bool = True) -> dict[str, Any]:
        value["pack"] = loads(value.get("pack"), {})
        value["source_counts"] = loads(value.get("source_counts"), {})
        value["warnings"] = loads(value.get("warnings"), [])
        if not include_rendered:
            value.pop("rendered", None)
        return value

    def latest(self, site_id: str, rebuild_if_missing: bool = False) -> dict[str, Any] | None:
        with self.engine.connect() as cx:
            row = cx.execute(select(content_knowledge_packs).where(content_knowledge_packs.c.site_id == site_id)
                             .order_by(content_knowledge_packs.c.version.desc()).limit(1)).first()
        if row:
            return self._public(dict(row._mapping))
        return self.rebuild(site_id) if rebuild_if_missing else None

    def history(self, site_id: str, limit: int = 20) -> list[dict[str, Any]]:
        with self.engine.connect() as cx:
            rows = cx.execute(select(content_knowledge_packs).where(content_knowledge_packs.c.site_id == site_id)
                              .order_by(content_knowledge_packs.c.version.desc()).limit(max(1, min(limit, 100)))).all()
        return [self._public(dict(r._mapping), include_rendered=False) for r in rows]
