"""Phase 9 — AI gateway (adapters via fake transports), routing, prompts, MemoryPack, section-by-section pipeline (job + SSE), feedback, learning."""
import json

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from seo_brain.ai.config import ProviderConfigRepository
from seo_brain.ai.gateway import CallMeta, Gateway, RouteStep, TaskRouter
from seo_brain.ai.gateway.adapters import AnthropicAdapter, CloudflareAdapter, GeminiAdapter, OllamaAdapter, OpenAICompatAdapter
from seo_brain.ai.prompts import PromptError, PromptLibrary, render
from seo_brain.ai.types import AIMessage, AIRequest, AIResponse, AITask, TaskKind
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
        parts = [p for ct in (body.get("contents") or []) for p in (ct.get("parts") or [])]   # Gemini wire format
        for m in (body.get("messages") or []) + parts:
            c = (m.get("content") or m.get("text")) if isinstance(m, dict) else ""
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


def test_cloudflare_uses_token_verify_and_catalog_for_connection_probe():
    seen = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append((req.method, str(req.url), req.headers.get("authorization")))
        return httpx.Response(200, json={"success": True}, request=req)

    base = "https://api.cloudflare.com/client/v4/accounts/account-id/ai/v1"
    adapter = CloudflareAdapter("cloudflare", "cf_token", base, ["@cf/qwen/qwen3-30b-a3b-fp8"], {}, transport=httpx.MockTransport(handler))
    result = adapter.test_connection()
    assert result["ok"] and result["models"] == ["@cf/qwen/qwen3-30b-a3b-fp8"]
    assert seen == [("GET", "https://api.cloudflare.com/client/v4/accounts/account-id/tokens/verify", "Bearer cf_token")]


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
    # meta / publishing endpoints: phase 16 allows ONLY the mode-gated writer paths (plan publish + capability probe)
    meta = c.get(f"/api/v1/sites/{SID}/generation/meta").json()
    assert meta["modes"] == ["manual", "assisted"] and meta["reserved_modes"] == ["autopilot"] and "fact_check" in [a["agent"] for a in meta["agents"]]
    allowed_publish = {"/api/v1/sites/{site_id}/content-plans/{plan_id}/publish", "/api/v1/sites/{site_id}/wordpress/publish-capability",
                       "/api/v1/sites/{site_id}/content/{cid}/wordpress/publish"}  # Content Brain explicit human publish (production)
    extra = {p_ for p_ in c.get("/api/openapi.json").json()["paths"] if "publish" in p_ and "metadata" not in p_} - allowed_publish
    assert not extra, f"unexpected publish endpoints: {extra}"


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


