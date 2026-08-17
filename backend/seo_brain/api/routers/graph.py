"""Graph endpoints in the Neo4j-compatible shape (id/site_id/type/metadata; source/target/relation_type/weight/metadata).

Reads go through GraphStore. Analytics that still live in the v0.1 `graph.queries` module (FTS search,
shortest path, orphans, site summary) are exposed here too, so the frontend has one API from day one.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from ...database.db import connect
from ...graph import queries as Q
from ...graph.store import GraphStore
from ..deps import graph_store, require_site

router = APIRouter(prefix="/sites/{site_id}/graph", tags=["graph"], dependencies=[Depends(require_site)])


def _types(types: str | None) -> list[str] | None:
    return [t.strip().upper() for t in types.split(",") if t.strip()] if types else None


@router.get("/summary")
def summary(site_id: str, store: GraphStore = Depends(graph_store)) -> dict:
    counts = store.counts(site_id)
    conn = connect()
    try:
        legacy = Q.get_site_summary(conn, site_id)
    finally:
        conn.close()
    return {"site_id": site_id, **counts, "site": legacy}


@router.get("/nodes")
def nodes(site_id: str, types: str | None = Query(None, description="comma-separated node types"),
          limit: int = Query(200, le=2000), offset: int = 0, store: GraphStore = Depends(graph_store)) -> list[dict]:
    return [n.to_dict() for n in store.list_nodes(site_id, _types(types), limit, offset)]


@router.get("/search")
def search(site_id: str, q: str = Query(..., min_length=1), types: str | None = None, limit: int = Query(20, le=200),
           store: GraphStore = Depends(graph_store)) -> dict:
    conn = connect()
    try:
        t = _types(types)
        fts = Q.search_graph(conn, site_id, q, t[0] if t else None, limit)
    finally:
        conn.close()
    like = [n.to_dict() for n in store.search(site_id, q, _types(types), limit)]
    return {"q": q, "fts": fts, "nodes": like}


@router.get("/node/{node_id:path}")
def node(site_id: str, node_id: str, store: GraphStore = Depends(graph_store)) -> dict:
    n = store.get_node(site_id, node_id)
    if not n:
        raise HTTPException(404, f"node not found: {node_id}")
    return n.to_dict()


@router.get("/neighbors/{node_id:path}")
def neighbors(site_id: str, node_id: str, relation_types: str | None = None, direction: str = Query("both", pattern="^(in|out|both)$"),
              store: GraphStore = Depends(graph_store)) -> dict:
    if not store.get_node(site_id, node_id):
        raise HTTPException(404, f"node not found: {node_id}")
    return store.neighbors(site_id, node_id, _types(relation_types), direction).to_dict()


@router.get("/subgraph")
def subgraph(site_id: str, center: str = Query(...), hops: int = Query(1, ge=0, le=4), relation_types: str | None = None,
             max_nodes: int = Query(300, le=2000), store: GraphStore = Depends(graph_store)) -> dict:
    if not store.get_node(site_id, center):
        raise HTTPException(404, f"node not found: {center}")
    return store.subgraph(site_id, center, hops, _types(relation_types), max_nodes).to_dict()


@router.get("/path")
def path(site_id: str, source: str, target: str, relation_types: str | None = None, max_paths: int = Query(3, le=10),
         max_depth: int = Query(6, le=10)) -> dict:
    conn = connect()
    try:
        return Q.find_path(conn, site_id, source, target, _types(relation_types), max_paths, max_depth)
    finally:
        conn.close()


@router.get("/orphans")
def orphans(site_id: str, include_nav_only: bool = False, limit: int = Query(100, le=1000)) -> list[dict]:
    conn = connect()
    try:
        return Q.find_orphans(conn, site_id, include_nav_only, limit)
    finally:
        conn.close()
