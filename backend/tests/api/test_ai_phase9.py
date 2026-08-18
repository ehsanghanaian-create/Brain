"""Phase 9 — AI gateway (adapters via fake transports), routing, prompts, MemoryPack, section-by-section pipeline (job + SSE), feedback, learning."""
import json

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from seo_brain.ai.config import ProviderConfigRepository
from seo_brain.ai.gateway import CallMeta, Gateway, RouteStep, TaskRouter
from seo_brain.ai.gateway.adapters import AnthropicAdapter, GeminiAdapter, OllamaAdapter, OpenAICompatAdapter
from seo_brain.ai.prompts import PromptError, PromptLibrary, render
from seo_brain.ai.types import AIMessage, AIRequest, AITask, TaskKind
from seo_brain.api import deps
from seo_brain.api.main import create_app
from seo_brain.api.routers import ai_config as ai_config_router
from seo_brain.api.routers import graph as graph_router
from seo_brain.api.routers import sites as sites_router
from seo_brain.automation.events import InProcessEventBus
from seo_brain.automation.queue import InProcessJobQueue
from seo_brain.brain.generation import GenerationPipeline, validate_section
from seo_brain.core.secrets import SecretStore
from seo_brain.database.db import connect as legacy_connect
from seo_brain.db.engine import make_engine
from seo_brain.db.migrate import migrate

SID = "demo"


# --------------------------------------------------------------------------- fake provider transports
def fake_transport(kind: str, fail_first: int = 0, status: int = 200):
    calls = {"n": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] <= fail_first:
            return httpx.Response(status, json={"error": "busy"})
        body = json.loads(req.content or b"{}") if req.method == "POST" else {}
        # figure out whether JSON was requested and echo keys back
        text_in = json.dumps(body, ensure_ascii=False)
        want_json = "JSON" in text_in or "json" in text_in.lower()
        keys = []
        for m in (body.get("messages") or []):
            c = m.get("content") if isinstance(m, dict) else ""
            if isinstance(c, str) and "کلیدهای" in c:
                keys = [k.strip() for k in c.split("کلیدهای", 1)[1].split("برگردان")[0].replace("،", ",").split(",") if k.strip()]
        out = json.dumps({k: (["x"] if k.endswith("s") else "x") for k in keys} or {"text": "سلام"}, ensure_ascii=False) if want_json else "پاسخ آزمایشی فارسی برای " + kind
        if kind == "anthropic":
            if req.url.path.endswith("/models"):
                return httpx.Response(200, json={"data": [{"id": "claude-sonnet-5"}, {"id": "claude-haiku-4-5-20251001"}]})
            return httpx.Response(200, json={"id": "msg_1", "model": body.get("model"), "content": [{"type": "text", "text": out}], "usage": {"input_tokens": 120, "output_tokens": 80}, "stop_reason": "end_turn"})
        if kind in ("openai", "openrouter", "custom"):
            if req.url.path.endswith("/models"):
                return httpx.Response(200, json={"data": [{"id": "gpt-5-mini"}, {"id": "gpt-4o-mini"}]})
            return httpx.Response(200, json={"id": "cmpl", "model": body.get("model"), "choices": [{"message": {"content": out}, "finish_reason": "stop"}], "usage": {"prompt_tokens": 100, "completion_tokens": 60}})
        if kind == "google":
            if "/models?" in str(req.url) or str(req.url).endswith("/models"):
                return httpx.Response(200, json={"models": [{"name": "models/gemini-2.5-flash"}]})
            return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": out}]}, "finishReason": "STOP"}], "usageMetadata": {"promptTokenCount": 90, "candidatesTokenCount": 50}})
        if kind == "ollama":
            if req.url.path.endswith("/api/tags"):
                return httpx.Response(200, json={"models": [{"name": "llama3"}]})
            return httpx.Response(200, json={"message": {"content": out}, "prompt_eval_count": 70, "eval_count": 40, "done_reason": "stop"})
        return httpx.Response(500)
    return httpx.MockTransport(handler), calls


