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
    ap.add_argument("--site", default="emdadmodiran", help="existing site with graph data (read-only checks)")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    BASE = a.base.rstrip("/")
    api = BASE + "/api/v1"
    H = {"X-API-Token": os.environ.get("API_TOKEN", "")} if os.environ.get("API_TOKEN") else {}
    sid = a.site
    tmp = f"zz-validation-{uuid.uuid4().hex[:6]}"

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
    check("graph modes", "GET", api + f"/sites/{sid}/graph/modes", 200, lambda r: [m["key"] for m in r.json()] == ["seo", "content", "links"], headers=H)
    check("graph view seo", "GET", api + f"/sites/{sid}/graph/view?mode=seo", 200, lambda r: len(r.json()["nodes"]) > 0 and len(r.json()["edges"]) > 0 and r.json()["mode"]["key"] == "seo", headers=H)
    check("graph view links (no isolated)", "GET", api + f"/sites/{sid}/graph/view?mode=links&include_isolated=false", 200, lambda r: all(e["relation_type"] in ("LINKS_TO", "SUGGESTED_LINK") for e in r.json()["edges"]), headers=H)
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
    check("wordpress test (real site, read-only)", "POST", api + f"/sites/{tmp}/connections/wordpress/test", 200, lambda r: r.json()["status"] in ("ok", "error", "not_found"), headers=H, json={"property": "https://emdadmodiran.com"})
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