def test_ai_workspace_echo_and_real_provider(c):
    """AI Content Test Workspace: options (echo + configured providers), estimate, generate via Echo (placeholder), generate via a fake OpenAI provider,
    SEO analysis, prompt/meta, save as draft (human action), history — all through the Gateway abstraction."""
    _seed_content(c)
    opts = c.get(f"/api/v1/sites/{SID}/ai-workspace/options").json()
    echo = next(p for p in opts["providers"] if p["name"] == "echo")
    assert echo["configured"] and echo["status"] == "offline_fallback" and opts["default"]["provider"] == "echo" and [s["key"] for s in opts["steps"]][:3] == ["research", "outline", "writer"] and opts["prompt"]
    spec = {"title": "امداد خودرو MVM در تهران", "keyword": "امداد خودرو mvm", "secondary_keywords": ["یدک کش mvm", "امداد خودرو mvm تهران"], "intent": "transactional", "content_type": "service_landing", "category": "MVM",
            "audience": "مالکان MVM", "tone": "formal", "word_count": 600, "instructions": "شماره تماس در پاراگراف اول"}
    est = c.post(f"/api/v1/sites/{SID}/ai-workspace/estimate", json={**spec, "provider": "echo"}).json()
    assert est["provider"] == "echo" and est["input_tokens"] > 0 and est["prompt_ref"].startswith("task.article_test") and est["memory_snapshot_id"] > 0
    g = c.post(f"/api/v1/sites/{SID}/ai-workspace/generate", json={**spec, "provider": "echo"})
    assert g.status_code == 200, g.text
    out = g.json()
    assert out["ok"] and out["meta"]["provider"] == "echo" and out["meta"]["placeholder"] is True and out["result"]["markdown"].startswith("# ") and out["result"]["sections"] and out["result"]["faq"]
    assert out["seo"]["total_checks"] == 9 and any(ch["key"] == "kw_in_title" and ch["ok"] for ch in out["seo"]["checks"]) and "memory_pack" not in out["prompt"]["user"] and "حافظه سایت" in out["prompt"]["user"]
    assert "امداد خودرو mvm" in out["result"]["markdown"] and out["result"]["word_count"] > 0
    # real (fake-transport) provider
    _add_provider(c, "OpenAI", "openai")
    opts2 = c.get(f"/api/v1/sites/{SID}/ai-workspace/options").json()
    oa = next(p for p in opts2["providers"] if p["name"] == "OpenAI")
    assert oa["configured"] and any(m["model_id"] == "gpt-4o-mini" for m in oa["models"])
    g2r = c.post(f"/api/v1/sites/{SID}/ai-workspace/generate", json={**spec, "provider": "OpenAI", "model": "gpt-4o-mini"}); assert g2r.status_code == 200, g2r.text; g2 = g2r.json()
    assert g2["meta"]["provider"] == "OpenAI" and g2["meta"]["model"] == "gpt-4o-mini" and g2["meta"]["placeholder"] is False and g2["result"]["sections"] and g2["meta"]["input_tokens"] >= 0
    hist = c.get(f"/api/v1/sites/{SID}/ai-workspace/history").json()
    assert len(hist) >= 2 and hist[0]["provider"] == "OpenAI"
    # save as draft into an existing content item (human hand-off)
    cid = c.get(f"/api/v1/sites/{SID}/content").json()["items"][0]["id"]
    sd = c.post(f"/api/v1/sites/{SID}/ai-workspace/save-draft", json={"content_id": cid, "markdown": out["result"]["markdown"], "title": out["result"]["title"], "meta_description": out["result"]["meta_description"], "meta": out["meta"]})
    assert sd.status_code == 201 and sd.json()["draft_id"]
    d = c.get(f"/api/v1/sites/{SID}/content/{cid}/drafts").json()[0]
    assert d["source"] == "ai:echo" and d["review_status"] == "none"
    assert c.post(f"/api/v1/sites/{SID}/ai-workspace/save-draft", json={"content_id": 99999, "markdown": "# x"}).status_code == 404


# --------------------------------------------------------------------------- Claude (Anthropic) integration
def _sse(events: list[dict]) -> bytes:
    return "".join(f"event: {e['type']}\ndata: {json.dumps(e, ensure_ascii=False)}\n\n" for e in events).encode()