def test_adapters_complete_and_list_models_via_fake_transports():
    req = AIRequest(model="m", messages=[AIMessage("system", "s"), AIMessage("user", "u")], max_tokens=100, temperature=0.2)
    for cls, kind in ((AnthropicAdapter, "anthropic"), (OpenAICompatAdapter, "openai"), (GeminiAdapter, "google"), (OllamaAdapter, "ollama")):
        t, _ = fake_transport(kind)
        a = cls("p", "key", None, ["m"], {"m": (1.0, 2.0)}, transport=t)
        r = a.complete(req)
        assert r.text and r.input_tokens > 0 and r.output_tokens > 0 and r.provider == "p" and r.latency_ms >= 0
        assert r.cost_usd == pytest.approx(0.0 if kind == 'ollama' else (r.input_tokens * 1.0 + r.output_tokens * 2.0) / 1e6)   # local models cost 0
        assert a.list_models()
        assert a.test_connection()["ok"]
    # json request → JSON text with requested keys
    t, _ = fake_transport("openai")
    a = OpenAICompatAdapter("p", "key", None, ["m"], {}, transport=t)
    r = a.complete(AIRequest(model="m", messages=[AIMessage("user", "u")], max_tokens=50, temperature=0, json_schema={"required": ["facts", "gaps"], "properties": {"facts": {}, "gaps": {}}}))
    assert set(json.loads(r.text)) == {"facts", "gaps"}
    # auth error → non-retryable ProviderError
    from seo_brain.ai.providers.base import ProviderError
    bad = OpenAICompatAdapter("p", "key", None, ["m"], {}, transport=httpx.MockTransport(lambda rq: httpx.Response(401, json={})))
    with pytest.raises(ProviderError) as ei:
        bad.complete(req)
    assert ei.value.retryable is False


@pytest.fixture
def c(tmp_path, monkeypatch):
    dbfile = tmp_path / "ai.db"
    eng = make_engine("sqlite:///" + dbfile.as_posix()); migrate(eng)
    monkeypatch.delenv("API_TOKEN", raising=False)
    monkeypatch.setattr(graph_router, "connect", lambda: legacy_connect(dbfile))
    monkeypatch.setattr(sites_router, "PROJECT_ROOT", tmp_path)
    store = SecretStore(tmp_path / "secrets")
    transports = {}

    def tf(kind):
        t, calls = fake_transport(kind, fail_first=transports.get(("fail", kind), 0), status=transports.get(("status", kind), 503))
        transports[kind] = calls
        return t
    gw = Gateway(eng, transport_factory=tf); gw.cfg = ProviderConfigRepository(eng, store)
    q = InProcessJobQueue(sync=True); bus = InProcessEventBus()
    app = create_app()
    app.dependency_overrides[deps.engine] = lambda: eng
    app.dependency_overrides[deps.gateway] = lambda: gw
    app.dependency_overrides[deps.job_queue] = lambda: q
    app.dependency_overrides[ai_config_router.cfg_repo] = lambda: ProviderConfigRepository(eng, store)
    monkeypatch.setattr("seo_brain.api.routers.generation.get_event_bus", lambda: bus)
    monkeypatch.setattr("seo_brain.brain.generation.pipeline.get_event_bus", lambda: bus)
    q.register("generation_run", lambda payload: GenerationPipeline(eng, gw, bus).execute(payload["run_id"]))
    client = TestClient(app)
    assert client.post("/api/v1/sites", json={"site_id": SID, "name": "Demo", "canonical_url": "https://demo.example/"}).status_code == 201
    client.post(f"/api/v1/sites/{SID}/initialize")
    client.eng, client.gw, client.store, client.transports, client.bus = eng, gw, store, transports, bus  # type: ignore[attr-defined]
    return client


