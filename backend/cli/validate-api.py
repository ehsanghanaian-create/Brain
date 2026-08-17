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

    # ---- legacy + cleanup
    check("legacy dashboard", "GET", BASE + "/legacy/", 200)
    check("legacy api", "GET", BASE + "/legacy/api/sites", 200)
    check("site delete refused (has memory) → 409", "DELETE", api + f"/sites/{tmp}", 409, lambda r: r.json()["error"]["code"] == "site_has_data" and "site_memory" in r.json()["error"]["details"], headers=H)
    check("site delete force", "DELETE", api + f"/sites/{tmp}?force=true", 200, lambda r: r.json()["deleted"] == tmp and r.json()["related_rows_deleted"].get("site_memory") == 1, headers=H)
    check("site gone → 404", "GET", api + f"/sites/{tmp}", 404, headers=H)
    check("real site untouched", "GET", api + f"/sites/{sid}/graph/summary", 200, lambda r: r.json()["nodes"] > 0, headers=H)

    # tidy: remove the (empty) workspace folders the temp site created; the API itself never deletes files
    import shutil
    ws = _bootstrap.ROOT / "data" / "sites" / tmp
    if ws.exists() and not any(p.is_file() for p in ws.rglob("*")):
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
