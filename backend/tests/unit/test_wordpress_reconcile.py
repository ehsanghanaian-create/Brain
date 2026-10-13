import json
import sqlite3

import httpx
import pytest
from sqlalchemy import text

from seo_brain.brain.planner.wordpress_reconcile import action_counts, apply_actions, apply_with_backup, live_actions, plan_actions
from seo_brain.db.engine import make_engine
from seo_brain.db.migrate import migrate


def test_reconcile_live_article_and_unpublished_brief_without_wordpress_write(tmp_path):
    engine = make_engine("sqlite:///" + (tmp_path / "reconcile.db").as_posix())
    migrate(engine)
    with engine.begin() as cx:
        cx.execute(text("INSERT INTO sites(site_id,name,canonical_url,wp_url,created_at,updated_at) VALUES('demo','Demo','https://demo.example/','https://api.demo.example','now','now')"))
        cx.execute(text("""INSERT INTO content_plans(site_id,title,url,primary_keyword,status,created_at,updated_at)
            VALUES('demo','Published guide','https://demo.example/blog/guide-a','guide a','review','now','now')"""))
        cx.execute(text("""INSERT INTO content_plans(site_id,title,url,primary_keyword,status,heading_structure,created_at,updated_at)
            VALUES('demo','Future guide','https://demo.example/blog/guide-b','guide b','review',:heading,'now','now')"""),
            {"heading": json.dumps([{"level": 2, "text": "Useful outline"}])})
    post = {"id": 77, "slug": "guide-a", "status": "publish", "link": "https://demo.example/2026/guide-a/", "modified_gmt": "2026-10-13T00:00:00"}
    reads = []

    def fetch(post_id):
        reads.append(post_id)
        return {**post, "title": {"raw": "Published guide"}, "content": {"raw": "<h2>Useful guide</h2><p>" + "word " * 340 + "</p>"}, "excerpt": {"raw": "Summary"}}

    actions = plan_actions(engine, "demo", [post], fetch)
    assert action_counts(actions) == {"published": 1, "brief": 1, "linked_published": 0, "existing_link": 0}
    assert reads == [77]
    requests = []

    def wordpress_get(request):
        requests.append((request.method, request.url.path))
        if request.url.path.endswith("/posts"):
            return httpx.Response(200, json=[post], headers={"x-wp-totalpages": "1"})
        if request.url.path.endswith("/posts/77"):
            return httpx.Response(200, json=fetch(77))
        return httpx.Response(404)

    with httpx.Client(transport=httpx.MockTransport(wordpress_get)) as client:
        live, post_count = live_actions(engine, "demo", client)
    assert post_count == 1 and action_counts(live) == action_counts(actions)
    assert requests == [("GET", "/wp-json/wp/v2/posts"), ("GET", "/wp-json/wp/v2/posts/77")]
    with pytest.raises(ValueError, match="unexpected reconciliation counts"):
        apply_actions(engine, "demo", actions, expected={"published": 2})
    assert apply_actions(engine, "demo", actions, expected={"published": 1, "brief": 1})["brief"] == 1
    with engine.connect() as cx:
        plans = cx.execute(text("SELECT status,content_item_id,publishing FROM content_plans ORDER BY id")).all()
        items = cx.execute(text("SELECT status,wp_post_id,current_draft_id,brief_id FROM content_items ORDER BY id")).all()
        drafts = cx.execute(text("SELECT format,source,review_status,word_count FROM content_drafts")).all()
    assert [r[0] for r in plans] == ["published", "brief_ready"]
    assert all(r[1] for r in plans)
    assert json.loads(plans[0][2])["wp_post_id"] == 77
    assert items[0][0] == "published" and items[0][1] == 77 and items[0][2]
    assert items[1][0] == "brief_ready" and items[1][3]
    assert drafts[0][0:3] == ("html", "wordpress:import", "none") and drafts[0][3] >= 300
    assert action_counts(plan_actions(engine, "demo", [post], fetch))["existing_link"] == 2

    new_post = {"id": 78, "slug": "guide-b", "status": "publish",
                "link": "https://demo.example/2026/guide-b/", "modified_gmt": "2026-10-13T08:30:00"}

    def fetch_new(post_id):
        assert post_id == 78
        return {**new_post, "title": {"raw": "Future guide"},
                "content": {"raw": "<h2>New live guide</h2><p>" + "word " * 340 + "</p>"},
                "excerpt": {"raw": "New summary"}}

    update = plan_actions(engine, "demo", [post, new_post], fetch_new)
    assert action_counts(update) == {"published": 0, "brief": 0, "linked_published": 1, "existing_link": 1}
    applied = apply_with_backup(engine, "demo", update, tmp_path / "backups")
    assert applied["actions"]["linked_published"] == 1 and applied["applied"] == 1
    with sqlite3.connect(applied["backup"]) as snapshot:
        assert snapshot.execute("PRAGMA quick_check").fetchone()[0] == "ok"
        assert snapshot.execute("SELECT status FROM content_plans WHERE id=2").fetchone()[0] == "brief_ready"
    with engine.connect() as cx:
        updated = cx.execute(text("SELECT status,content_item_id,publishing FROM content_plans WHERE id=2")).one()
        item = cx.execute(text("SELECT status,wp_post_id,current_draft_id,brief_id FROM content_items WHERE id=:i"),
                          {"i": updated[1]}).one()
        draft_count = cx.execute(text("SELECT COUNT(*) FROM content_drafts WHERE content_id=:i"),
                                 {"i": updated[1]}).scalar()
    assert updated[0] == "published" and json.loads(updated[2])["wp_post_id"] == 78
    assert item[0] == "published" and item[1] == 78 and item[2] and item[3]
    assert draft_count == 1
    assert apply_with_backup(engine, "demo", plan_actions(engine, "demo", [post, new_post], fetch_new),
                             tmp_path / "backups")["backup"] is None
