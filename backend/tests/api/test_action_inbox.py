"""The unified inbox must preserve source, site and evidence boundaries."""
from fastapi.testclient import TestClient
from sqlalchemy import text

from seo_brain.api import deps
from seo_brain.api.main import create_app
from seo_brain.db.engine import make_engine
from seo_brain.db.migrate import migrate


def test_action_inbox_joins_only_active_site_scoped_signals(tmp_path, monkeypatch):
    monkeypatch.delenv("API_TOKEN", raising=False)
    eng = make_engine("sqlite:///" + (tmp_path / "inbox.db").as_posix())
    migrate(eng)
    app = create_app()
    app.dependency_overrides[deps.engine] = lambda: eng
    client = TestClient(app)
    for site in ("one", "two"):
        assert client.post("/api/v1/sites", json={"site_id": site, "name": site, "canonical_url": f"https://{site}.example/"}).status_code == 201
    with eng.begin() as cx:
        cx.execute(text("""INSERT INTO issue_cases(site_id,fingerprint,problem_type,url,severity,status,detail,first_seen,last_seen)
            VALUES ('one','case-one','missing_h1','https://one.example/a/','high','open','{\"count\": 0}', '2026-10-10','2026-10-11'),
                   ('two','case-two','orphan','https://two.example/b/','low','open','{}','2026-10-10','2026-10-11'),
                   ('one','case-old','missing_h1','https://one.example/old/','high','resolved','{}','2026-10-09','2026-10-10')"""))
        cx.execute(text("""INSERT INTO keywords(site_id,keyword,normalized) VALUES ('one','کفش مردانه','کفش مردانه')"""))
        cx.execute(text("""INSERT INTO keyword_opportunities(site_id,keyword_id,kind,target_url,score,reason,evidence,status)
            VALUES ('one',1,'improve_page','https://one.example/a/',0.9,'بهبود صفحه','{\"impressions\": 90}','new'),
                   ('one',1,'create_content','https://one.example/a/',0.4,'نادیده','{}','dismissed')"""))
        cx.execute(text("""INSERT INTO link_suggestions(site_id,source_node_id,target_node_id,kind,source_url,target_url,score,confidence,status)
            VALUES ('one','src','dst','contextual','https://one.example/a/','https://one.example/b/',0.7,'recommended','new'),
                   ('two','src','dst','contextual','https://two.example/a/','https://two.example/b/',0.7,'recommended','new')"""))

    base = "/api/v1/portfolio/action-inbox"
    all_items = client.get(base).json()
    assert all_items["counts"] == {"issue": 2, "keyword": 1, "link": 2}
    assert all_items["total"] == 5
    one = client.get(base, params={"site_id": "one", "limit": 2}).json()
    assert one["counts"] == {"issue": 1, "keyword": 1, "link": 1}
    assert one["total"] == 3
    assert len(one["items"]) == 2
    assert all(item["site_id"] == "one" for item in one["items"])
    issue = next(item for item in one["items"] if item["kind"] == "issue")
    assert issue["evidence"] == {"count": 0}
    second_page = client.get(base, params={"site_id": "one", "limit": 2, "offset": 2}).json()
    assert len(second_page["items"]) == 1
    keyword = client.get(base, params={"site_id": "one", "kind": "keyword"}).json()
    assert keyword["total"] == 1 and keyword["items"][0]["title"] == "کفش مردانه"
    assert client.get(base, params={"site_id": "missing"}).status_code == 404