def test_anthropic_adapter_streaming_sampling_count_tokens_and_refusal():
    from seo_brain.ai.providers.base import ProviderError
    seen = {}

    def handler(req: httpx.Request) -> httpx.Response:
        body = json.loads(req.content or b"{}") if req.method == "POST" else {}
        seen[req.url.path] = body
        assert req.headers.get("x-api-key") == "sk-ant-test" and req.headers.get("anthropic-version")
        if req.url.path == "/v1/messages/count_tokens":
            return httpx.Response(200, json={"input_tokens": 321})
        if req.url.path == "/v1/models":
            return httpx.Response(200, json={"data": [{"id": "claude-sonnet-5"}, {"id": "claude-opus-5"}], "has_more": False})
        if body.get("model") == "refuse-me":
            return httpx.Response(200, headers={"content-type": "text/event-stream"}, content=_sse([
                {"type": "message_start", "message": {"id": "m0", "model": "refuse-me", "usage": {"input_tokens": 5}}},
                {"type": "message_delta", "delta": {"stop_reason": "refusal", "stop_details": {"category": "cyber"}}, "usage": {"output_tokens": 0}}]))
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, content=_sse([
            {"type": "message_start", "message": {"id": "msg_s", "model": body.get("model"), "usage": {"input_tokens": 100, "output_tokens": 1}}},
            {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}},
            {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "```json\n{\"title\": \"سلام\","}},
            {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": " \"sections\": []}\n```"}},
            {"type": "content_block_stop", "index": 0},
            {"type": "message_delta", "delta": {"stop_reason": "end_turn"}, "usage": {"output_tokens": 42}},
            {"type": "message_stop"}]))

    a = AnthropicAdapter("anthropic", "sk-ant-test", None, [], {"claude-sonnet-5": (3.0, 15.0)}, transport=httpx.MockTransport(handler))
    # sonnet-5: streamed, no temperature, fences stripped, usage merged from message_start + message_delta
    deltas = []
    r = a.complete(AIRequest(model="claude-sonnet-5", messages=[AIMessage("system", "s"), AIMessage("user", "u")], max_tokens=500, temperature=0.4, json_schema={"properties": {"title": {}, "sections": {}}}), on_delta=deltas.append)
    assert seen["/v1/messages"]["stream"] is True and "temperature" not in seen["/v1/messages"] and seen["/v1/messages"]["system"] == "s"
    assert json.loads(r.text)["title"] == "سلام" and r.input_tokens == 100 and r.output_tokens == 42 and r.cost_usd == pytest.approx((100 * 3 + 42 * 15) / 1e6) and r.raw["streamed"] and len(deltas) == 2
    # legacy model keeps temperature
    a.complete(AIRequest(model="claude-sonnet-4-5", messages=[AIMessage("user", "u")], max_tokens=50, temperature=0.2))
    assert seen["/v1/messages"]["temperature"] == 0.2 and AnthropicAdapter.accepts_temperature("claude-haiku-4-5") and not AnthropicAdapter.accepts_temperature("claude-opus-5")
    # exact estimate via count_tokens
    est = a.estimate(AIRequest(model="claude-sonnet-5", messages=[AIMessage("user", "متن")], max_tokens=1000, temperature=0.4))
    assert est["exact"] and est["input_tokens"] == 321 and "max_tokens" not in seen["/v1/messages/count_tokens"] and "stream" not in seen["/v1/messages/count_tokens"]
    assert a.list_models() == ["claude-sonnet-5", "claude-opus-5"] and a.test_connection()["ok"]
    # refusal → non-retryable
    with pytest.raises(ProviderError) as ei:
        a.complete(AIRequest(model="refuse-me", messages=[AIMessage("user", "u")], max_tokens=50, temperature=0))
    assert ei.value.retryable is False and "refusal" in str(ei.value)
    # no key → heuristic estimate, no network
    est2 = AnthropicAdapter("anthropic", None, None, [], {}, transport=httpx.MockTransport(lambda rq: httpx.Response(500))).estimate(AIRequest(model="claude-sonnet-5", messages=[AIMessage("user", "متن")], max_tokens=1000, temperature=0.4))
    assert est2["input_tokens"] > 0 and not est2.get("exact")


