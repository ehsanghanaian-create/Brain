"""Build the knowledge graph (entities -> analysis -> graph tables -> Obsidian vault).

    python scripts/build-graph.py --limit-pages 15     # first validation graph (site + 10-20 pages)
    python scripts/build-graph.py                      # full graph
    python scripts/build-graph.py --skip-analysis      # reuse existing analysis results
"""
import _bootstrap  # noqa: F401
import argparse
import json

from src.analysis import extract_entities, run_analysis
from src.common.config import get_site, vault_path
from src.common.logging_setup import setup_logging
from src.database.db import db
from src.graph import GraphBuild, ObsidianWriter


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--site", default=None)
    ap.add_argument("--limit-pages", type=int, default=None)
    ap.add_argument("--skip-analysis", action="store_true")
    ap.add_argument("--no-obsidian", action="store_true")
    a = ap.parse_args()
    setup_logging("build-graph")
    site = get_site(a.site)
    out = {}
    with db() as conn:
        if not a.skip_analysis:
            out["entities"] = extract_entities(conn, site)
            out["analysis"] = run_analysis(conn, site)
        out["graph"] = GraphBuild(conn, site).build(limit_pages=a.limit_pages)
        if not a.no_obsidian:
            out["obsidian"] = ObsidianWriter(conn, site, vault_path()).write()
    print(json.dumps(out, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
