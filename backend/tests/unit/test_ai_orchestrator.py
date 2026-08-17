from seo_brain.ai import (AIMessage, AIOrchestrator, AIRouter, AITask, EchoProvider, MemoryService, Route, TaskKind)
from seo_brain.automation import InProcessJobQueue, Job
from seo_brain.db.engine import make_engine
from seo_brain.db.migrate import migrate
from seo_brain.db.repositories import SiteMemoryRepository, SitesRepository
from seo_brain.db.repositories.sites import Site


def _router(fail_primary=False):
    r = AIRouter(providers={})
    r.register(EchoProvider())
    bad = EchoProvider(fail=True); bad.name = "bad"          # type: ignore[attr-defined]
    r.register(bad)
    r.set_route(TaskKind.CONTENT_WRITING, [Route("bad", "b-1"), Route("echo", "echo-1")] if fail_primary else [Route("echo", "echo-1")])
    r.default = [Route("echo", "echo-1")]
    return r


def test_task_router_provider_validator_flow():
    orch = AIOrchestrator(_router())
    task = AITask(TaskKind.CONTENT_WRITING, "t", [AIMessage("user", "سلام")])
    res = orch.run(task)
    assert res.ok and res.response.text == "سلام" and res.route_used == Route("echo", "echo-1")
    assert res.attempts[0].ok


def test_fallback_on_provider_error():
    orch = AIOrchestrator(_router(fail_primary=True))
    res = orch.run(AITask(TaskKind.CONTENT_WRITING, "t", [AIMessage("user", "x")]))
    assert res.ok and res.route_used.provider == "echo"
    assert [a.ok for a in res.attempts] == [False, True] and "ProviderError" in res.attempts[0].error


def test_json_validation_sets_parsed_and_fails_on_missing_keys():
    orch = AIOrchestrator(_router())
    schema = {"type": "object", "required": ["title", "h1"], "properties": {"title": {}, "h1": {}}}
    res = orch.run(AITask(TaskKind.BRIEF, "t", [AIMessage("user", "brief")], json_schema=schema))
    assert res.ok and res.response.parsed == {"title": "echo:title", "h1": "echo:h1"}
    # provider that returns non-JSON for a JSON task → validation error → no route left → not ok
    r = AIRouter(providers={}); r.register(EchoProvider()); r.set_route(TaskKind.BRIEF, [Route("echo", "echo-1")])
    class NoJson(EchoProvider):
        name = "nojson"
        def complete(self, request):
            request.json_schema = None
            return super().complete(request)
    r.register(NoJson()); r.set_route(TaskKind.BRIEF, [Route("nojson", "echo-1")])
    res2 = AIOrchestrator(r).run(AITask(TaskKind.BRIEF, "t", [AIMessage("user", "not json")], json_schema=schema))
    assert not res2.ok and "ValidationError" in res2.attempts[0].error


def test_memory_context_and_learning(tmp_path):
    eng = make_engine("sqlite:///" + (tmp_path / "m.db").as_posix()); migrate(eng)
    SitesRepository(eng).save(Site(site_id="t", name="T", canonical_url="https://t.example/"))
    mem = MemoryService(SiteMemoryRepository(eng))
    mem.update("t", business_rules=["no price promises"], tone={"voice": "formal"})
    orch = AIOrchestrator(_router(), memory=mem)
    res = orch.run(AITask(TaskKind.SEO_ANALYSIS, "t", [AIMessage("user", "analyse")]),
                   learn={"pattern": "service pages first", "evidence": "test"})
    assert res.ok and res.memory_used
    m = mem.get("t")
    assert m.successful_patterns and m.successful_patterns[0]["source"].startswith("seo_analysis:echo/")
    ctx = mem.context_messages("t")[0].content
    assert "no price promises" in ctx and "voice=formal" in ctx and "service pages first" in ctx


def test_inprocess_job_queue_sync():
    q = InProcessJobQueue(sync=True)
    q.register("add", lambda p: p["a"] + p["b"])
    q.register("boom", lambda p: 1 / 0)
    ok = q.enqueue(Job("add", {"a": 2, "b": 3}))
    bad = q.enqueue(Job("boom"))
    assert ok.status == "succeeded" and ok.result == 5
    assert bad.status == "failed" and "ZeroDivisionError" in bad.error
    assert q.get(ok.run_id) is ok and len(q.list()) == 2
