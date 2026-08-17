"""SiteInitializer — wizard step 3.

  1. workspace   data/sites/<site_id>/{raw,exports,uploads,vault,logs} (+ README.md describing the layout)
  2. site memory an explicit row in site_memory (empty lists/objects) so the Brain has a place to write
  3. graph ns    the SITE node `site:<site_id>` in graph_nodes — every later node/edge hangs off it

Idempotent: re-running reports what already existed. Never deletes anything.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from sqlalchemy import Engine

from ..common.config import PROJECT_ROOT
from ..db.repositories.memory import SiteMemory, SiteMemoryRepository
from ..db.repositories.sites import Site
from ..graph.model import GraphNode
from ..graph.store import get_graph_store

WORKSPACE_SUBDIRS = ("raw", "exports", "uploads", "vault", "logs")


def slugify_domain(domain_or_url: str) -> str:
    host = urlparse(domain_or_url if "://" in domain_or_url else f"https://{domain_or_url}").hostname or domain_or_url
    host = host.lower().removeprefix("www.")
    slug = re.sub(r"[^a-z0-9]+", "-", host.rsplit(".", 1)[0] if host.count(".") >= 1 else host).strip("-")
    return slug[:63] or "site"


class SiteInitializer:
    def __init__(self, engine: Engine, root: Path | None = None):
        self.engine = engine
        self.root = root or PROJECT_ROOT

    def workspace_dir(self, site_id: str) -> Path:
        return self.root / "data" / "sites" / site_id

    def init_workspace(self, site: Site) -> dict[str, Any]:
        base = self.workspace_dir(site.site_id)
        created = []
        for sub in WORKSPACE_SUBDIRS:
            p = base / sub
            if not p.exists():
                p.mkdir(parents=True, exist_ok=True)
                created.append(sub)
        readme = base / "README.md"
        if not readme.exists():
            readme.write_text(
                f"# Workspace — {site.name} ({site.site_id})\n\n"
                f"canonical: {site.canonical_url}\n\n"
                "raw/      raw snapshots (WordPress JSON, crawl HTML, GSC/GA4 responses)\n"
                "exports/  reports, CSV/Markdown exports\n"
                "uploads/  files you import (keyword sheets, calendars)\n"
                "vault/    Obsidian notes generated for this site\n"
                "logs/     per-site run logs\n", encoding="utf-8")
            created.append("README.md")
        rel = str(base.relative_to(self.root)).replace("\\", "/") if base.is_relative_to(self.root) else str(base)
        return {"path": rel, "created": created, "existed": not created}

    def init_memory(self, site: Site) -> dict[str, Any]:
        repo = SiteMemoryRepository(self.engine)
        existing = repo.get(site.site_id)
        if existing.updated_at:
            return {"initialized": False, "existed": True, "updated_at": existing.updated_at}
        mem = SiteMemory(site_id=site.site_id, tone={"language": site.language or "fa-IR"})
        saved = repo.save(mem)
        return {"initialized": True, "existed": False, "updated_at": saved.updated_at}

    def init_graph_namespace(self, site: Site) -> dict[str, Any]:
        store = get_graph_store(self.engine)
        node_id = f"site:{site.site_id}"
        existed = store.get_node(site.site_id, node_id) is not None
        store.upsert_nodes([GraphNode(id=node_id, site_id=site.site_id, type="SITE",
                                      metadata={"label": site.name, "url": site.canonical_url,
                                                "props": {"language": site.language, "country": site.country, "mode": site.mode}})])
        counts = store.counts(site.site_id)
        return {"site_node": node_id, "existed": existed, "nodes": counts["nodes"], "edges": counts["edges"]}

    def initialize(self, site: Site) -> dict[str, Any]:
        return {"site_id": site.site_id, "workspace": self.init_workspace(site), "memory": self.init_memory(site),
                "graph": self.init_graph_namespace(site)}