def test_claude_provider_setup_routes_and_workspace_default(c):
    """Claude provider via SecretStore: catalog seeded (Sonnet/Opus/Haiku), key never returned, recommended routes are a human action,
    workspace defaults to Claude Sonnet with Echo kept as offline fallback, generation metadata carries prompt version + memory snapshot."""
    _seed_content(c)
    p = _add_provider(c, "anthropic", "anthropic", "sk-ant-api03-abcdefgh1234")
    assert p["has_key"] and p["key_hint"] == "1234" and "secret_ref" not in p and "api_key" not in json.dumps(p) and p["default_model"] == "claude-sonnet-5"
    kinds = {k["kind"]: k for k in c.get("/api/v1/ai/provider-kinds").json()}
    assert kinds["anthropic"]["setup"]["console_url"].startswith("https://platform.claude.com") and "claude-haiku-4-5" in kinds["anthropic"]["models"]
    models = {m["model_id"]: m for m in c.get(f"/api/v1/ai/models?provider_id={p['id']}").json()}
    assert {"claude-sonnet-5", "claude-opus-5", "claude-haiku-4-5"} <= set(models) and models["claude-sonnet-5"]["tier"] == "balanced" and models["claude-opus-5"]["tier"] == "quality" and models["claude-haiku-4-5"]["tier"] == "fast"
    assert models["claude-sonnet-5"]["price_out_per_m"] == 15.0 and models["claude-opus-5"]["price_in_per_m"] == 5.0
    # discovery merges live model ids without duplicating catalog rows
    sync = c.post(f"/api/v1/ai/models/sync?provider_id={p['id']}").json()
    assert sync["anthropic"]["discovered"] == 2 and all("claude" in m for m in models)
    # test connection (fake transport) → status recorded, no key in response
    t = c.post(f"/api/v1/ai/provider-configs/{p['id']}/test").json()
    assert t["ok"] and "sk-ant" not in json.dumps(t)
    # recommended routes: preview is read-only, applying is explicit
    rec = c.get(f"/api/v1/ai/provider-configs/{p['id']}/recommended-routes").json()["routes"]
    by = {r["task_kind"]: r for r in rec}
    assert by["article_long"]["model"] == "claude-sonnet-5" and by["article_long"]["fallback_model"] == "claude-opus-5" and by["seo_review"]["model"] == "claude-sonnet-5" and by["title_meta"]["model"] == "claude-haiku-4-5"
    assert all(r["provider_id"] is None for r in c.get("/api/v1/ai/task-routes").json()["routes"])
    ap = c.post(f"/api/v1/ai/provider-configs/{p['id']}/recommended-routes", json={}).json()
    assert ap["applied"] == len(rec)
    routes = {r["task_kind"]: r for r in c.get("/api/v1/ai/task-routes").json()["routes"]}
    assert routes["article_long"]["provider_name"] == "anthropic" and routes["article_long"]["model"] == "claude-sonnet-5" and routes["article_long"]["fallback_model"] == "claude-opus-5" and routes["article_long"]["policy"] == "explicit"
    assert routes["faq"]["model"] == "claude-haiku-4-5"
    prev = c.get("/api/v1/ai/routing/preview?task_kind=article_long").json()
    assert prev["policy"] == "explicit" and [s["model"] for s in prev["chain"][:2]] == ["claude-sonnet-5", "claude-opus-5"]
    # workspace: Claude Sonnet is the default, Echo remains available (last)
    opts = c.get(f"/api/v1/sites/{SID}/ai-workspace/options").json()
    assert opts["default"] == {"provider": "anthropic", "model": "claude-sonnet-5", "kind": "anthropic"} and opts["providers"][-1]["name"] == "echo"
    cl = next(pp for pp in opts["providers"] if pp["name"] == "anthropic")
    assert cl["status"] == "connected" and cl["models"][0]["model_id"] == "claude-sonnet-5" and cl["models"][0]["display"] == "Claude Sonnet 5" and cl["last_test"]["ok"]
    spec = {"title": "امداد خودرو رنو ساندرو", "keyword": "امداد خودرو رنو ساندرو", "secondary_keywords": ["امداد خودرو ساندرو تهران"], "intent": "commercial", "content_type": "service_landing", "word_count": 500}
    est = c.post(f"/api/v1/sites/{SID}/ai-workspace/estimate", json={**spec, "provider": "anthropic"}).json()      # provider without model → default model
    assert est["provider"] == "anthropic" and est["model"] == "claude-sonnet-5" and est["cost_usd"] > 0
    g = c.post(f"/api/v1/sites/{SID}/ai-workspace/generate", json={**spec, "provider": "anthropic", "model": "claude-sonnet-5"}); assert g.status_code == 200, g.text
    m = g.json()["meta"]
    assert m["provider"] == "anthropic" and m["provider_kind"] == "anthropic" and m["model"] == "claude-sonnet-5" and m["placeholder"] is False and m["prompt_version"].startswith("task.article_test") and m["memory_snapshot_id"] > 0 and m["run_id"].startswith("ws-")
    assert m["input_tokens"] == 120 and m["output_tokens"] == 80 and m["cost_usd"] == pytest.approx((120 * 3 + 80 * 15) / 1e6)
    hist = c.get(f"/api/v1/sites/{SID}/ai-workspace/history").json()
    assert hist[0]["provider"] == "anthropic" and hist[0]["run_id"] == m["run_id"]
    # Echo still works as explicit offline fallback
    e = c.post(f"/api/v1/sites/{SID}/ai-workspace/generate", json={**spec, "provider": "echo"}).json()
    assert e["meta"]["provider"] == "echo" and e["meta"]["placeholder"] is True
    # provider without key → missing_credentials in options, router ignores it
    p2 = c.post("/api/v1/ai/provider-configs", json={"name": "claude-nokey", "kind": "anthropic"}).json()
    o2 = next(pp for pp in c.get(f"/api/v1/sites/{SID}/ai-workspace/options").json()["providers"] if pp["name"] == "claude-nokey")
    assert o2["status"] == "missing_credentials" and not o2["configured"] and p2["has_key"] is False