def _seed_content(c):
    with c.eng.begin() as cx:
        for nid, t, label, url in (("page:https://demo.example/mvm/", "PAGE", "امداد خودرو MVM", "https://demo.example/mvm/"), ("model:mvm", "MODEL", "MVM", None), ("location:tehran", "LOCATION", "تهران", None), ("service:emdad", "SERVICE", "امداد خودرو", None)):
            cx.execute(text("INSERT INTO graph_nodes(site_id,node_id,node_type,label,url,props,pagerank,updated_at) VALUES(:s,:n,:t,:l,:u,'{}',0.2,datetime('now'))"), {"s": SID, "n": nid, "t": t, "l": label, "u": url})
        cx.execute(text("INSERT INTO graph_edges(site_id,edge_id,source_id,target_id,edge_type,weight) VALUES(:s,'e1','page:https://demo.example/mvm/','model:mvm','ABOUT',1)"), {"s": SID})
        cx.execute(text("INSERT INTO gsc_query_page(site_id,page,query,clicks,impressions,ctr,position) VALUES(:s,'https://demo.example/mvm/','امداد خودرو mvm',2,300,0,8.5)"), {"s": SID})
    csv = "keyword,intent,priority,volume\nامداد خودرو mvm,transactional,high,1300\nامداد خودرو mvm تهران,local,medium,200\n"
    c.post(f"/api/v1/sites/{SID}/keywords/import", files={"file": ("k.csv", csv.encode(), "text/csv")}, data={"dry_run": "false"})
    c.post(f"/api/v1/sites/{SID}/keywords/cluster")
    c.put(f"/api/v1/sites/{SID}/memory", json={"business_rules": ["فقط تهران"], "tone": {"voice": "formal"}, "cta_rules": ["شماره در پاراگراف اول"], "forbidden_claims": ["ارزان‌ترین"]})
    kw = next(k for k in c.get(f"/api/v1/sites/{SID}/keywords").json()["items"] if k["keyword"] == "امداد خودرو mvm")
    cid = c.post(f"/api/v1/sites/{SID}/content", json={"title": "امداد خودرو MVM در تهران", "target_keyword_id": kw["id"]}).json()["id"]
    c.post(f"/api/v1/sites/{SID}/content/{cid}/brief", json={"mark_ready": True})
    return cid


def _add_provider(c, name="OpenAI", kind="openai", key="sk-test-1234abcd"):
    p = c.post("/api/v1/ai/provider-configs", json={"name": name, "kind": kind, "api_key": key}).json()
    c.gw.seed_catalog(p["id"], kind); c.gw.invalidate()
    return p


