import json

import pytest
from sqlalchemy import text

from seo_brain.brain.planner.wordpress_reconcile import action_counts, apply_actions, plan_actions
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
    assert action_counts(actions) == {"published": 1, "brief": 1, "existing_link": 0}
    assert reads == [77]
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
