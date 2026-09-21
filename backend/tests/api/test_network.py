"""Settings → «شبکهٔ Brain»: one read-only snapshot of Brain ↔ AI writers, Brain ↔ sites (WordPress), site ↔ GSC/GA4
and cross-site links (external links whose host is another managed site)."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from seo_brain.api import deps
from seo_brain.api.main import create_app
from seo_brain.api.routers import sites as sites_router
from seo_brain.db.engine import make_engine
from seo_brain.db.migrate import migrate


@pytest.fixture
def c(tmp_path, monkeypatch):
    eng = make_engine("sqlite:///" + (tmp_path / "net.db").as_posix()); migrate(eng)
    monkeypatch.delenv("API_TOKEN", raising=False)
    monkeypatch.setattr(sites_router, "PROJECT_ROOT", tmp_path)
    app = create_app(); app.dependency_overrides[deps.engine] = lambda: eng
    client = TestClient(app); client.eng = eng  # type: ignore[attr-defined]
    return client


def test_network_snapshot(c):
    r = c.post("/api/v1/sites", json={"site_id": "site-a", "name": "A", "canonical_url": "https://a.example/"})
    assert r.status_code == 201, r.text
    assert c.post("/api/v1/sites", json={"site_id": "site-b", "name": "B", "canonical_url": "https://b.example/"}).status_code == 201
    c.patch("/api/v1/sites/site-a", json={"wp_url": "https://a.example"})
    assert c.post("/api/v1/ai/provider-configs", json={"name": "claude", "kind": "anthropic"}).status_code == 201   # no key → off
    with c.eng.begin() as cx:
        cx.execute(text("INSERT INTO site_connections(site_id, kind, status) VALUES('site-a','wordpress','ok'),('site-a','gsc','ok')"))
        cx.execute(text("INSERT INTO links(site_id, source_url, target_url, is_internal) VALUES"
                        "('site-a','https://a.example/p1','https://www.b.example/x',0),('site-a','https://a.example/p2','https://b.example/y',0),"
                        "('site-a','https://a.example/p3','https://other.example/',0),('site-b','https://b.example/q','https://a.example/p1',0)"))
    d = c.get("/api/v1/network").json()
    by_id = {n["id"]: n for n in d["nodes"]}
    assert by_id["brain"]["kind"] == "brain"
    assert by_id["site:site-a"]["status"] == "ok" and by_id["site:site-a"]["meta"]["wordpress"] == "ok" and by_id["site:site-b"]["status"] == "off"
    assert by_id["gsc:site-a"]["status"] == "ok" and by_id["ga4:site-a"]["status"] == "off" and by_id["gsc:site-b"]["status"] == "off"
    prov = [n for n in d["nodes"] if n["kind"] == "provider"]
    assert len(prov) == 1 and prov[0]["meta"]["kind"] == "anthropic" and prov[0]["status"] == "off" and prov[0]["label"] == "Claude (Anthropic)"
    kinds = {e["kind"] for e in d["edges"]}
    assert {"ai", "wp", "gsc", "ga4", "backlink"} <= kinds
    cross = sorted((e["source"], e["target"], e["weight"], e["label"]) for e in d["edges"] if e["kind"] == "backlink")
    assert cross == [("site:site-a", "site:site-b", 2, "2 لینک"), ("site:site-b", "site:site-a", 1, "1 لینک")]
    assert d["counts"] == {"providers": 1, "sites": 2, "cross_links": 2}