def test_prompts_memorypack_and_routing(c):
    _seed_content(c)
    # prompt library seeded + versioning + activation/approval + memory requirement
    lst = c.get("/api/v1/ai/prompts").json()
    keys = {p["key"] for p in lst}
    assert {"system.base", "site.brain", "agent.research", "agent.outline", "agent.writer_section", "agent.fact_check", "agent.seo", "agent.linking", "agent.reviewer"} <= keys
    writer = next(p for p in lst if p["key"] == "agent.writer_section")
    assert writer["active_version"] == 1 and writer["versions"][0]["approval"] == "approved"
    v2 = c.post(f"/api/v1/ai/prompts/{writer['id']}/versions", json={"template": "{{memory_pack}}\nنسخه دوم: بخش «{{h2}}» را بنویس. خروجی JSON با کلیدهای markdown, word_count برگردان", "changelog": "v2 shorter", "activate": False}).json()
    assert v2["version"] == 2 and v2["is_active"] == 0 and "h2" in v2["variables"]
    assert c.post(f"/api/v1/ai/prompts/{writer['id']}/versions", json={"template": "بدون حافظه"}).status_code == 422       # generic writing refused
    act = c.patch(f"/api/v1/ai/prompts/versions/{v2['id']}", json={"activate": True, "approval": "approved", "approved_by": "sepehr"}).json()
    assert act["is_active"] == 1 and act["approval"] == "approved" and act["approved_by"] == "sepehr"
    assert c.get("/api/v1/ai/prompts").json() and next(p for p in c.get("/api/v1/ai/prompts").json() if p["key"] == "agent.writer_section")["active_version"] == 2
    # preview renders memory pack (Site Brain injected)
    pv = c.post(f"/api/v1/ai/prompts/versions/{v2['id']}/preview", json={"site_id": SID, "variables": {"h2": "خدمات"}}).json()
    assert "فقط تهران" in pv["rendered"] and "ارزان‌ترین" in pv["rendered"] and "خدمات" in pv["rendered"] and pv["memory_snapshot_id"]
    mp = c.get(f"/api/v1/sites/{SID}/generation/memory-preview").json()
    assert mp["pack"]["business_rules"] == ["فقط تهران"] and "شماره در پاراگراف اول" in mp["rendered"]
    # routing: no providers → echo; with provider → policy picks tiers; explicit route wins
    r0 = c.get("/api/v1/ai/routing/preview", params={"task_kind": "article_section", "site_id": SID}).json()
    assert r0["policy"] == "echo" and r0["chain"][0]["provider"] == "echo"
    p = _add_provider(c)
    r1 = c.get("/api/v1/ai/routing/preview", params={"task_kind": "outline", "site_id": SID}).json()
    assert r1["policy"] == "auto" and r1["chain"][0]["provider"] == "OpenAI" and r1["chain"][0]["model"] in ("gpt-4o-mini", "gpt-5-mini")     # fast/cheap first
    r2 = c.get("/api/v1/ai/routing/preview", params={"task_kind": "seo_review", "site_id": SID}).json()
    assert r2["chain"][0]["model"] == "gpt-5"                                                                                             # reasoning first
    r3 = c.get("/api/v1/ai/routing/preview", params={"task_kind": "article_section", "site_id": SID}).json()
    assert r3["chain"][0]["model"] == "gpt-4.1"                                                                                          # quality first
    c.put("/api/v1/ai/task-routes/outline", json={"provider_id": p["id"], "model": "gpt-4.1"})
    r4 = c.get("/api/v1/ai/routing/preview", params={"task_kind": "outline", "site_id": SID}).json()
    assert r4["policy"] == "explicit" and r4["chain"][0]["model"] == "gpt-4.1" and len(r4["chain"]) >= 2                                  # explicit + auto fallback
    # models catalog + user edits
    ms = c.get("/api/v1/ai/models").json()
    m = next(x for x in ms if x["model_id"] == "gpt-4o-mini")
    assert m["tier"] == "fast" and m["provider"] == "OpenAI"
    up = c.patch(f"/api/v1/ai/models/{m['id']}", json={"price_out_per_m": 0.9, "enabled": False}).json()
    assert up["price_out_per_m"] == 0.9 and up["enabled"] is False and up["source"] == "user"
    est = c.post("/api/v1/ai/estimate", json={"task_kind": "outline", "site_id": SID, "text": "سلام دنیا " * 100}).json()
    assert est["input_tokens"] > 0 and est["cost_usd"] >= 0 and est["route"]["policy"] == "explicit"