def test_gemini_provider_setup_routes_env_fallback_and_workspace(c, monkeypatch):
    """Gemini 3.6 Flash as a first-class provider: kind metadata + setup, catalog seeding, recommended routes,
    workspace generation through the gateway (fake google transport), and the optional GEMINI_API_KEY env fallback."""
    _seed_content(c)
    kinds = {k["kind"]: k for k in c.get("/api/v1/ai/provider-kinds").json()}
    g = kinds["google"]
    assert g["models"][0] == "gemini-3.6-flash" and g["setup"]["console_url"].startswith("https://aistudio.google.com")
    assert "content_generation" in g["capabilities"] and g["env_key"] == "GEMINI_API_KEY"
    # registry drives the UI: Gemini needs NO base URL from the user; only Cloudflare/custom truly do
    assert g["requires_base_url"] is False and g["supports_model_discovery"] is True and g["auth_type"] == "api_key"
    assert kinds["cloudflare"]["requires_base_url"] is True and kinds["custom"]["requires_base_url"] is True
    assert kinds["ollama"]["auth_type"] == "optional_api_key"
    p = _add_provider(c, "gemini", "google", "AIzaTestKey12345678")
    assert p["has_key"] and p["default_model"] == "gemini-3.6-flash" and "api_key" not in json.dumps(p) and "secret_ref" not in p
    models = {m["model_id"]: m for m in c.get(f"/api/v1/ai/models?provider_id={p['id']}").json()}
    assert {"gemini-3.6-flash", "gemini-2.5-pro", "gemini-2.5-flash"} <= set(models)
    assert models["gemini-3.6-flash"]["tier"] == "balanced" and models["gemini-3.6-flash"]["context_tokens"] == 1000000
    t = c.post(f"/api/v1/ai/provider-configs/{p['id']}/test").json()
    assert t["ok"] and "AIzaTest" not in json.dumps(t)
    # recommended routes: heavy tasks fall back to 2.5 Pro, light tasks to 2.5 Flash — applying stays a human action
    rec = {r["task_kind"]: r for r in c.get(f"/api/v1/ai/provider-configs/{p['id']}/recommended-routes").json()["routes"]}
    assert rec["article_long"]["model"] == "gemini-3.6-flash" and rec["article_long"]["fallback_model"] == "gemini-2.5-pro"
    assert rec["faq"]["model"] == "gemini-3.6-flash" and rec["faq"]["fallback_model"] == "gemini-2.5-flash"
    ap = c.post(f"/api/v1/ai/provider-configs/{p['id']}/recommended-routes", json={}).json()
    assert ap["applied"] == len(rec)
    prev = c.get("/api/v1/ai/routing/preview?task_kind=content_writing").json()
    assert prev["policy"] == "explicit" and [s["model"] for s in prev["chain"][:2]] == ["gemini-3.6-flash", "gemini-2.5-pro"]
    # workspace generation goes through the same gateway/ledger path
    spec = {"title": "امداد خودرو پژو", "keyword": "امداد خودرو پژو", "word_count": 400}
    r = c.post(f"/api/v1/sites/{SID}/ai-workspace/generate", json={**spec, "provider": "gemini", "model": "gemini-3.6-flash"})
    assert r.status_code == 200, r.text
    m = r.json()["meta"]
    assert m["provider"] == "gemini" and m["provider_kind"] == "google" and m["model"] == "gemini-3.6-flash" and m["placeholder"] is False
    assert m["input_tokens"] == 90 and m["output_tokens"] == 50
    # optional env fallback: a keyless google provider becomes configured once GEMINI_API_KEY is set (key never stored)
    p2 = c.post("/api/v1/ai/provider-configs", json={"name": "gemini-env", "kind": "google"}).json()
    assert p2["has_key"] is False and p2["configured"] is False and p2["key_source"] is None
    monkeypatch.setenv("GEMINI_API_KEY", "AIzaEnvKey")
    p2b = next(x for x in c.get("/api/v1/ai/provider-configs").json() if x["name"] == "gemini-env")
    assert p2b["configured"] is True and p2b["key_source"] == "env" and p2b["has_key"] is False
    repo = ProviderConfigRepository(c.eng, c.store)
    assert repo.api_key(repo.get_by_name("gemini-env")) == "AIzaEnvKey"
    monkeypatch.delenv("GEMINI_API_KEY")
    # optional GEMINI_MODEL env: default model for a new google provider
    monkeypatch.setenv("GEMINI_MODEL", "gemini-2.5-flash")
    p3 = c.post("/api/v1/ai/provider-configs", json={"name": "gemini-envmodel", "kind": "google"}).json()
    assert p3["default_model"] == "gemini-2.5-flash"


