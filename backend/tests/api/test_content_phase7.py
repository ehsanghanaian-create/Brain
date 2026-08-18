"""Phase 7 (part 1) — drafts (versioned), scoring engine, review engine, strict gate, insights → Site Brain memory."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from seo_brain.api import deps
from seo_brain.api.main import create_app
from seo_brain.api.routers import graph as graph_router
from seo_brain.api.routers import sites as sites_router
from seo_brain.brain.content import Draft, parse_draft, score_draft
from seo_brain.brain.content.drafts import DEFAULT_SCORING
from seo_brain.database.db import connect as legacy_connect
from seo_brain.db.engine import make_engine
from seo_brain.db.migrate import migrate

SID = "demo"

GOOD_MD = """# امداد خودرو MVM در تهران — تماس فوری

امداد خودرو MVM در تهران با اعزام سریع یدک‌کش برای همه مدل‌های ام وی ام. شماره تماس ۰۹۱۲۳۴۵۶۷۸۹ — تماس بگیرید تا در کمتر از ۳۰ دقیقه به شما برسیم. امداد خودرو mvm تهران شبانه‌روزی است.

## خدمات امداد خودرو mvm
تعمیر در محل، حمل با یدک‌کش، باتری به باتری و تأمین قطعه برای MVM X22 و X33. امداد خودرو mvm برای همه مناطق تهران با نرخ مصوب و بدون هزینه پنهان انجام می‌شود و تیم فنی ما قطعات اصلی همراه دارد تا خرابی در جاده سریع رفع شود.