def test_gateway_fallback_ledger_breaker_budget(c):
    _seed_content(c)
    p1 = _add_provider(c, "Broken", "anthropic", "sk-ant-x1234")
    p2 = _add_provider(c, "OpenAI", "openai")
    c.transports[("fail", "anthropic")] = 99      # anthropic always 503
    task = AITask(kind=TaskKind.GENERIC, site_id=SID, messages=[AIMessage("user", "تست")], max_tokens=50)
    res = c.gw.run(task, [RouteStep("Broken", "claude-sonnet-5", "explicit"), RouteStep("OpenAI", "gpt-4o-mini", "fallback")], CallMeta(site_id=SID, agent="t"))
    assert res.ok and res.response.provider == "OpenAI" and len(res.attempts) >= 2 and res.attempts[0].ok is False and res.attempts[-1].ok is True
    # ledger + usage + health
    u = c.get("/api/v1/ai/usage", params={"site_id": SID, "group_by": "provider"}).json()
    assert any(r["key"] == "OpenAI" and r["calls"] >= 1 and r["cost_usd"] >= 0 for r in u["rows"]) and u["budget"]["limit_usd"] == 20.0
    h = c.get("/api/v1/ai/health").json()["providers"]
    assert next(x for x in h if x["provider"] == "Broken")["failures"] >= 1
    # breaker opens after 3 consecutive failures → provider skipped
    for _ in range(3):
        c.gw.run(task, [RouteStep("Broken", "claude-sonnet-5", "x")], CallMeta(site_id=SID))
    res2 = c.gw.run(task, [RouteStep("Broken", "claude-sonnet-5", "x"), RouteStep("OpenAI", "gpt-4o-mini", "fb")], CallMeta(site_id=SID))
    assert res2.attempts[0].error == "circuit breaker open" and res2.response.provider == "OpenAI"
    assert c.get("/api/v1/ai/routing/preview", params={"task_kind": "outline", "site_id": SID}).json()["chain"][0]["provider"] == "OpenAI"   # router excludes broken provider
    # budget: warn/soft/hard via seeded cost
    with c.eng.begin() as cx:
        cx.execute(text("INSERT INTO ai_calls(site_id,task_kind,provider,model,cost_usd,ok,created_at) VALUES(:s,'x','OpenAI','m',17.0,1,strftime('%Y-%m-%dT%H:%M:%fZ','now'))"), {"s": SID})
    assert c.get("/api/v1/ai/budget", params={"site_id": SID}).json()["state"] == "warning"
    with c.eng.begin() as cx:
        cx.execute(text("INSERT INTO ai_calls(site_id,task_kind,provider,model,cost_usd,ok,created_at) VALUES(:s,'x','OpenAI','m',4.0,1,strftime('%Y-%m-%dT%H:%M:%fZ','now'))"), {"s": SID})
    assert c.get("/api/v1/ai/budget", params={"site_id": SID}).json()["state"] == "soft_limit"
    assert c.gw.run(task, [RouteStep("OpenAI", "gpt-4o-mini", "x")], CallMeta(site_id=SID)).ok            # soft limit still runs
    with c.eng.begin() as cx:
        cx.execute(text("INSERT INTO ai_calls(site_id,task_kind,provider,model,cost_usd,ok,created_at) VALUES(:s,'x','OpenAI','m',4.0,1,strftime('%Y-%m-%dT%H:%M:%fZ','now'))"), {"s": SID})
    assert c.get("/api/v1/ai/budget", params={"site_id": SID}).json()["state"] == "hard_stop"
    from seo_brain.ai.gateway import BudgetExceeded
    with pytest.raises(BudgetExceeded):
        c.gw.run(task, [RouteStep("OpenAI", "gpt-4o-mini", "x")], CallMeta(site_id=SID))
    cid = _seed_content(c) if False else c.get(f"/api/v1/sites/{SID}/content").json()["items"][0]["id"]
    r = c.post(f"/api/v1/sites/{SID}/content/{cid}/generate", json={})
    assert r.status_code == 409 and r.json()["error"]["code"] == "budget_exceeded"


def test_section_validation_rules():
    good = "## خدمات امداد خودرو MVM\n\n" + ("امداد خودرو MVM در تهران با تیم مجرب و قطعات اصلی. " * 25)
    v = validate_section(good, 150, ["MVM"], ["ارزان‌ترین"], "امداد خودرو mvm")
    assert v["ok"] and v["words"] > 150 and not v["issues"]
    bad = "متن بدون سرفصل، ما ارزان‌ترین هستیم. در این مقاله ..."
    v2 = validate_section(bad, 150, ["MVM"], ["ارزان‌ترین"], "امداد خودرو mvm")
    codes = {i["code"] for i in v2["issues"]}
    assert not v2["ok"] and {"no_h2", "forbidden_claim", "too_short", "boilerplate", "entities_missing"} <= codes