# --------------------------------------------------------------------------- OmniRoute (external gateway behind the SEO Brain Gateway)
def _omni_transport(grouped: bool = False, key_required: str | None = None):
    seen: dict = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen[req.url.path] = json.loads(req.content or b"{}") if req.method == "POST" else {}
        seen["auth"] = req.headers.get("authorization")
        if key_required and req.headers.get("authorization") != f"Bearer {key_required}":
            return httpx.Response(401, json={"error": "unauthorized"})
        if req.url.path.endswith("/models"):
            if grouped:
                return httpx.Response(200, json={"data": {"claude": [{"id": "opus-5"}, {"id": "claude/sonnet-5"}], "openai": [{"id": "gpt-4o"}]}})
            return httpx.Response(200, json={"object": "list", "data": [{"id": "claude/sonnet-5", "owned_by": "claude"}, {"id": "openai/gpt-4o", "owned_by": "openai"}, {"id": "gemini/gemini-2.5-flash"}]})
        body = seen[req.url.path]
        want_json = bool(body.get("response_format"))
        out = json.dumps({"title": "ساندرو", "sections": [{"h2": "خدمات", "paragraphs": ["متن"]}], "faq": [], "internal_links": [], "meta_description": "م", "h1": "ه", "keywords_used": [], "notes": ""}, ensure_ascii=False) if want_json else "پاسخ OmniRoute"
        hdr = {"X-OmniRoute-Decision": "strategy=auto;provider=claude;model=claude-sonnet-5;latency=812", "X-OmniRoute-Cost": "0.0012"}
        if body.get("stream"):
            chunks = [{"id": "c1", "model": "claude/sonnet-5", "choices": [{"delta": {"content": out[:5]}}]}, {"id": "c1", "model": "claude/sonnet-5", "choices": [{"delta": {"content": out[5:]}, "finish_reason": "stop"}]},
                      {"id": "c1", "model": "claude/sonnet-5", "choices": [], "usage": {"prompt_tokens": 90, "completion_tokens": 33}}]
            content = "".join(f"data: {json.dumps(ch, ensure_ascii=False)}\n\n" for ch in chunks) + "data: [DONE]\n\n"
            return httpx.Response(200, headers={"content-type": "text/event-stream", **hdr}, content=content.encode())
        return httpx.Response(200, headers=hdr, json={"id": "cmpl-o", "model": "claude/sonnet-5", "choices": [{"message": {"content": out}, "finish_reason": "stop"}], "usage": {"prompt_tokens": 100, "completion_tokens": 40}})
    return httpx.MockTransport(handler), seen


