"""Phase 1.5 — live API validation. Exercises EVERY v1 endpoint against a running server and writes a report.

    python backend/cli/api.py --port 8000            (in another terminal)
    python backend/cli/validate-api.py --base http://127.0.0.1:8000 --out docs/seo-brain/03-phase1.5-api-validation.md

Creates a throw-away site `zz-validation-<hex>` (deleted at the end), never touches existing sites' data.
Exit code 0 = all checks passed.
"""
import _bootstrap  # noqa: F401
import argparse
import json
import os
import time
import uuid
from datetime import datetime, timezone

import httpx

CHECKS: list[dict] = []


def check(name: str, method: str, url: str, expect: int, cond=None, **kw) -> httpx.Response | None:
    t0 = time.perf_counter()
    try:
        r = httpx.request(method, url, timeout=60, **kw)
    except Exception as e:  # noqa: BLE001
        CHECKS.append({"name": name, "method": method, "url": url, "status": "EXC", "expect": expect, "ok": False, "ms": 0, "note": str(e)})
        return None
    ms = int((time.perf_counter() - t0) * 1000)
    ok = r.status_code == expect
    note = ""
    if ok and cond is not None:
        try:
            res = cond(r)
            if res is not True:
                ok, note = False, f"condition failed: {str(res)[:160]}"
        except Exception as e:  # noqa: BLE001
            ok, note = False, f"condition error: {e}"
    if not ok and not note:
        note = r.text[:200]
    CHECKS.append({"name": name, "method": method, "url": url.replace(BASE, ""), "status": r.status_code, "expect": expect,
                   "ok": ok, "ms": ms, "note": note})
    return r