def test_pipeline_echo_manual_and_real_assisted_with_sse_feedback_learning(c):
    cid = _seed_content(c)
    # 1) manual mode without providers → echo placeholders, artifacts, no draft until human accepts
    est = c.post(f"/api/v1/sites/{SID}/content/{cid}/generate/estimate", json={}).json()
    assert est["total"]["input_tokens"] > 0 and est["sections"] >= 4 and est["memory_snapshot_id"] and set(est["per_agent"]) >= {"research", "outline", "writer", "fact_check", "seo", "linking", "reviewer"}
    r = c.post(f"/api/v1/sites/{SID}/content/{cid}/generate", json={"mode": "manual"})
    assert r.status_code == 202, r.text
    run_id = r.json()["run_id"]
    run = c.get(f"/api/v1/sites/{SID}/generation/runs/{run_id}").json()
    assert run["status"] == "succeeded" and run["memory_snapshot_id"] and run["draft_id"] is None
    steps = [s["key"] for s in run["steps"]]
    assert steps[:2] == ["research", "outline"] and any(s.startswith("section:") for s in steps) and {"assembly", "seo", "linking", "review"} <= set(steps) and "draft" not in steps
    arts = {a["step"]: a for a in run["artifacts"]}
    assert arts["assembly"]["payload"]["markdown"].startswith("# ") and arts["research"]["provenance"]["placeholder"] is True and arts["outline"]["provenance"]["prompt_version_id"]
    sec1 = next(a for a in run["artifacts"] if a["step"] == "section:1")
    assert "validation" in sec1["payload"] and "fact_check" in sec1["payload"] and sec1["provenance"]["memory_snapshot_id"] == run["memory_snapshot_id"]
    # SSE replay for finished run
    ev = c.get(f"/api/v1/sites/{SID}/generation/runs/{run_id}/stream").text
    assert "event: step_start" in ev and "event: step_done" in ev and "event: done" in ev and "section:1" in ev
    # human accepts → draft version + phase-7 review
    acc = c.post(f"/api/v1/sites/{SID}/generation/runs/{run_id}/accept").json()
    assert acc["draft_id"] and acc["version"] == 1 and acc["review_status"] in ("ready", "changes_requested")
    d = c.get(f"/api/v1/sites/{SID}/content/{cid}/drafts/{acc['draft_id']}").json()
    assert d["source"].startswith("ai:") and d["provenance"]["run_id"] == run_id and d["provenance"]["memory_snapshot_id"] == run["memory_snapshot_id"]
    assert c.post(f"/api/v1/sites/{SID}/generation/runs/{run_id}/accept").json()["already"] is True
    # 2) assisted mode with a real (fake-transport) provider → draft created automatically, models/prompts recorded, ledger rows
    p = _add_provider(c, "OpenAI", "openai")
    r = c.post(f"/api/v1/sites/{SID}/content/{cid}/generate", json={"mode": "assisted", "models": {"writer": {"provider": "OpenAI", "model": "gpt-4.1"}}})
    run2 = c.get(f"/api/v1/sites/{SID}/generation/runs/{r.json()['run_id']}").json()
    assert run2["status"] == "succeeded" and run2["draft_id"] and run2["models"]["writer"] == {"provider": "OpenAI", "model": "gpt-4.1"} and run2["prompt_versions"]["writer"]
    assert run2["actual"]["cost_usd"] >= 0 and run2["actual"]["input_tokens"] > 0 and any(s["key"] == "draft" for s in run2["steps"])
    calls = c.get("/api/v1/ai/usage", params={"site_id": SID, "group_by": "agent"}).json()["rows"]
    assert {r_["key"] for r_ in calls} >= {"writer", "outline", "research", "fact_check", "seo", "linking", "reviewer"}
    with c.eng.connect() as cx:
        row = cx.execute(text("SELECT memory_snapshot_id, prompt_refs, route_reason FROM ai_calls WHERE run_id=:r AND agent='writer' LIMIT 1"), {"r": run2["run_id"]}).first()
    assert row[0] == run2["memory_snapshot_id"] and "agent.writer_section" in row[1] and row[2]
    # single agent run (proposal only)
    sa = c.post(f"/api/v1/sites/{SID}/content/{cid}/agents/outline/run", json={}).json()
    assert sa["ok"] and "sections" in sa["payload"] and sa["provenance"]["provider"] == "OpenAI"
    assert c.get(f"/api/v1/sites/{SID}/content/{cid}/drafts").json()[0]["version"] == 2       # no extra draft from single agent
    # feedback + learning (needs n>=5 → nothing yet; with min_n=2 → insights, recommendation only)
    fb = c.post(f"/api/v1/sites/{SID}/content/{cid}/feedback", json={"rating": 4, "tags": ["good_structure", "weak_intro", "nope"], "run_id": run2["run_id"], "draft_id": run2["draft_id"]}).json()
    assert fb["rating"] == 4 and fb["tags"] == ["good_structure", "weak_intro"]
    assert c.post(f"/api/v1/sites/{SID}/content/{cid}/feedback", json={"rating": 9}).status_code == 422
    assert c.post("/api/v1/ai/insights/learn", params={"site_id": SID}).json()["insights"] == []          # small sample → nothing
    for _ in range(2):
        c.post(f"/api/v1/sites/{SID}/content/{cid}/generate", json={"mode": "assisted"})
    res = c.post("/api/v1/ai/insights/learn", params={"site_id": SID, "min_n": 2}).json()
    assert res["samples"] >= 3
    routes_before = c.get("/api/v1/ai/task-routes").json()["routes"]
    ins = c.get("/api/v1/ai/insights", params={"site_id": SID}).json()
    if ins:
        acc_i = c.patch(f"/api/v1/ai/insights/{ins[0]['id']}", json={"status": "accepted"}).json()
        assert acc_i["status"] == "accepted"
    assert c.get("/api/v1/ai/task-routes").json()["routes"] == routes_before                                  # routing never auto-changes
    # meta / no publishing endpoint
    meta = c.get(f"/api/v1/sites/{SID}/generation/meta").json()
    assert meta["modes"] == ["manual", "assisted"] and meta["reserved_modes"] == ["autopilot"] and "fact_check" in [a["agent"] for a in meta["agents"]]
    assert not any("publish" in p_ for p_ in c.get("/api/openapi.json").json()["paths"])