def test_omniroute_adapter_contract():
    from seo_brain.ai.gateway.providers import OmniRouteAdapter, ProviderAdapter
    from seo_brain.ai.providers.base import ProviderError
    t, seen = _omni_transport()
    a = OmniRouteAdapter("omniroute", None, None, [], {"claude/sonnet-5": (3.0, 15.0)}, transport=t)
    assert isinstance(a, ProviderAdapter) and a.base_url == "http://127.0.0.1:20128/v1"
    caps = a.capabilities(); assert caps["gateway"] and caps["streaming"] and "auto" in caps["auto_models"] and caps["decision_header"] == "X-OmniRoute-Decision"
    ms = a.list_models(); assert ms[:4] == ["auto", "auto/fast", "auto/cheap", "auto/coding"] and "claude/sonnet-5" in ms and "gemini/gemini-2.5-flash" in ms and seen["auth"] is None
    tr = a.test(); assert tr["ok"] and tr["gateway"] and a.last_health["ok"]
    req = AIRequest(model="claude/sonnet-5", messages=[AIMessage("system", "s"), AIMessage("user", "u")], max_tokens=300, temperature=0.4, json_schema={"properties": {"title": {}, "sections": {}}})
    r = a.complete(req)
    assert json.loads(r.text)["title"] == "ساندرو" and r.input_tokens == 90 and r.output_tokens == 33 and r.cost_usd == pytest.approx((90 * 3 + 33 * 15) / 1e6) and r.raw["streamed"]   # complete() consumes the stream (OmniRoute may SSE regardless)
    assert r.raw["gateway"] == "omniroute" and r.raw["decision"]["decision"].startswith("strategy=auto;provider=claude") and a.last_decision["cost"] == "0.0012"
    assert seen["/v1/chat/completions"]["response_format"] == {"type": "json_object"} and "temperature" not in seen["/v1/chat/completions"]  # sonnet-5 → no sampling params
    a.complete(AIRequest(model="openai/gpt-4o", messages=[AIMessage("user", "u")], max_tokens=50, temperature=0.2)); assert seen["/v1/chat/completions"]["temperature"] == 0.2
    # streaming: deltas then final AIResponse with usage from the last chunk
    items = list(a.stream(req)); deltas, final = items[:-1], items[-1]
    assert len(deltas) == 2 and isinstance(final, AIResponse) and final.raw["streamed"] and final.input_tokens == 90 and final.output_tokens == 33 and json.loads(final.text)["title"] == "ساندرو"
    assert seen["/v1/chat/completions"]["stream"] is True
    # grouped /models shape + bearer key + 401 handling
    t2, seen2 = _omni_transport(grouped=True, key_required="omni-key")
    b = OmniRouteAdapter("omniroute", "omni-key", None, [], {}, transport=t2)
    assert {"claude/opus-5", "claude/sonnet-5", "openai/gpt-4o"} <= set(b.list_models()) and seen2["auth"] == "Bearer omni-key"
    bad = OmniRouteAdapter("omniroute", "wrong", None, [], {}, transport=t2)
    with pytest.raises(ProviderError) as ei:
        bad.list_models()
    assert ei.value.retryable is False
    # default adapters also satisfy the contract (stream = single chunk)
    at, _ = fake_transport("anthropic")
    an = AnthropicAdapter("anthropic", "sk-ant-test", None, [], {}, transport=at)
    assert isinstance(an, ProviderAdapter) and an.capabilities()["gateway"] is False and isinstance(list(an.stream(AIRequest(model="claude-sonnet-5", messages=[AIMessage("user", "u")], max_tokens=20, temperature=0)))[-1], AIResponse)