def main() -> int:
    global BASE
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8000")
    ap.add_argument("--site", default="example-site", help="existing site with graph data (read-only checks)")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    BASE = a.base.rstrip("/")
    api = BASE + "/api/v1"
    H = {"X-API-Token": os.environ.get("API_TOKEN", "")} if os.environ.get("API_TOKEN") else {}
    sid = a.site
    tmp = f"zz-validation-{uuid.uuid4().hex[:6]}"

    # Validation must be deterministic and never spend real tokens: temporarily disable every enabled provider (Claude/OmniRoute/…)
    # so all AI paths fall back to Echo; the original enabled flags are restored at exit (also on exceptions). Real adapters are
    # covered by pytest fake transports; the dedicated phase-9 blocks below re-create throw-away providers and delete them.
    import atexit
    _paused: list[int] = []
    try:
        for p in httpx.get(api + "/ai/provider-configs", headers=H, timeout=30).json():
            if p.get("enabled"):
                httpx.patch(api + f"/ai/provider-configs/{p['id']}", headers=H, json={"enabled": False}, timeout=30); _paused.append(p["id"])
    except Exception:  # noqa: BLE001
        pass

    def _restore():
        for pid_ in _paused:
            try:
                httpx.patch(api + f"/ai/provider-configs/{pid_}", headers=H, json={"enabled": True}, timeout=30)
            except Exception:  # noqa: BLE001
                pass
    atexit.register(_restore)

    # ---- health / meta
    check("root", "GET", BASE + "/", 200, lambda r: r.json()["api"] == "/api/v1")
    check("openapi", "GET", BASE + "/api/openapi.json", 200, lambda r: len(r.json()["paths"]) >= 15 or f"paths={len(r.json()['paths'])}")
    check("docs", "GET", BASE + "/api/docs", 200)
    check("health", "GET", api + "/health", 200, lambda r: r.json()["migrations"]["pending"] == [])
    check("request-id header", "GET", api + "/health", 200, lambda r: bool(r.headers.get("X-Request-ID")))
    check("request-id echoed", "GET", api + "/health", 200, lambda r: r.headers.get("X-Request-ID") == "abc123", headers={"X-Request-ID": "abc123"})

    # ---- error envelope
    check("404 envelope", "GET", api + "/sites/nope-nope", 404, lambda r: r.json()["error"]["code"] == "not_found" and "request_id" in r.json()["error"], headers=H)
    check("422 envelope", "POST", api + "/sites", 422, lambda r: r.json()["error"]["code"] == "validation_error" and isinstance(r.json()["error"]["details"], list), headers=H, json={"site_id": "BAD SLUG", "name": "x", "canonical_url": "nope"})

    # ---- sites CRUD (temporary site)
    check("sites list", "GET", api + "/sites", 200, lambda r: any(s["site_id"] == sid for s in r.json()), headers=H)
    check("site get", "GET", api + f"/sites/{sid}", 200, lambda r: r.json()["site_id"] == sid and r.json()["mode"] in ("manual", "assisted", "autopilot"), headers=H)
    check("site create", "POST", api + "/sites", 201, lambda r: r.json()["site_id"] == tmp and r.json()["mode"] == "manual" and r.json()["workspace_path"] == f"data/sites/{tmp}", headers=H,
          json={"site_id": tmp, "name": "Validation", "canonical_url": "https://validation.example/", "business_type": "test", "language": "fa-IR", "country": "IR"})
    check("site create duplicate → 409", "POST", api + "/sites", 409, lambda r: r.json()["error"]["code"] == "conflict", headers=H,
          json={"site_id": tmp, "name": "Validation", "canonical_url": "https://validation.example/"})
    check("site patch mode", "PATCH", api + f"/sites/{tmp}", 200, lambda r: r.json()["mode"] == "assisted" and r.json()["country"] == "IR", headers=H, json={"mode": "assisted"})
    check("site patch invalid mode → 422", "PATCH", api + f"/sites/{tmp}", 422, headers=H, json={"mode": "yolo"})

    # ---- graph (read-only on the real site)
    check("graph summary", "GET", api + f"/sites/{sid}/graph/summary", 200, lambda r: r.json()["nodes"] > 0 and r.json()["edges"] > 0 and "by_node_type" in r.json(), headers=H)
    r = check("graph nodes (types=PAGE,POST)", "GET", api + f"/sites/{sid}/graph/nodes?types=PAGE,POST&limit=5", 200,
              lambda r: len(r.json()) > 0 and set(r.json()[0]) == {"id", "site_id", "type", "metadata"}, headers=H)
    node_id = r.json()[0]["id"] if r is not None and r.status_code == 200 and r.json() else f"site:{sid}"
    check("graph node", "GET", api + f"/sites/{sid}/graph/node/{node_id}", 200, lambda r: r.json()["id"] == node_id, headers=H)
    check("graph node 404", "GET", api + f"/sites/{sid}/graph/node/nope:x", 404, lambda r: r.json()["error"]["code"] == "not_found", headers=H)
    check("graph neighbors", "GET", api + f"/sites/{sid}/graph/neighbors/{node_id}", 200, lambda r: len(r.json()["edges"]) > 0 and set(r.json()["edges"][0]) == {"source", "target", "relation_type", "weight", "metadata", "site_id"}, headers=H)
    check("graph neighbors filtered", "GET", api + f"/sites/{sid}/graph/neighbors/{node_id}?relation_types=LINKS_TO&direction=out", 200, lambda r: all(e["relation_type"] == "LINKS_TO" for e in r.json()["edges"]), headers=H)
    check("graph subgraph hops=2", "GET", api + f"/sites/{sid}/graph/subgraph?center=site:{sid}&hops=2&max_nodes=100", 200, lambda r: 0 < len(r.json()["nodes"]) <= 100 and r.json()["hops"] == 2, headers=H)
    check("graph subgraph bad hops → 422", "GET", api + f"/sites/{sid}/graph/subgraph?center=site:{sid}&hops=9", 422, headers=H)
    check("graph search", "GET", api + f"/sites/{sid}/graph/search?q=امداد", 200, lambda r: "fts" in r.json() and "nodes" in r.json() and bool(r.json()["fts"] or r.json()["nodes"]), headers=H)
    check("graph path", "GET", api + f"/sites/{sid}/graph/path?source=site:{sid}&target={node_id}", 200, lambda r: isinstance(r.json(), dict), headers=H)
    check("graph orphans", "GET", api + f"/sites/{sid}/graph/orphans", 200, lambda r: isinstance(r.json(), list), headers=H)
    check("graph on unknown site → 404", "GET", api + "/sites/nope-nope/graph/summary", 404, headers=H)

    # ---- phase 4: graph modes / view / node details (real site, read-only)
    check("graph modes", "GET", api + f"/sites/{sid}/graph/modes", 200, lambda r: [m["key"] for m in r.json()] == ["seo", "content", "links", "planner"], headers=H)
    check("graph view seo", "GET", api + f"/sites/{sid}/graph/view?mode=seo", 200, lambda r: len(r.json()["nodes"]) > 0 and len(r.json()["edges"]) > 0 and r.json()["mode"]["key"] == "seo", headers=H)
    check("graph view links (no isolated)", "GET", api + f"/sites/{sid}/graph/view?mode=links&include_isolated=false", 200, lambda r: all(e["relation_type"] in ("LINKS_TO", "SUGGESTED_LINK", "LINK_OPPORTUNITY", "SUPPORTS") for e in r.json()["edges"]), headers=H)
    check("graph view content types filter", "GET", api + f"/sites/{sid}/graph/view?mode=content&types=SCHEMA,PAGE", 200, lambda r: set(n["type"] for n in r.json()["nodes"]) <= {"SCHEMA", "PAGE"}, headers=H)
    check("graph view bad mode → 422", "GET", api + f"/sites/{sid}/graph/view?mode=nope", 422, headers=H)
    check("node details (page)", "GET", api + f"/sites/{sid}/graph/node-details/{node_id}", 200, lambda r: r.json()["type"] in ("PAGE", "POST") and "page" in r.json() and "content_status" in r.json()["page"], headers=H)
    check("node details 404", "GET", api + f"/sites/{sid}/graph/node-details/nope:x", 404, headers=H)

    # ---- memory (temporary site only)
    check("memory get (empty)", "GET", api + f"/sites/{tmp}/memory", 200, lambda r: r.json()["business_rules"] == [] and r.json()["tone"] == {}, headers=H)
    check("memory put", "PUT", api + f"/sites/{tmp}/memory", 200, lambda r: r.json()["business_rules"] == ["فقط تهران"] and r.json()["tone"]["voice"] == "formal" and bool(r.json()["updated_at"]), headers=H,
          json={"business_rules": ["فقط تهران"], "tone": {"voice": "formal"}, "content_rules": ["H1 یکتا"]})
    check("memory context", "GET", api + f"/sites/{tmp}/memory/context", 200, lambda r: r.json()["messages"][0]["role"] == "system" and "فقط تهران" in r.json()["messages"][0]["content"], headers=H)
    check("memory get (real site, read-only)", "GET", api + f"/sites/{sid}/memory", 200, lambda r: r.json()["site_id"] == sid, headers=H)

    # ---- AI orchestrator
    check("ai routes", "GET", api + "/ai/routes", 200, lambda r: "echo" in r.json()["providers"] and "content_writing" in r.json()["routes"], headers=H)
    check("ai providers", "GET", api + "/ai/providers", 200, lambda r: r.json()[0]["test"]["ok"] is True, headers=H)
    check("ai run text", "POST", api + f"/ai/sites/{tmp}/run", 200, lambda r: r.json()["ok"] and r.json()["memory_used"] and r.json()["response"]["provider"] == "echo", headers=H,
          json={"kind": "content_writing", "prompt": "یک پاراگراف درباره امداد خودرو"})
    check("ai run json + learn", "POST", api + f"/ai/sites/{tmp}/run", 200, lambda r: r.json()["response"]["parsed"] == {"seo_title": "echo:seo_title", "h1": "echo:h1"}, headers=H,
          json={"kind": "brief", "prompt": "brief", "json_keys": ["seo_title", "h1"], "learn_pattern": "brief-json-ok", "learn_evidence": "validation"})
    check("memory learned pattern", "GET", api + f"/sites/{tmp}/memory", 200, lambda r: r.json()["successful_patterns"][-1]["pattern"] == "brief-json-ok", headers=H)
    check("ai run unknown kind → 422", "POST", api + f"/ai/sites/{tmp}/run", 422, lambda r: r.json()["error"]["code"] == "validation_error", headers=H, json={"kind": "nope", "prompt": "x"})

    # ---- jobs
    r = check("job enqueue noop", "POST", api + "/jobs", 202, lambda r: r.json()["status"] in ("queued", "running", "succeeded"), headers=H, json={"type": "noop", "payload": {"site_id": tmp, "k": 1}})
    run_id = r.json()["run_id"] if r is not None and r.status_code == 202 else "none"
    for _ in range(50):
        st = httpx.get(api + f"/jobs/{run_id}", headers=H).json()
        if st.get("status") in ("succeeded", "failed"):
            break
        time.sleep(0.05)
    check("job run finished", "GET", api + f"/jobs/{run_id}", 200, lambda r: r.json()["status"] == "succeeded" and r.json()["result"] == {"echo": {"site_id": tmp, "k": 1}}, headers=H)
    check("jobs list", "GET", api + "/jobs", 200, lambda r: any(j["run_id"] == run_id for j in r.json()), headers=H)
    check("job unknown type → 422", "POST", api + "/jobs", 422, headers=H, json={"type": "does-not-exist"})
    check("job unknown run → 404", "GET", api + "/jobs/none", 404, headers=H)

    # ---- phase 3: connections + initialize + site brain
    check("connections status (empty)", "GET", api + f"/sites/{tmp}/connections", 200, lambda r: r.json()["status"] == {} and "configured" in r.json(), headers=H)
    check("gsc test without property → not_configured", "POST", api + f"/sites/{tmp}/connections/gsc/test", 200, lambda r: r.json()["status"] == "not_configured" and r.json()["ok"] is False, headers=H, json={})
    check("ga4 test bad id → not_configured", "POST", api + f"/sites/{tmp}/connections/ga4/test", 200, lambda r: r.json()["status"] == "not_configured", headers=H, json={"property": "abc"})
    check("wordpress test (real site, read-only)", "POST", api + f"/sites/{tmp}/connections/wordpress/test", 200, lambda r: r.json()["status"] in ("ok", "error", "not_found"), headers=H, json={"property": "https://example.com"})
    check("connections status (3 kinds)", "GET", api + f"/sites/{tmp}/connections", 200, lambda r: set(r.json()["status"]) == {"gsc", "ga4", "wordpress"}, headers=H)
    check("gsc properties listing", "GET", api + "/connections/gsc/properties", 200, lambda r: r.json()["status"] in ("ok", "not_configured", "not_authorized", "error"), headers=H)
    check("unknown connection kind → 404", "POST", api + f"/sites/{tmp}/connections/nope/test", 404, headers=H, json={})
    check("initialize", "POST", api + f"/sites/{tmp}/initialize", 200, lambda r: r.json()["graph"]["site_node"] == f"site:{tmp}" and r.json()["memory"]["existed"] is True, headers=H)
    check("initialize idempotent", "POST", api + f"/sites/{tmp}/initialize", 200, lambda r: r.json()["graph"]["existed"] is True, headers=H)
    check("site brain put (audience/cta/forbidden)", "PUT", api + f"/sites/{tmp}/memory", 200, lambda r: r.json()["forbidden_claims"] == ["ارزان‌ترین"] and r.json()["audience"]["segments"] == ["مالکان MVM"], headers=H,
          json={"audience": {"segments": ["مالکان MVM"], "pains": [], "intent_notes": ""}, "cta_rules": ["تماس در پاراگراف اول"], "forbidden_claims": ["ارزان‌ترین"]})
    check("site brain in AI context", "GET", api + f"/sites/{tmp}/memory/context", 200, lambda r: "NEVER claim" in r.json()["messages"][0]["content"], headers=H)

    # ---- phase 5: keywords (temporary site)
    kcsv = "کلمه کلیدی,اینتنت,حجم,اولویت,صفحه هدف\nتست کلمه یک,تراکنشی,100,بالا,https://validation.example/a\nتست کلمه دو,,50,,\n"
    check("keywords import dry-run", "POST", api + f"/sites/{tmp}/keywords/import", 200, lambda r: r.json()["dry_run"] and r.json()["rows_valid"] == 2 and r.json()["mapping"]["کلمه کلیدی"] == "keyword",
          headers=H, files={"file": ("k.csv", kcsv.encode("utf-8"), "text/csv")}, data={"dry_run": "true"})
    check("keywords import commit", "POST", api + f"/sites/{tmp}/keywords/import", 200, lambda r: r.json()["rows_imported"] == 2 and r.json()["import_id"] is not None,
          headers=H, files={"file": ("k.csv", kcsv.encode("utf-8"), "text/csv")}, data={"dry_run": "false"})
    check("keywords list", "GET", api + f"/sites/{tmp}/keywords", 200, lambda r: r.json()["total"] == 2 and "gsc" in r.json()["items"][0] and r.json()["counts"]["total"] == 2, headers=H)
    r = check("keyword create", "POST", api + f"/sites/{tmp}/keywords", 201, lambda r: r.json()["keyword"] == "تست کلمه سه", headers=H, json={"keyword": "تست کلمه سه", "intent": "local"})
    kid = r.json()["id"] if r is not None and r.status_code == 201 else 0
    check("keyword create duplicate → 409", "POST", api + f"/sites/{tmp}/keywords", 409, headers=H, json={"keyword": "تست  کلمه سه"})
    check("keyword patch", "PATCH", api + f"/sites/{tmp}/keywords/{kid}", 200, lambda r: r.json()["status"] == "planned", headers=H, json={"status": "planned"})
    check("keyword detail", "GET", api + f"/sites/{tmp}/keywords/{kid}", 200, lambda r: "gsc_pages" in r.json() and "opportunities" in r.json(), headers=H)
    check("keywords cluster", "POST", api + f"/sites/{tmp}/keywords/cluster", 200, lambda r: r.json()["clusters"] >= 1 and "graph" in r.json(), headers=H)
    check("keywords topic-map", "GET", api + f"/sites/{tmp}/keywords/topic-map", 200, lambda r: sum(c["keywords_count"] for c in r.json()["clusters"]) == 3, headers=H)
    check("keywords analyze", "POST", api + f"/sites/{tmp}/keywords/analyze", 200, lambda r: r.json()["keywords"] == 3 and r.json()["by_kind"].get("create_content", 0) >= 1, headers=H)
    check("keyword opportunities", "GET", api + f"/sites/{tmp}/keywords/opportunities", 200, lambda r: r.json()["total"] >= 1 and bool(r.json()["items"][0]["kind_fa"]), headers=H)
    check("keywords in graph view", "GET", api + f"/sites/{tmp}/graph/view?mode=seo&types=KEYWORD,TOPIC", 200, lambda r: r.json()["stats"]["by_type"].get("KEYWORD") == 3, headers=H)
    check("keyword delete", "DELETE", api + f"/sites/{tmp}/keywords/{kid}", 200, lambda r: r.json()["deleted"] == kid, headers=H)
    check("keywords meta", "GET", api + f"/sites/{tmp}/keywords/meta", 200, lambda r: len(r.json()["opportunity_kinds"]) == 4, headers=H)


    # ---- phase 6: content brain + ai providers (temporary site)
    r = check("content create", "POST", api + f"/sites/{tmp}/content", 201, lambda r: r.json()["status"] == "planned" and r.json()["allowed_transitions"] == ["brief_ready"], headers=H,
              json={"title": "محتوای آزمایشی", "target_keyword": "تست کلمه یک", "priority": "high", "publish_date": "2026-09-05"})
    cid = r.json()["id"] if r is not None and r.status_code == 201 else 0
    check("content transition skip → 409", "POST", api + f"/sites/{tmp}/content/{cid}/transition", 409, lambda r: r.json()["error"]["code"] == "invalid_transition", headers=H, json={"status": "writing"})
    check("content brief", "POST", api + f"/sites/{tmp}/content/{cid}/brief", 200, lambda r: r.json()["version"] == 1 and bool(r.json()["h1"]) and bool(r.json()["markdown"]), headers=H, json={"use_ai": True})
    check("content status brief_ready", "GET", api + f"/sites/{tmp}/content/{cid}", 200, lambda r: r.json()["status"] == "brief_ready" and r.json()["brief"]["version"] == 1, headers=H)
    check("content transition writing", "POST", api + f"/sites/{tmp}/content/{cid}/transition", 200, lambda r: r.json()["status"] == "writing", headers=H, json={"status": "writing"})
    check("content board", "GET", api + f"/sites/{tmp}/content/board", 200, lambda r: [c["status"] for c in r.json()["columns"]] == ["planned", "brief_ready", "writing", "review", "approved", "published"], headers=H)
    check("content calendar", "GET", api + f"/sites/{tmp}/content/calendar?from=2026-09-01&to=2026-09-30", 200, lambda r: len(r.json()["days"].get("2026-09-05", [])) == 1, headers=H)
    check("content sync graph", "POST", api + f"/sites/{tmp}/content/sync-graph", 200, lambda r: r.json()["nodes"] == 1, headers=H)
    check("content meta", "GET", api + f"/sites/{tmp}/content/meta", 200, lambda r: len(r.json()["statuses"]) == 6, headers=H)
    # ---- phase 7: drafts / score / review / gate / analytics / insights (temporary site, content created above)
    md7 = "# تست کلمه یک — راهنما\n\nپاراگراف اول درباره تست کلمه یک با شماره ۰۹۱۲۰۰۰۰۰۰۰.\n\n## بخش اول\nمتن بخش اول درباره تست کلمه یک.\n\n## سؤالات متداول\n### چرا؟\nچون.\n"
    r = check("draft create v1", "POST", api + f"/sites/{tmp}/content/{cid}/drafts", 201, lambda r: r.json()["version"] == 1 and r.json()["word_count"] > 0 and r.json()["structure"]["faq"] is True, headers=H, json={"body": md7, "format": "markdown", "author": "validator"})
    check("draft create v2 keeps v1", "POST", api + f"/sites/{tmp}/content/{cid}/drafts", 201, lambda r: r.json()["version"] == 2 and r.json()["revision_of"] is not None, headers=H, json={"body": md7 + "\n## بخش دوم\nمتن.\n", "source": "ai:test", "provenance": {"provider": "test"}})
    check("drafts list", "GET", api + f"/sites/{tmp}/content/{cid}/drafts", 200, lambda r: [d["version"] for d in r.json()] == [2, 1] and "body" not in r.json()[0], headers=H)
    check("score", "POST", api + f"/sites/{tmp}/content/{cid}/score", 200, lambda r: 0 <= r.json()["total"] <= 100 and set(r.json()["dims"]) == {"intent", "keywords", "entities", "headings", "links", "cta", "completeness"}, headers=H)
    check("review (rules, advisory ai)", "POST", api + f"/sites/{tmp}/content/{cid}/review", 200, lambda r: r.json()["review_status"] in ("ready", "changes_requested") and "counts" in r.json() and r.json()["gate"] == "strict", headers=H, json={"use_ai": True})
    check("intelligence history", "GET", api + f"/sites/{tmp}/content/{cid}/intelligence", 200, lambda r: len(r.json()["drafts"]) == 2 and len(r.json()["reviews"]) >= 1, headers=H)
    check("scoring settings get", "GET", api + f"/sites/{tmp}/content/settings/scoring", 200, lambda r: r.json()["review_gate"] == "strict" and r.json()["weights"]["intent"] == 20, headers=H)
    check("scoring settings put", "PUT", api + f"/sites/{tmp}/content/settings/scoring", 200, lambda r: r.json()["review_gate"] == "advisory", headers=H, json={"review_gate": "advisory"})
    check("analytics settings", "GET", api + f"/sites/{tmp}/content/analytics/settings", 200, lambda r: r.json()["min_impressions"] == 1000 and r.json()["min_clicks"] == 30 and r.json()["min_age_days"] == 28, headers=H)
    check("analytics snapshot (no urls)", "POST", api + f"/sites/{tmp}/content/analytics/snapshot", 200, lambda r: r.json()["snapshots"] == 0, headers=H)
    check("analytics learn (no samples)", "POST", api + f"/sites/{tmp}/content/analytics/learn", 200, lambda r: r.json()["samples"] == 0 and r.json()["insights"] == [], headers=H)
    check("analytics overview", "GET", api + f"/sites/{tmp}/content/analytics/overview", 200, lambda r: r.json()["totals"]["contents"] == 0, headers=H)
    check("insights list", "GET", api + f"/sites/{tmp}/content/insights", 200, lambda r: r.json() == [], headers=H)

    check("content delete", "DELETE", api + f"/sites/{tmp}/content/{cid}", 200, lambda r: r.json()["deleted"] == cid, headers=H)
    check("ai provider kinds", "GET", api + "/ai/provider-kinds", 200, lambda r: {k["kind"] for k in r.json()} >= {"anthropic", "openai", "google", "ollama"}, headers=H)
    r = check("ai provider create", "POST", api + "/ai/provider-configs", 201, lambda r: r.json()["has_key"] and r.json()["key_hint"] == "9999" and "api_key" not in r.json(), headers=H,
              json={"name": "zz-validation-provider", "kind": "ollama", "api_key": "test-key-9999"})
    pid = r.json()["id"] if r is not None and r.status_code == 201 else 0
    check("ai task routes", "GET", api + "/ai/task-routes", 200, lambda r: len(r.json()["routes"]) == 17, headers=H)
    check("ai route set", "PUT", api + "/ai/task-routes/brief", 200, lambda r: r.json()["provider_name"] == "zz-validation-provider", headers=H, json={"provider_id": pid, "model": "llama3"})
    check("ai route reset", "PUT", api + "/ai/task-routes/brief", 200, lambda r: r.json()["provider_id"] is None, headers=H, json={})
    check("ai provider delete", "DELETE", api + f"/ai/provider-configs/{pid}", 200, lambda r: r.json()["deleted"] == pid, headers=H)
    # ---- phase 9 (Claude): catalog + setup metadata + recommended routes (read-only preview) + no secret leakage — a temporary key-less provider
    check("claude provider kind setup", "GET", api + "/ai/provider-kinds", 200, lambda r: next(k for k in r.json() if k["kind"] == "anthropic")["setup"]["console_url"].startswith("https://platform.claude.com") and "claude-sonnet-5" in next(k for k in r.json() if k["kind"] == "anthropic")["models"], headers=H)
    r = check("claude provider create (no key)", "POST", api + "/ai/provider-configs", 201, lambda r: r.json()["has_key"] is False and r.json()["default_model"] == "claude-sonnet-5" and "secret_ref" not in r.json(), headers=H,
              json={"name": "zz-validation-claude", "kind": "anthropic"})
    cpid = r.json()["id"] if r is not None and r.status_code == 201 else 0
    check("claude catalog seeded", "GET", api + f"/ai/models?provider_id={cpid}", 200, lambda r: {m["model_id"]: m["tier"] for m in r.json()}.items() >= {"claude-sonnet-5": "balanced", "claude-opus-5": "quality", "claude-haiku-4-5": "fast"}.items(), headers=H)
    check("claude test without key → not_configured", "POST", api + f"/ai/provider-configs/{cpid}/test", 200, lambda r: r.json()["ok"] is False and r.json()["status"] == "not_configured", headers=H)
    check("claude recommended routes (preview)", "GET", api + f"/ai/provider-configs/{cpid}/recommended-routes", 200, lambda r: next(x for x in r.json()["routes"] if x["task_kind"] == "article_long")["model"] == "claude-sonnet-5" and next(x for x in r.json()["routes"] if x["task_kind"] == "faq")["model"] == "claude-haiku-4-5", headers=H)
    check("claude provider delete (cascades catalog)", "DELETE", api + f"/ai/provider-configs/{cpid}", 200, lambda r: r.json()["deleted"] == cpid, headers=H)
    # ---- phase 9 (OmniRoute external gateway): keyless kind counts as configured, auto models seeded, gateway-status read-only (no OmniRoute process needed)
    r = check("omniroute provider create (keyless gateway)", "POST", api + "/ai/provider-configs", 201, lambda r: r.json()["configured"] is True and r.json()["is_gateway"] is True and r.json()["route_kind"] == "gateway" and r.json()["default_model"] == "auto" and r.json()["endpoint_url"].endswith(":20128/v1"), headers=H,
              json={"name": "zz-validation-omniroute", "kind": "omniroute"})
    opid = r.json()["id"] if r is not None and r.status_code == 201 else 0
    check("omniroute catalog (auto models)", "GET", api + f"/ai/models?provider_id={opid}", 200, lambda r: {"auto", "auto/fast", "auto/cheap", "auto/coding"} <= {m["model_id"] for m in r.json()}, headers=H)
    check("omniroute gateway-status", "GET", api + f"/ai/provider-configs/{opid}/gateway-status", 200, lambda r: r.json()["is_gateway"] and r.json()["capabilities"].get("gateway") is True and r.json()["routing"]["auto_models"][0] == "auto" and "fallback_for" in r.json()["fallback"], headers=H)
    check("omniroute recommended routes (auto / auto-fast)", "GET", api + f"/ai/provider-configs/{opid}/recommended-routes", 200, lambda r: next(x for x in r.json()["routes"] if x["task_kind"] == "article_long")["model"] == "auto" and next(x for x in r.json()["routes"] if x["task_kind"] == "faq")["model"] == "auto/fast", headers=H)
    check("omniroute provider delete", "DELETE", api + f"/ai/provider-configs/{opid}", 200, lambda r: r.json()["deleted"] == opid, headers=H)

    # ---- phase 8: internal linking (real site read-only analyze is heavy → run on the temporary site; plus read checks on real site)
    check("links meta", "GET", api + f"/sites/{sid}/links/meta", 200, lambda r: len(r.json()["confidence"]) == 3 and r.json()["future_scopes"] == ["external", "backlink", "competitor"], headers=H)
    check("links analyze (tmp site, sync)", "POST", api + f"/sites/{tmp}/links/analyze", 200, lambda r: r.json()["mode"] == "sync" and "suggestions" in r.json(), headers=H)
    check("links summary (real site)", "GET", api + f"/sites/{sid}/links/summary", 200, lambda r: "by_status" in r.json() and "flags" in r.json(), headers=H)
    check("links suggestions (real site)", "GET", api + f"/sites/{sid}/links/suggestions?limit=5", 200, lambda r: all(0.45 <= i["score"] <= 1 and i["confidence"] in ("low", "recommended", "high") and i["reason_fa"] for i in r.json()["items"] if i["kind"] != "anchor_fix"), headers=H)
    check("links pages (real site)", "GET", api + f"/sites/{sid}/links/pages?limit=5", 200, lambda r: all(0 <= p["health_score"] <= 100 for p in r.json()["items"]), headers=H)
    check("links patterns", "GET", api + f"/sites/{tmp}/links/patterns", 200, lambda r: isinstance(r.json(), list), headers=H)
    check("links settings", "GET", api + f"/sites/{tmp}/links/settings", 200, lambda r: r.json()["min_score"] == 0.45 and r.json()["max_per_target"] == 5 and r.json()["max_per_source"] == 3, headers=H)
    check("links export csv", "GET", api + f"/sites/{tmp}/links/export.csv", 200, lambda r: "text/csv" in r.headers["content-type"], headers=H)

    # ---- phase 9: AI gateway / prompts / generation (echo — no external calls; writes only on the tmp site)
    check("ai task kinds (17)", "GET", api + "/ai/task-kinds", 200, lambda r: len(r.json()) == 17 and all(k["fa"] and "policy" in k for k in r.json()), headers=H)
    check("ai models catalog", "GET", api + "/ai/models", 200, lambda r: isinstance(r.json(), list), headers=H)
    check("ai health", "GET", api + "/ai/health", 200, lambda r: "providers" in r.json(), headers=H)
    check("ai budget default 20 + thresholds", "GET", api + f"/ai/budget?site_id={tmp}", 200, lambda r: r.json()["limit_usd"] == 20.0 and r.json()["thresholds"] == {"warning": 0.8, "soft_limit": 1.0, "hard_stop": 1.2} and r.json()["state"] == "ok", headers=H)
    check("ai budget set (human)", "PUT", api + f"/ai/budget?site_id={tmp}", 200, lambda r: r.json()["limit_usd"] == 7.5, headers=H, json={"budget_usd_month": 7.5})
    check("ai budget set invalid → 422", "PUT", api + f"/ai/budget?site_id={tmp}", 422, headers=H, json={"budget_usd_month": 0})
    check("ai usage", "GET", api + f"/ai/usage?site_id={tmp}&group_by=model", 200, lambda r: "rows" in r.json() and "budget" in r.json(), headers=H)
    check("ai routing preview (echo w/o provider)", "GET", api + f"/ai/routing/preview?task_kind=article_section&site_id={tmp}", 200, lambda r: r.json()["policy"] in ("echo", "auto", "explicit") and bool(r.json()["reason"]) and len(r.json()["chain"]) >= 1, headers=H)
    check("ai routing preview unknown kind → 422", "GET", api + "/ai/routing/preview?task_kind=nope", 422, headers=H)
    check("ai route policy+fallbacks (additive)", "PUT", api + "/ai/task-routes/outline", 200, lambda r: r.json()["policy"] == "auto" and r.json()["fallbacks"] == [], headers=H, json={"policy": "auto", "fallbacks": []})
    pr = check("ai prompts seeded (11, all with memory_pack)", "GET", api + "/ai/prompts", 200, lambda r: len(r.json()) >= 11 and all(any(v["is_active"] for v in p["versions"]) for p in r.json()), headers=H)
    wid = next((p for p in (pr.json() if pr is not None else []) if p["key"] == "agent.writer_section"), None)
    if wid:
        vid = next(v["id"] for v in wid["versions"] if v["is_active"])
        check("ai prompt get + performance", "GET", api + f"/ai/prompts/{wid['id']}", 200, lambda r: "performance" in r.json() and r.json()["key"] == "agent.writer_section", headers=H)
        check("ai prompt preview (memory injected)", "POST", api + f"/ai/prompts/versions/{vid}/preview", 200, lambda r: "حافظه سایت" in r.json()["rendered"] and r.json()["memory_snapshot_id"] > 0, headers=H, json={"site_id": tmp})
        check("ai prompt new version w/o memory_pack → 422", "POST", api + f"/ai/prompts/{wid['id']}/versions", 422, headers=H, json={"template": "بدون حافظه"})
        nv = check("ai prompt new version (inactive)", "POST", api + f"/ai/prompts/{wid['id']}/versions", 201, lambda r: not r.json()["is_active"] and r.json()["approval"] == "draft", headers=H, json={"template": "{{memory_pack}}\nنسخه تست {{h2}}", "changelog": "validation"})
        if nv is not None:
            check("ai prompt version approve (human)", "PATCH", api + f"/ai/prompts/versions/{nv.json()['id']}", 200, lambda r: r.json()["approval"] == "approved", headers=H, json={"approval": "approved", "approved_by": "validation"})
    check("ai feedback tags (6)", "GET", api + "/ai/feedback-tags", 200, lambda r: [t["tag"] for t in r.json()] == ["good_structure", "weak_intro", "wrong_intent", "too_generic", "excellent_entities", "good_links"], headers=H)
    check("gen meta (7 agents, autopilot reserved)", "GET", api + f"/sites/{tmp}/generation/meta", 200, lambda r: len(r.json()["agents"]) == 7 and "autopilot" in r.json()["reserved_modes"] and "autopilot" not in r.json()["modes"], headers=H)
    check("gen memory preview", "GET", api + f"/sites/{tmp}/generation/memory-preview", 200, lambda r: r.json()["id"] > 0 and "حافظه سایت" in r.json()["rendered"], headers=H)
    r9 = check("content create for generation", "POST", api + f"/sites/{tmp}/content", 201, lambda r: r.json()["status"] == "planned", headers=H, json={"title": "امداد خودرو تست تولید"})
    cid = r9.json()["id"] if r9 is not None and r9.status_code == 201 else 0
    if cid:
        check("content brief for generation", "POST", api + f"/sites/{tmp}/content/{cid}/brief", 200, lambda r: bool(r.json()["h1"]), headers=H, json={"use_ai": True, "mark_ready": True})
        check("gen estimate", "POST", api + f"/sites/{tmp}/content/{cid}/generate/estimate", 200, lambda r: r.json()["total"]["input_tokens"] > 0 and r.json()["sections"] >= 1 and r.json()["memory_snapshot_id"] > 0, headers=H, json={})
        check("gen start invalid mode (autopilot) → 422", "POST", api + f"/sites/{tmp}/content/{cid}/generate", 422, headers=H, json={"mode": "autopilot"})
        # validation never spends real tokens: pin every agent to Echo (explicit override) — real providers/gateways are exercised by pytest fake transports
        echo_models = {a: {"provider": "echo", "model": "echo-1"} for a in ("research", "outline", "writer", "fact_check", "seo", "linking", "reviewer")}
        gr = check("gen start (manual, 202, echo-pinned)", "POST", api + f"/sites/{tmp}/content/{cid}/generate", 202, lambda r: r.json()["run_id"].startswith("gen-") and r.json()["mode"] == "manual", headers=H, json={"mode": "manual", "models": echo_models})
        if gr is not None and gr.status_code == 202:
            rid = gr.json()["run_id"]
            for _ in range(40):
                st = httpx.get(api + f"/sites/{tmp}/generation/runs/{rid}", headers=H, timeout=30).json()
                if st["status"] in ("succeeded", "failed", "cancelled"):
                    break
                time.sleep(0.5)
            check("gen run detail (provenance)", "GET", api + f"/sites/{tmp}/generation/runs/{rid}", 200, lambda r: r.json()["status"] == "succeeded" and r.json()["memory_snapshot_id"] and r.json()["prompt_versions"] and r.json()["models"]["writer"]["model"] and len(r.json()["artifacts"]) >= 5, headers=H)
            check("gen run stream (SSE)", "GET", api + f"/sites/{tmp}/generation/runs/{rid}/stream", 200, lambda r: "text/event-stream" in r.headers["content-type"], headers=H)
            check("gen runs list", "GET", api + f"/sites/{tmp}/generation/runs", 200, lambda r: any(x["run_id"] == rid for x in r.json()), headers=H)
            acc = check("gen accept (human) → draft", "POST", api + f"/sites/{tmp}/generation/runs/{rid}/accept", 200, lambda r: r.json()["draft_id"] > 0 and 0 <= r.json()["score"] <= 100, headers=H)
            check("gen accept idempotent", "POST", api + f"/sites/{tmp}/generation/runs/{rid}/accept", 200, lambda r: r.json().get("already") is True, headers=H)
            check("gen run 404", "GET", api + f"/sites/{tmp}/generation/runs/gen-nope", 404, headers=H)
            if acc is not None:
                check("draft feedback (rating+tags)", "POST", api + f"/sites/{tmp}/content/{cid}/feedback", 201, lambda r: r.json()["rating"] == 5, headers=H, json={"rating": 5, "tags": ["good_structure"], "draft_id": acc.json()["draft_id"], "run_id": rid})
                check("draft feedback unknown tag filtered", "POST", api + f"/sites/{tmp}/content/{cid}/feedback", 201, lambda r: r.json()["tags"] == [], headers=H, json={"rating": 3, "tags": ["nope"]})
                check("draft feedback rating out of range → 422", "POST", api + f"/sites/{tmp}/content/{cid}/feedback", 422, headers=H, json={"rating": 9})
                check("draft feedback list", "GET", api + f"/sites/{tmp}/content/{cid}/feedback", 200, lambda r: len(r.json()) >= 1, headers=H)
        check("agent single run (research, echo proposal)", "POST", api + f"/sites/{tmp}/content/{cid}/agents/research/run", 200, lambda r: r.json()["agent"] == "research" and "payload" in r.json() and r.json()["memory_snapshot_id"] > 0, headers=H, json={})
        check("agent single run (fact_check needs section) → 404", "POST", api + f"/sites/{tmp}/content/{cid}/agents/fact_check/run", 404, headers=H, json={})
    check("ai insights list", "GET", api + f"/ai/insights?site_id={tmp}", 200, lambda r: isinstance(r.json(), list), headers=H)
    check("ai insights learn (min_n=5 → advisory)", "POST", api + f"/ai/insights/learn?site_id={tmp}", 200, lambda r: "insights" in r.json(), headers=H)

    # ---- phase 8.5: content strategy planner (tmp site: categories via local snapshot/brain, plans CRUD, mirroring, import/export, mapping, suggestions, graph)
    check("planner meta (7 statuses, 3 views, publishing disabled)", "GET", api + f"/sites/{tmp}/content-plans/meta", 200, lambda r: len(r.json()["statuses"]) == 7 and r.json()["views"] == ["table", "kanban", "graph"] and r.json()["publishing"]["enabled"] is False and r.json()["ai_generation"]["enabled"] is False, headers=H)
    check("planner categories sync (brain; WP not configured on tmp)", "POST", api + f"/sites/{tmp}/content-plans/categories/sync?min_keywords=1", 200, lambda r: "brain" in r.json() and r.json()["wordpress_error"] == "wordpress_not_configured", headers=H)
    check("planner category create (manual)", "POST", api + f"/sites/{tmp}/content-plans/categories", 201, lambda r: r.json()["source"] == "manual" and r.json()["name"] == "راهنماها", headers=H, json={"name": "راهنماها"})
    check("planner categories tree", "GET", api + f"/sites/{tmp}/content-plans/categories?tree=true", 200, lambda r: any(c["name"] == "راهنماها" for c in r.json()), headers=H)
    pl = check("planner plan create (+analyze, recommendation, advanced fields)", "POST", api + f"/sites/{tmp}/content-plans", 201, lambda r: r.json()["recommendation"]["action"] and r.json()["priority_score"] is not None and r.json()["content_gap"] in ("none", "partial", "full") and r.json()["funnel_stage"] and r.json()["ai_priority"] is not None, headers=H, json={"title": "امداد خودرو تست تهران", "primary_keyword": "امداد خودرو تست", "category": "راهنماها"})
    plid = pl.json()["id"] if pl is not None and pl.status_code == 201 else 0
    if plid:
        check("planner plan PATCH (inline edit)", "PATCH", api + f"/sites/{tmp}/content-plans/{plid}", 200, lambda r: r.json()["seo_title"] == "عنوان سئو تست" and r.json()["business_value"] == 70, headers=H, json={"seo_title": "عنوان سئو تست", "business_value": 70})
        check("planner transition researching (planner-only)", "POST", api + f"/sites/{tmp}/content-plans/{plid}/transition", 200, lambda r: r.json()["status"] == "researching" and r.json()["content_item"] is None, headers=H, json={"status": "researching"})
        check("planner transition writing without item → 409", "POST", api + f"/sites/{tmp}/content-plans/{plid}/transition", 409, headers=H, json={"status": "writing"})
        check("planner brief → content item + brief_ready", "POST", api + f"/sites/{tmp}/content-plans/{plid}/brief", 200, lambda r: bool(r.json()["h1"]) and "plan_hints" in r.json(), headers=H, json={})
        check("planner plan detail (mirrored)", "GET", api + f"/sites/{tmp}/content-plans/{plid}", 200, lambda r: r.json()["status"] == "brief_ready" and r.json()["content_item"]["has_brief"] is True and len(r.json()["events"]) >= 1, headers=H)
        check("planner generation job prepared (no run)", "POST", api + f"/sites/{tmp}/content-plans/{plid}/generation-jobs", 201, lambda r: r.json()["status"] == "prepared" and r.json()["generation_run_id"] is None, headers=H, json={"kind": "article"})
        check("planner publishing metadata only", "PUT", api + f"/sites/{tmp}/content-plans/{plid}/publishing-metadata", 200, lambda r: r.json()["publishing"]["publishing_enabled"] is False, headers=H, json={"target": "wordpress", "wp_status": "draft"})
        check("planner link prep", "POST", api + f"/sites/{tmp}/content-plans/{plid}/link-prep", 200, lambda r: "inbound" in r.json() and "outbound" in r.json(), headers=H)
        check("planner recommendations stored", "GET", api + f"/sites/{tmp}/content-plans/{plid}/recommendations", 200, lambda r: len(r.json()) >= 1 and all(x["status"] in ("new", "superseded", "accepted", "dismissed", "applied") for x in r.json()), headers=H)
    check("planner list + counts", "GET", api + f"/sites/{tmp}/content-plans?limit=50", 200, lambda r: r.json()["total"] >= 1 and "by_status" in r.json()["counts"], headers=H)
    check("planner board (7 columns)", "GET", api + f"/sites/{tmp}/content-plans/board", 200, lambda r: len(r.json()["columns"]) == 7, headers=H)
    check("planner calendar", "GET", api + f"/sites/{tmp}/content-plans/calendar?from=2026-01-01&to=2026-12-31", 200, lambda r: "days" in r.json() and "unscheduled" in r.json(), headers=H)
    csv85 = "عنوان,کلمه کلیدی اصلی,دسته,اینتنت,نوع صفحه,تاریخ انتشار,اولویت\nبرنامه واردشده,امداد خودرو تست دو,راهنماها,اطلاعاتی,راهنما,2026-09-03,متوسط\n"
    check("planner import dry-run (Persian headers)", "POST", api + f"/sites/{tmp}/content-plans/import", 200, lambda r: r.json()["dry_run"] and r.json()["created"] == 1 and r.json()["mapping"].get("کلمه کلیدی اصلی") == "primary_keyword", headers=H, files={"file": ("plans.csv", csv85.encode("utf-8"), "text/csv")}, data={"dry_run": "true"})
    check("planner import apply", "POST", api + f"/sites/{tmp}/content-plans/import", 200, lambda r: r.json()["created"] == 1, headers=H, files={"file": ("plans.csv", csv85.encode("utf-8"), "text/csv")}, data={"dry_run": "false"})
    check("planner import upsert", "POST", api + f"/sites/{tmp}/content-plans/import", 200, lambda r: r.json()["created"] == 0 and r.json()["updated"] == 1, headers=H, files={"file": ("plans.csv", csv85.encode("utf-8"), "text/csv")}, data={"dry_run": "false"})
    check("planner export csv", "GET", api + f"/sites/{tmp}/content-plans/export.csv", 200, lambda r: "text/csv" in r.headers["content-type"] and "عنوان" in r.text, headers=H)
    check("planner export xlsx", "GET", api + f"/sites/{tmp}/content-plans/export.xlsx", 200, lambda r: r.content[:2] == b"PK", headers=H)
    check("planner import template", "GET", api + f"/sites/{tmp}/content-plans/import/template.csv", 200, lambda r: "عنوان" in r.text, headers=H)
    src85 = check("planner google-sheet source create", "POST", api + f"/sites/{tmp}/content-plans/sources", 201, lambda r: r.json()["kind"] == "google_sheet" and r.json()["auto_sync"] is False, headers=H, json={"name": "شیت تست", "kind": "google_sheet", "url": "https://docs.google.com/spreadsheets/d/ABC/edit#gid=0"})
    check("planner keyword mapping overview", "GET", api + f"/sites/{tmp}/content-plans/keyword-mapping", 200, lambda r: "counts" in r.json(), headers=H)
    check("planner keyword mapping suggest (persisted)", "POST", api + f"/sites/{tmp}/content-plans/keyword-mapping/suggest", 200, lambda r: "items" in r.json() and all(i["recommendation"]["reasons_fa"] for i in r.json()["items"]), headers=H, json={"limit": 20})
    check("planner suggestions inbox", "GET", api + f"/sites/{tmp}/content-plans/suggestions", 200, lambda r: isinstance(r.json(), list), headers=H)
    check("planner analyze all (sync)", "POST", api + f"/sites/{tmp}/content-plans/analyze", 200, lambda r: r.json()["mode"] == "sync" and r.json()["analyzed"] >= 1, headers=H, json={})
    check("planner graph mode", "GET", api + f"/sites/{tmp}/graph/view?mode=planner", 200, lambda r: "CONTENT_PLAN" in r.json()["mode"]["node_types"] and any(n["type"] == "CONTENT_PLAN" for n in r.json()["nodes"]), headers=H)
    check("planner graph focus", "GET", api + f"/sites/{tmp}/content-plans/graph?plan_id={plid}", 200, lambda r: r.json().get("focus") == f"plan:{plid}", headers=H)
    check("planner node details", "GET", api + f"/sites/{tmp}/graph/node-details/plan:{plid}", 200, lambda r: r.json()["type"] == "CONTENT_PLAN" and "plan" in r.json(), headers=H)
    check("planner insights (advisory)", "POST", api + f"/sites/{tmp}/content-plans/insights/learn", 200, lambda r: "insights" in r.json(), headers=H)
    check("planner backfill", "POST", api + f"/sites/{tmp}/content-plans/backfill", 200, lambda r: "created" in r.json(), headers=H)
    check("planner plan 404", "GET", api + f"/sites/{tmp}/content-plans/999999", 404, headers=H)

    # ---- ai content test workspace (Echo — no external calls)
    check("ai workspace options (echo = offline fallback, default resolved)", "GET", api + f"/sites/{tmp}/ai-workspace/options", 200, lambda r: any(p["name"] == "echo" and p["status"] == "offline_fallback" for p in r.json()["providers"]) and "provider" in r.json()["default"] and len(r.json()["steps"]) == 7, headers=H)
    ws_spec = {"title": "امداد خودرو تست", "keyword": "امداد خودرو تست", "secondary_keywords": ["یدک کش تست"], "intent": "transactional", "content_type": "service_landing", "tone": "formal", "word_count": 400, "provider": "echo", "model": "echo-1"}
    check("ai workspace estimate", "POST", api + f"/sites/{tmp}/ai-workspace/estimate", 200, lambda r: r.json()["provider"] == "echo" and r.json()["input_tokens"] > 0 and r.json()["prompt_ref"].startswith("task.article_test"), headers=H, json=ws_spec)
    check("ai workspace generate (echo placeholder)", "POST", api + f"/sites/{tmp}/ai-workspace/generate", 200, lambda r: r.json()["ok"] and r.json()["meta"]["placeholder"] is True and r.json()["result"]["markdown"].startswith("# ") and r.json()["seo"]["total_checks"] == 9, headers=H, json=ws_spec)
    check("ai workspace history", "GET", api + f"/sites/{tmp}/ai-workspace/history", 200, lambda r: len(r.json()) >= 1, headers=H)
    check("ai workspace save-draft 404", "POST", api + f"/sites/{tmp}/ai-workspace/save-draft", 404, headers=H, json={"content_id": 999999, "markdown": "# x"})

    # ---- legacy + cleanup
    check("legacy dashboard", "GET", BASE + "/legacy/", 200)
    check("legacy api", "GET", BASE + "/legacy/api/sites", 200)
    check("site delete refused (has data) → 409", "DELETE", api + f"/sites/{tmp}", 409, lambda r: r.json()["error"]["code"] == "site_has_data" and {"site_memory", "site_connections", "graph_nodes"} <= set(r.json()["error"]["details"]), headers=H)
    check("site delete force", "DELETE", api + f"/sites/{tmp}?force=true", 200, lambda r: r.json()["deleted"] == tmp and r.json()["related_rows_deleted"].get("site_connections") == 3 and r.json()["related_rows_deleted"].get("keywords") == 2, headers=H)
    check("site gone → 404", "GET", api + f"/sites/{tmp}", 404, headers=H)
    check("real site untouched", "GET", api + f"/sites/{sid}/graph/summary", 200, lambda r: r.json()["nodes"] > 0, headers=H)

    # tidy: remove the (empty) workspace folders the temp site created; the API itself never deletes files
    import shutil
    ws = _bootstrap.ROOT / "data" / "sites" / tmp
    if ws.exists() and all(p.name == "README.md" for p in ws.rglob("*") if p.is_file()):   # only initializer artefacts
        shutil.rmtree(ws, ignore_errors=True)
    passed = sum(1 for c in CHECKS if c["ok"]); total = len(CHECKS)
    lines = [f"# Phase 1.5 — live API validation report", "",
             f"Date: {datetime.now(timezone.utc).isoformat(timespec='seconds')} · Base: `{BASE}` · Site: `{sid}` · Temp site: `{tmp}` (created and force-deleted)",
             f"", f"**Result: {passed}/{total} checks passed**", "",
             "| # | Check | Method | Path | Status | Expected | ms | OK | Note |", "|---|---|---|---|---|---|---|---|---|"]
    for i, c in enumerate(CHECKS, 1):
        lines.append(f"| {i} | {c['name']} | {c['method']} | `{c['url']}` | {c['status']} | {c['expect']} | {c['ms']} | {'✅' if c['ok'] else '❌'} | {c['note'].replace('|', '/')} |")
    lines += ["", "## Coverage", "",
              "* health / openapi / docs / request-id · error envelope (404, 409, 422) · sites CRUD (create, get, list, patch, delete-refuse, delete-force, 404 after) ·",
              "  phase 3: connections status/tests (gsc/ga4/wordpress + 404 kind), gsc properties listing, initialize (idempotent), site brain fields + AI context ·",
              "  phase 6: content create/transition guard/brief/board/calendar/graph sync/delete · ai provider config (masked key)/task routes ·",
              "  phase 7: drafts v1/v2, score, review, intelligence history, scoring/analytics settings, snapshot/learn/overview/insights ·",
              "  phase 8: links meta/analyze/summary/suggestions/pages/patterns/settings/export ·",
              "  phase 9: ai task-kinds/models/health/budget(get/put/422)/usage/routing preview/route policy+fallbacks/prompts (seeded, get, preview, version 422/create/approve)/feedback tags ·",
              "  phase 9: generation meta/memory-preview/estimate/start (202, autopilot 422)/run detail+provenance/SSE/list/accept (+idempotent)/404/feedback (+422)/single agent/insights ·",
              "  ai workspace: options/estimate/generate (echo)/history/save-draft 404 ·",
              "  phase 8.5: planner meta/categories (sync brain, manual, tree)/plan create+PATCH+transitions (researching, 409 gate)/brief→item/generation job prepared/publishing metadata/link prep/recommendations/list/board/calendar/import (dry-run, apply, upsert)/export csv+xlsx/template/sheet source/keyword mapping+suggest/suggestions/analyze/graph mode+focus+details/insights/backfill/404 ·",
              "  graph (summary, nodes, node, 404, neighbors, filtered neighbors, subgraph, 422, search, path, orphans, unknown site) ·",
              "  memory (get, put, context, learned pattern) · AI orchestrator (routes, providers, text run, JSON run + learn, 422) · jobs (enqueue, poll, list, 422, 404) · legacy mount.",
              "* All checks ran over real HTTP against uvicorn (not TestClient). Read-only on the real site; writes only on the temporary site."]
    report = "\n".join(lines) + "\n"
    if a.out:
        with open(a.out, "w", encoding="utf-8") as f:
            f.write(report)
    print(report if not a.out else f"{passed}/{total} passed → {a.out}")
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