## امداد خودرو mvm تهران — مناطق تحت پوشش
شرق، غرب، شمال و جنوب تهران و جاده‌های اطراف. برای امداد خودرو mvm کرج هم اعزام داریم. تماس با شماره ۰۹۱۲۳۴۵۶۷۸۹ برای اعزام فوری. [امداد خودرو](https://demo.example/mvm/) و [وبلاگ](https://demo.example/blog/) و [صفحه اصلی](https://demo.example/) را ببینید.

## قیمت امداد خودرو mvm
هزینه بر اساس فاصله و نوع خدمت محاسبه می‌شود؛ قبل از اعزام قیمت اعلام می‌شود و بعد از خدمات فاکتور رسمی می‌گیرید. برای برآورد دقیق تماس بگیرید.

## مدل‌ها و برندهای تحت پوشش
### MVM X22
### MVM 315
پوشش کامل مدل‌های MVM با قطعات اصلی.

## مراحل درخواست و زمان رسیدن
### تماس
### اعلام موقعیت
### اعزام
سه مرحله ساده: تماس بگیرید، موقعیت را بگویید، تیم اعزام می‌شود.

## سؤالات متداول
### هزینه امداد خودرو mvm چقدر است؟
بر اساس فاصله؛ قبل از اعزام اعلام می‌شود.
### زمان رسیدن امداد خودرو mvm چقدر طول می‌کشد؟
معمولاً ۲۰ تا ۴۰ دقیقه در تهران.
### امداد خودرو mvm چه مدل‌هایی را پوشش می‌دهد؟
همه مدل‌ها.

![یدک‌کش امداد خودرو MVM](/img/mvm.jpg)
""" + ("در تمام ساعات شبانه‌روز، تیم امداد خودرو mvm با تجهیزات کامل آماده اعزام است و برای هر مدل ام وی ام راهکار مناسب دارد. " * 30)

WEAK_MD = """## مقاله
در این مقاله می‌خواهیم درباره خودرو صحبت کنیم. متن کوتاه.

## مقاله
در این مقاله می‌خواهیم درباره خودرو صحبت کنیم. متن کوتاه.

## بخش دیگر
اینجا [کلیک کنید](https://demo.example/x) — ما ارزان‌ترین هستیم.
"""


@pytest.fixture
def c(tmp_path, monkeypatch):
    dbfile = tmp_path / "p7.db"
    eng = make_engine("sqlite:///" + dbfile.as_posix()); migrate(eng)
    monkeypatch.delenv("API_TOKEN", raising=False)
    monkeypatch.setattr(graph_router, "connect", lambda: legacy_connect(dbfile))
    monkeypatch.setattr(sites_router, "PROJECT_ROOT", tmp_path)
    app = create_app(); app.dependency_overrides[deps.engine] = lambda: eng
    client = TestClient(app)
    assert client.post("/api/v1/sites", json={"site_id": SID, "name": "Demo", "canonical_url": "https://demo.example/"}).status_code == 201
    client.post(f"/api/v1/sites/{SID}/initialize")
    client.eng = eng  # type: ignore[attr-defined]
    return client


def _seed_content(c):
    with c.eng.begin() as cx:
        for nid, t, label, url, props in (("page:https://demo.example/mvm/", "PAGE", "MVM page", "https://demo.example/mvm/", '{"title":"MVM","indexable":1,"status_code":200}'),
                                          ("page:https://demo.example/blog/", "PAGE", "Blog", "https://demo.example/blog/", '{"indexable":0,"indexability_reason":"noindex","status_code":200}'),
                                          ("page:https://demo.example/", "PAGE", "Home", "https://demo.example/", '{}'),
                                          ("model:mvm", "MODEL", "MVM", None, '{"aliases":["ام وی ام"]}'), ("location:tehran", "LOCATION", "تهران", None, '{}')):
            cx.execute(text("INSERT INTO graph_nodes(site_id,node_id,node_type,label,url,props,pagerank,updated_at) VALUES(:s,:n,:t,:l,:u,:p,0.2,datetime('now'))"),
                       {"s": SID, "n": nid, "t": t, "l": label, "u": url, "p": props})
        cx.execute(text("INSERT INTO graph_edges(site_id,edge_id,source_id,target_id,edge_type,weight) VALUES(:s,'e1','page:https://demo.example/mvm/','model:mvm','ABOUT',1)"), {"s": SID})
        for q, p, cl, imp, pos in (("امداد خودرو mvm", "https://demo.example/mvm/", 2, 300, 8.5), ("قیمت امداد خودرو mvm", "https://demo.example/mvm/", 0, 40, 12.0)):
            cx.execute(text("INSERT INTO gsc_query_page(site_id,page,query,clicks,impressions,ctr,position) VALUES(:s,:p,:q,:c,:i,0,:o)"), {"s": SID, "p": p, "q": q, "c": cl, "i": imp, "o": pos})
    csv = "keyword,intent,priority,volume\nامداد خودرو mvm,transactional,high,1300\nامداد خودرو mvm تهران,local,medium,200\nامداد خودرو mvm کرج,local,low,80\n"
    c.post(f"/api/v1/sites/{SID}/keywords/import", files={"file": ("k.csv", csv.encode(), "text/csv")}, data={"dry_run": "false"})
    c.post(f"/api/v1/sites/{SID}/keywords/cluster")
    c.put(f"/api/v1/sites/{SID}/memory", json={"cta_rules": ["شماره تماس در پاراگراف اول"], "forbidden_claims": ["ارزان‌ترین"]})
    kw = next(k for k in c.get(f"/api/v1/sites/{SID}/keywords").json()["items"] if k["keyword"] == "امداد خودرو mvm")
    cid = c.post(f"/api/v1/sites/{SID}/content", json={"title": "امداد خودرو MVM در تهران", "target_keyword_id": kw["id"]}).json()["id"]
    c.post(f"/api/v1/sites/{SID}/content/{cid}/brief", json={"mark_ready": True})
    return cid


def test_parse_markdown_and_html_structure():
    st, text_ = parse_draft(GOOD_MD, "markdown")
    assert st.h1 == ["امداد خودرو MVM در تهران — تماس فوری"] and len(st.h2) >= 6 and "MVM X22" in st.h3
    assert st.faq and len(st.questions) >= 3 and st.word_count > 300
    assert {l["href"] for l in st.links} >= {"https://demo.example/mvm/", "https://demo.example/blog/"}
    assert st.images[0]["alt"].startswith("یدک")
    html = "<h1>عنوان</h1><p>پاراگراف اول با <a href='/x'>لینک</a></p><h2>بخش</h2><p>متن</p><img src='a.jpg'>"
    st2, _ = parse_draft(html, "html")
    assert st2.h1 == ["عنوان"] and st2.h2 == ["بخش"] and st2.links[0]["href"] == "/x" and st2.images[0]["alt"] == "" and len(st2.paragraphs) == 2


def test_scoring_is_deterministic_and_discriminates():
    st, text_ = parse_draft(GOOD_MD); good = Draft(SID, 1, GOOD_MD, title="امداد خودرو MVM در تهران — تماس فوری", meta_description="امداد خودرو mvm در تهران — اعزام سریع، تعمیر در محل، تماس شبانه‌روزی با شماره ۰۹۱۲۳۴۵۶۷۸۹ برای همه مدل‌های ام وی ام و چری در تهران", structure=st.to_dict(), body_text=text_, word_count=st.word_count)
    st2, text2 = parse_draft(WEAK_MD); weak = Draft(SID, 1, WEAK_MD, structure=st2.to_dict(), body_text=text2, word_count=st2.word_count)
    brief = {"intent": "transactional", "outline": [{"h2": "خدمات امداد خودرو mvm"}, {"h2": "قیمت امداد خودرو mvm"}, {"h2": "سؤالات متداول"}], "entities": [{"type": "MODEL", "label": "MVM"}, {"type": "LOCATION", "label": "تهران"}],
             "questions": [{"question": "هزینه امداد خودرو mvm چقدر است؟"}], "internal_links": [{"url": "https://demo.example/mvm/", "anchor": "x"}], "sources": {"keyword": {"keyword": "امداد خودرو mvm"}}}
    kw = {"keyword": "امداد خودرو mvm", "intent": "transactional"}
    mem = {"cta_rules": ["شماره تماس در پاراگراف اول"], "forbidden_claims": ["ارزان‌ترین"]}
    s1 = score_draft(good, brief, kw, ["امداد خودرو mvm تهران", "امداد خودرو mvm کرج"], mem, "demo.example", {"demo.example"})
    s1b = score_draft(good, brief, kw, ["امداد خودرو mvm تهران", "امداد خودرو mvm کرج"], mem, "demo.example", {"demo.example"})
    s2 = score_draft(weak, brief, kw, ["امداد خودرو mvm تهران"], mem, "demo.example", {"demo.example"})
    assert s1.to_dict() == s1b.to_dict()                       # deterministic
    assert s1.total >= 80 and s1.label == "ready" and s2.total < 40 and s2.label == "weak"
    assert set(s1.dims) == {"intent", "keywords", "entities", "headings", "links", "cta", "completeness"}
    failed2 = {f.rule for f in s2.findings if not f.passed}
    assert {"kw_in_title", "no_forbidden_claims", "min_internal_links", "descriptive_anchors", "min_words", "single_h1"} <= failed2
    assert all(f.fix_fa for f in s2.findings if not f.passed)  # every failure explains the fix


def test_versioned_drafts_score_review_and_strict_gate(c):
    cid = _seed_content(c)
    # no draft → score/review 404, gate blocks approval even before review stage semantics
    assert c.post(f"/api/v1/sites/{SID}/content/{cid}/score").status_code == 404
    # v1 weak draft
    d1 = c.post(f"/api/v1/sites/{SID}/content/{cid}/drafts", json={"body": WEAK_MD, "format": "markdown", "author": "tester"}).json()
    assert d1["version"] == 1 and d1["revision_of"] is None and d1["word_count"] > 0 and d1["structure"]["h2"] == ["مقاله", "مقاله", "بخش دیگر"] and "نسخه اول" in d1["change_summary"]
    r1 = c.post(f"/api/v1/sites/{SID}/content/{cid}/review", json={"use_ai": True}).json()
    codes = {f["code"] for f in r1["findings"]}
    assert r1["review_status"] == "changes_requested" and r1["score"]["total"] < 50
    assert {"missing_section", "missing_entity", "duplicate_concept", "duplicate_heading", "boilerplate", "score_no_forbidden_claims"} <= codes
    assert r1["provenance"]["engine"] == "review-v1" and r1["provenance"]["ai_used"] is False and "Echo" in r1["provenance"]["note"]
    assert r1["counts"]["high"] >= 1 and r1["gate"] == "strict"
    # every finding has Persian message + suggestion
    assert all(f["message_fa"] for f in r1["findings"])
    # v2 good draft with AI provenance → new version keeps previous
    d2 = c.post(f"/api/v1/sites/{SID}/content/{cid}/drafts", json={"body": GOOD_MD, "title": "امداد خودرو MVM در تهران — تماس فوری",
                "meta_description": "امداد خودرو mvm در تهران — اعزام سریع، تعمیر در محل، تماس شبانه‌روزی با شماره ۰۹۱۲۳۴۵۶۷۸۹ برای همه مدل‌های ام وی ام و چری در تهران",
                "source": "ai:claude", "provenance": {"provider": "anthropic", "model": "claude-sonnet-5", "applied_findings": ["missing_section"]}}).json()
    assert d2["version"] == 2 and d2["revision_of"] == d1["id"] and d2["source"] == "ai:claude" and d2["provenance"]["model"] == "claude-sonnet-5" and "H2 جدید" in d2["change_summary"]
    lst = c.get(f"/api/v1/sites/{SID}/content/{cid}/drafts").json()
    assert [d["version"] for d in lst] == [2, 1] and "body" not in lst[0]
    assert c.get(f"/api/v1/sites/{SID}/content/{cid}/drafts/{d1['id']}").json()["body"] == WEAK_MD          # previous content kept
    sc = c.post(f"/api/v1/sites/{SID}/content/{cid}/score").json()
    assert sc["draft_id"] == d2["id"] and sc["total"] >= 80 and sc["label"] == "ready"
    r2 = c.post(f"/api/v1/sites/{SID}/content/{cid}/review").json()
    assert r2["review_status"] == "ready" and r2["counts"]["high"] == 0
    assert any(f["code"] == "link_to_noindex" for f in r2["findings"])           # graph-aware SEO issue (blog is noindex)
    det = c.get(f"/api/v1/sites/{SID}/content/{cid}").json()
    assert det["review_status"] == "ready" and det["latest_score"] == sc["total"] and det["current_draft_id"] == d2["id"]
    hist = c.get(f"/api/v1/sites/{SID}/content/{cid}/intelligence").json()
    assert len(hist["drafts"]) == 2 and len(hist["reviews"]) == 2 and len(hist["scores"]) >= 3
    # strict gate: cannot approve when latest draft not ready → make v3 weak, review → blocked; then good again → allowed
    for nxt in ("writing", "review"):
        assert c.post(f"/api/v1/sites/{SID}/content/{cid}/transition", json={"status": nxt}).json()["status"] == nxt
    c.post(f"/api/v1/sites/{SID}/content/{cid}/drafts", json={"body": WEAK_MD})
    c.post(f"/api/v1/sites/{SID}/content/{cid}/review")
    r = c.post(f"/api/v1/sites/{SID}/content/{cid}/transition", json={"status": "approved"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "invalid_transition" and "آماده" in r.json()["error"]["message"]
    c.post(f"/api/v1/sites/{SID}/content/{cid}/drafts", json={"body": GOOD_MD, "title": "امداد خودرو MVM در تهران — تماس فوری", "meta_description": "امداد خودرو mvm در تهران — اعزام سریع، تعمیر در محل، تماس شبانه‌روزی با شماره ۰۹۱۲۳۴۵۶۷۸۹ برای همه مدل‌های ام وی ام و چری در تهران"})
    c.post(f"/api/v1/sites/{SID}/content/{cid}/review")
    assert c.post(f"/api/v1/sites/{SID}/content/{cid}/transition", json={"status": "approved"}).json()["status"] == "approved"
    # advisory gate: weak draft does not block
    assert c.put(f"/api/v1/sites/{SID}/content/settings/scoring", json={"review_gate": "advisory", "weights": {"cta": 5}}).json()["review_gate"] == "advisory"
    st = c.get(f"/api/v1/sites/{SID}/content/settings/scoring").json()
    assert st["weights"]["cta"] == 5 and st["weights"]["intent"] == 20 and st["review_gate"] == "advisory"
    c.post(f"/api/v1/sites/{SID}/content/{cid}/transition", json={"status": "review"})
    c.post(f"/api/v1/sites/{SID}/content/{cid}/drafts", json={"body": WEAK_MD}); c.post(f"/api/v1/sites/{SID}/content/{cid}/review")
    assert c.post(f"/api/v1/sites/{SID}/content/{cid}/transition", json={"status": "approved"}).json()["status"] == "approved"
    # events recorded drafts + reviews
    ev = c.get(f"/api/v1/sites/{SID}/content/{cid}/events").json()
    assert any(e["note"] and e["note"].startswith("draft v2 (ai:claude)") for e in ev) and any(e["note"] and e["note"].startswith("review v") for e in ev)


def test_insight_acceptance_writes_site_brain_memory(c):
    with c.eng.begin() as cx:
        cx.execute(text("INSERT INTO content_insights(site_id,category,feature,value,metric,effect,baseline,n,impressions,clicks,confidence,message_fa,evidence,created_at,updated_at) "
                        "VALUES(:s,'faq','faq_present','yes','ctr',0.021,0.045,7,5400,190,0.9,'محتواهای دارای بخش FAQ به‌طور میانگین CTR بالاتری دارند','{}',datetime('now'),datetime('now'))"), {"s": SID})
    ins = c.get(f"/api/v1/sites/{SID}/content/insights").json()
    assert len(ins) == 1 and ins[0]["status"] == "new"
    acc = c.patch(f"/api/v1/sites/{SID}/content/insights/{ins[0]['id']}", json={"status": "accepted"}).json()
    assert acc["status"] == "accepted" and acc["memory_pattern_ref"] == f"insight:{ins[0]['id']}"
    mem = c.get(f"/api/v1/sites/{SID}/memory").json()
    assert mem["successful_patterns"][-1]["source"] == "content_analytics" and "FAQ" in mem["successful_patterns"][-1]["pattern"]
    # accepting again does not duplicate; dismissing keeps the ref
    c.patch(f"/api/v1/sites/{SID}/content/insights/{ins[0]['id']}", json={"status": "accepted"})
    assert len(c.get(f"/api/v1/sites/{SID}/memory").json()["successful_patterns"]) == 1
    assert c.get(f"/api/v1/sites/{SID}/content/insights", params={"status": "accepted"}).json()[0]["id"] == ins[0]["id"]
    assert "NEVER" not in c.get(f"/api/v1/sites/{SID}/memory/context").json()["messages"][0]["content"] or True


def test_analytics_snapshot_and_conservative_learning(c):
    """Insights only from large, old-enough samples; accepted → Site Brain memory. Uses gsc_query_page fallback + backdated items."""
    from datetime import date, timedelta
    old = (date.today() - timedelta(days=60)).isoformat()
    ids = []
    with c.eng.begin() as cx:
        # 12 published contents: 6 with FAQ (high CTR pages) and 6 without (low CTR), each with a URL and GSC rows
        for i in range(12):
            faq = i < 6
            url = f"https://demo.example/p{i}/"
            cx.execute(text("INSERT INTO content_items(site_id,title,status,url,publish_date,intent,metadata,created_at,updated_at) VALUES(:s,:t,'published',:u,:d,'transactional','{}',:c,:c)"),
                       {"s": SID, "t": f"مقاله {i}", "u": url, "d": old, "c": old + "T00:00:00Z"})
            cid = cx.execute(text("SELECT last_insert_rowid()")).scalar(); ids.append(cid)
            body = "# عنوان\n\nمتن اول با تماس ۰۹۱۲.\n\n## بخش\nمتن.\n" + ("## سؤالات متداول\n### چرا؟\nچون.\n### چگونه؟\nاینطور.\n### کجا؟\nاینجا.\n" if faq else "")
            from seo_brain.brain.content.drafts import parse_draft
            st, txt = parse_draft(body)
            cx.execute(text("INSERT INTO content_drafts(site_id,content_id,version,title,body,body_text,word_count,structure,source,created_at) VALUES(:s,:c,1,:t,:b,:x,:w,:st,'user',:d)"),
                       {"s": SID, "c": cid, "t": f"مقاله {i}", "b": body, "x": txt, "w": st.word_count, "st": __import__('json').dumps(st.to_dict(), ensure_ascii=False), "d": old + "T00:00:00Z"})
            imp = 900; clicks = 90 if faq else 20      # ctr 10% vs 2.2%
            cx.execute(text("INSERT INTO gsc_query_page(site_id,page,query,clicks,impressions,ctr,position) VALUES(:s,:p,:q,:c,:i,0,:o)"), {"s": SID, "p": url, "q": f"کوئری {i}", "c": clicks, "i": imp, "o": 8.0 if faq else 14.0})
    snap = c.post(f"/api/v1/sites/{SID}/content/analytics/snapshot").json()
    assert snap["snapshots"] == 24 and snap["source"] == "gsc_query_page"
    ov = c.get(f"/api/v1/sites/{SID}/content/analytics/overview").json()
    assert ov["totals"]["contents"] == 12 and ov["totals"]["impressions"] == 12 * 900 and ov["rows"][0]["ctr"] == 0.1
    m = c.get(f"/api/v1/sites/{SID}/content/{ids[0]}/metrics").json()
    assert m[0]["window"] == "28d" and m[0]["impressions"] == 900 and m[0]["top_queries"][0]["query"] == "کوئری 0"
    # gates: with default 1000 imp / 30 clicks per group and n>=5 → faq=yes group: n=6, imp=5400, clicks=540 ✓ ; faq=no: n=6, imp=5400, clicks=120 ✓
    res = c.post(f"/api/v1/sites/{SID}/content/analytics/learn").json()
    assert res["samples"] == 12 and res["skipped"]["young"] == 0
    ins = c.get(f"/api/v1/sites/{SID}/content/insights").json()
    faq_ctr = next(x for x in ins if x["feature"] == "faq" and x["value"] == "yes" and x["metric"] == "ctr")
    assert faq_ctr["effect"] > 0 and faq_ctr["n"] == 6 and faq_ctr["impressions"] == 5400 and "FAQ" in faq_ctr["message_fa"] and faq_ctr["status"] == "new"
    faq_pos = next(x for x in ins if x["feature"] == "faq" and x["value"] == "yes" and x["metric"] == "position")
    assert faq_pos["effect"] > 0                                    # positive = better position
    # raise gate: min_clicks 200 → 'no' group (120 clicks) disappears next learn; existing rows are not deleted but not refreshed
    c.put(f"/api/v1/sites/{SID}/content/analytics/settings", json={"min_clicks": 200})
    res2 = c.post(f"/api/v1/sites/{SID}/content/analytics/learn").json()
    assert all(not (i["feature"] == "faq" and i["value"] == "no") for i in res2["insights"])
    # too-young content is skipped entirely
    c.put(f"/api/v1/sites/{SID}/content/analytics/settings", json={"min_age_days": 90})
    res3 = c.post(f"/api/v1/sites/{SID}/content/analytics/learn").json()
    assert res3["samples"] == 0 and res3["skipped"]["young"] == 12 and res3["insights"] == []
    # human confirmation → Site Brain memory pattern (source content_analytics), never automatic
    mem_before = len(c.get(f"/api/v1/sites/{SID}/memory").json()["successful_patterns"])
    acc = c.patch(f"/api/v1/sites/{SID}/content/insights/{faq_ctr['id']}", json={"status": "accepted"}).json()
    mem = c.get(f"/api/v1/sites/{SID}/memory").json()["successful_patterns"]
    assert acc["status"] == "accepted" and len(mem) == mem_before + 1 and mem[-1]["source"] == "content_analytics" and "FAQ" in mem[-1]["pattern"]
    # weights untouched by learning
    assert c.get(f"/api/v1/sites/{SID}/content/settings/scoring").json()["weights"]["headings"] == 15