def _debug(c, run):
    return {"status": run["status"], "error": run.get("error"), "models": run["models"], "steps": [(s["key"], s["status"], (s.get("error") or "")[:80]) for s in run["steps"]]}


def test_route_policy_fallbacks_and_budget_put(c):
    """Phase 9 additive route fields (policy, fallbacks chain) drive the TaskRouter; budget is human-set per site."""
    p1 = _add_provider(c, "OpenAI", "openai")
    p2 = _add_provider(c, "Claude", "anthropic", "sk-ant-x1234")
    r = c.put("/api/v1/ai/task-routes/outline", json={"provider_id": p1["id"], "model": "gpt-4o-mini", "policy": "explicit",
                                                       "fallbacks": [{"provider_id": p2["id"], "model": "claude-haiku-4-5"}]})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["policy"] == "explicit" and body["fallbacks"][0]["provider_name"] == "Claude"
    # omitted policy/fallbacks keep their values (additive contract)
    r2 = c.put("/api/v1/ai/task-routes/outline", json={"provider_id": p1["id"], "model": "gpt-4o-mini"}).json()
    assert r2["policy"] == "explicit" and len(r2["fallbacks"]) == 1
    d = c.get("/api/v1/ai/routing/preview", params={"task_kind": "outline", "site_id": SID}).json()
    assert d["policy"] == "explicit" and d["chain"][0]["model"] == "gpt-4o-mini" and any(s["model"] == "claude-haiku-4-5" for s in d["chain"])
    assert c.put("/api/v1/ai/task-routes/outline", json={"policy": "weird"}).status_code in (400, 422)
    # echo policy → routing decision echo
    c.put("/api/v1/ai/task-routes/outline", json={"provider_id": p1["id"], "model": "gpt-4o-mini", "policy": "echo"})
    assert c.get("/api/v1/ai/routing/preview", params={"task_kind": "outline", "site_id": SID}).json()["policy"] != "explicit"
    # budget: human-set per site, thresholds fixed
    b = c.put("/api/v1/ai/budget", params={"site_id": SID}, json={"budget_usd_month": 5}).json()
    assert b["limit_usd"] == 5.0 and b["thresholds"] == {"warning": 0.8, "soft_limit": 1.0, "hard_stop": 1.2}
    assert c.get("/api/v1/ai/budget", params={"site_id": SID}).json()["limit_usd"] == 5.0
    assert c.put("/api/v1/ai/budget", params={"site_id": SID}, json={"budget_usd_month": 0}).status_code == 422