def test_omniroute_provider_end_to_end(c):
    """OmniRoute registered as a provider kind: keyless config counts as configured, catalog seeds auto models, discovery adds provider/model ids,
    workspace exposes route_kind gateway, gateway-status endpoint reports routing/fallback, generation runs through the SEO Brain Gateway (ledger, budget)."""
    _seed_content(c)
    t, seen = _omni_transport()
    orig = c.gw._transport_factory
    c.gw._transport_factory = lambda kind: t if kind == "omniroute" else orig(kind)
    kinds = {k["kind"]: k for k in c.get("/api/v1/ai/provider-kinds").json()}
    assert kinds["omniroute"]["is_gateway"] and kinds["omniroute"]["needs_key"] is False and kinds["omniroute"]["base_url"].endswith(":20128/v1")
    p = c.post("/api/v1/ai/provider-configs", json={"name": "omniroute", "kind": "omniroute"}).json()
    assert p["configured"] and p["is_gateway"] and p["route_kind"] == "gateway" and p["endpoint_url"] == "http://127.0.0.1:20128/v1" and p["has_key"] is False and p["default_model"] == "auto"
    c.gw.seed_catalog(p["id"], "omniroute"); c.gw.invalidate()
    models = {m["model_id"]: m for m in c.get(f"/api/v1/ai/models?provider_id={p['id']}").json()}
    assert {"auto", "auto/fast", "auto/cheap", "auto/coding"} <= set(models) and models["auto"]["tier"] == "balanced"
    sync = c.post(f"/api/v1/ai/models/sync?provider_id={p['id']}").json()["omniroute"]
    assert sync["discovered"] >= 5 and sync["added"] >= 3
    models = {m["model_id"]: m for m in c.get(f"/api/v1/ai/models?provider_id={p['id']}").json()}
    assert models["claude/sonnet-5"]["tier"] == "balanced" and models["openai/gpt-4o"]["source"] == "discovered"
    tst = c.post(f"/api/v1/ai/provider-configs/{p['id']}/test").json(); assert tst["ok"] and "auto" in tst["models_found"]
    # optional API key → SecretStore, never returned
    p2 = c.patch(f"/api/v1/ai/provider-configs/{p['id']}", json={"api_key": "omni-secret-7777"}).json()
    assert p2["has_key"] and p2["key_hint"] == "7777" and "omni-secret" not in json.dumps(p2)
    # gateway status (routing/fallback) before any call
    gs = c.get(f"/api/v1/ai/provider-configs/{p['id']}/gateway-status").json()
    assert gs["is_gateway"] and gs["status"] == "connected" and gs["capabilities"]["gateway"] and gs["routing"]["auto_models"][0] == "auto" and gs["routing"]["models_available"] >= 7 and gs["fallback"]["fallback_for"] == []
    # recommended routes for the gateway → apply → article_long routed to omniroute/auto
    ap = c.post(f"/api/v1/ai/provider-configs/{p['id']}/recommended-routes", json={}).json(); assert ap["applied"] == 17
    prev = c.get("/api/v1/ai/routing/preview?task_kind=article_long").json(); assert prev["chain"][0]["provider"] == "omniroute" and prev["chain"][0]["model"] == "auto"
    # workspace: gateway route kind exposed, generation goes through the SEO Brain Gateway (ledger row, decision captured)
    opts = c.get(f"/api/v1/sites/{SID}/ai-workspace/options").json()
    om = next(x for x in opts["providers"] if x["name"] == "omniroute"); assert om["route_kind"] == "gateway" and om["configured"] and om["status"] == "connected"
    assert next(x for x in opts["providers"] if x["name"] == "echo")["route_kind"] == "offline"
    spec = {"title": "امداد خودرو رنو ساندرو", "keyword": "امداد خودرو رنو ساندرو", "secondary_keywords": ["امداد خودرو ساندرو تهران"], "intent": "commercial", "content_type": "service_landing", "word_count": 400}
    g = c.post(f"/api/v1/sites/{SID}/ai-workspace/generate", json={**spec, "provider": "omniroute", "model": "claude/sonnet-5"}); assert g.status_code == 200, g.text
    m = g.json()["meta"]
    assert m["provider"] == "omniroute" and m["provider_kind"] == "omniroute" and m["placeholder"] is False and m["gateway_decision"]["decision"].startswith("strategy=auto") and m["served_model"] == "claude/sonnet-5"
    assert m["input_tokens"] == 90 and m["output_tokens"] == 33 and m["memory_snapshot_id"] > 0 and m["prompt_version"].startswith("task.article_test")
    hist = c.get(f"/api/v1/sites/{SID}/ai-workspace/history").json(); assert hist[0]["provider"] == "omniroute"
    gs2 = c.get(f"/api/v1/ai/provider-configs/{p['id']}/gateway-status").json()
    assert gs2["routing"]["last_decision"]["decision"].startswith("strategy=auto") and gs2["recent_calls"][0]["ok"] == 1 and "article_long" in gs2["routing"]["primary_for"]
    # Echo untouched
    e = c.post(f"/api/v1/sites/{SID}/ai-workspace/generate", json={**spec, "provider": "echo"}).json(); assert e["meta"]["placeholder"] is True
    c.gw._transport_factory = orig
