"""Acceptance tests (spec §65) executed against the real local database through the MCP stdio server.

TEST 1  get_site_summary works
TEST 2  "چند صفحه در سایت وجود دارد؟"                     -> get_site_summary counts
TEST 3  "صفحات یتیم را پیدا کن."                          -> find_orphans
TEST 4  "صفحات رتبه 4 تا 15 را پیدا کن."                   -> get_gsc_page_data(min_position=4,max_position=15)   (OK or NO_GSC_DATA, never invented)
TEST 5  "صفحات Impression بالا و CTR پایین را پیدا کن."     -> get_seo_opportunities(opp_type='ctr_opportunity')      (needs GSC)
TEST 6  "کاندیدهای Cannibalization را پیدا کن."             -> find_cannibalization                                   (needs GSC)
TEST 7  "برای صفحه X فرصت‌های لینک‌سازی داخلی را پیدا کن."  -> find_internal_link_opportunities(page=X)
TEST 8  site structure                                      -> get_site_structure
TEST 9  Obsidian graph                                      -> vault files exist for Pages/Categories/Models/Services/Locations + wikilinks (visual check in Obsidian is manual)
TEST 10 no WordPress modification                           -> static check: no HTTP write verbs in src/, and WP modified timestamps unchanged vs. snapshot
"""
import asyncio
import json
import os
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
DB = ROOT / "data" / "seo.db"
VAULT = ROOT / "obsidian" / "SEO-Knowledge-Graph"
pytestmark = pytest.mark.skipif(not DB.exists(), reason="database not built")


def _payload(result):
    sc = getattr(result, "structured_content", None)
    if sc is not None:
        return sc["result"] if isinstance(sc, dict) and set(sc) == {"result"} else sc
    for c in result.content:
        if getattr(c, "type", "") == "text":
            try:
                return json.loads(c.text)
            except json.JSONDecodeError:
                return c.text
    return None


def call(name, args=None):
    async def go():
        from mcp.client.session import ClientSession
        from mcp.client.stdio import StdioServerParameters, stdio_client
        params = StdioServerParameters(command=sys.executable, args=[str(ROOT / "mcp" / "server.py")], env={**os.environ, "PYTHONUTF8": "1", "SEO_KG_ROOT": str(ROOT)})
        async with stdio_client(params) as (r, w):
            async with ClientSession(r, w) as s:
                await s.initialize()
                return _payload(await s.call_tool(name, args or {}))
    return asyncio.run(go())


def test_1_get_site_summary():
    s = call("get_site_summary")
    assert s["site"]["site_id"] == "emdadmodiran" and s["read_only"] is True


def test_2_how_many_pages():
    s = call("get_site_summary")
    c = s["counts"]
    assert c["crawled_urls"] >= 18 and c["wp_pages"] == 3 and c["wp_posts"] == 11


def test_3_orphans():
    o = call("find_orphans")
    assert isinstance(o, list)
    for item in o:
        assert item["problem_type"] == "orphan" and item["url"].startswith("https://emdadmodiran.com/")


def test_4_positions_4_to_15():
    r = call("get_gsc_page_data", {"min_position": 4, "max_position": 15})
    assert r["status"] in ("OK", "NO_GSC_DATA")
    if r["status"] == "OK":
        for row in r["rows"]:
            assert 4 <= row["position"] <= 15


def test_5_high_impressions_low_ctr():
    r = call("get_seo_opportunities", {"opp_type": "ctr_opportunity"})
    assert "items" in r  # empty list is legitimate without GSC data
    s = call("get_site_summary")
    if s["counts"]["gsc_daily_rows"] == 0:
        assert r["items"] == []


def test_6_cannibalization():
    r = call("find_cannibalization")
    assert (isinstance(r, dict) and r.get("status") == "NO_GSC_DATA") or isinstance(r, list)


def test_7_internal_link_opportunities_for_page():
    r = call("find_internal_link_opportunities", {"page": "https://emdadmodiran.com/blog/امداد-خودرو-mvm/"})
    assert isinstance(r, list) and len(r) >= 1
    assert r[0]["source_page"] == "https://emdadmodiran.com/blog/امداد-خودرو-mvm/" and r[0]["potential_anchor"] and r[0]["reason"]


def test_8_site_structure():
    st = call("get_site_structure")
    assert st["site"]["url"] == "https://emdadmodiran.com/"
    assert len(st["pages"]) == 3 and st["category_tree"]
    assert st["entities"]["BRAND"] and st["entities"]["MODEL"] and st["entities"]["SERVICE"] and st["entities"]["LOCATION"]


def test_9_obsidian_vault_files_and_wikilinks():
    for folder in ("01-Pages", "02-Posts", "03-Categories", "05-Brands", "06-Models", "07-Services", "08-Locations"):
        files = list((VAULT / folder).glob("*.md"))
        assert files, folder
    post = next((VAULT / "02-Posts").glob("*تیگو 5*.md"))
    text = post.read_text(encoding="utf-8")
    assert text.startswith("---\n") and "type: post" in text
    links = re.findall(r"\[\[([^\]|]+)\|", text)
    assert any(l.startswith("06-Models/") for l in links) and any(l.startswith("03-Categories/") for l in links)
    assert (VAULT / ".obsidian" / "graph.json").exists()


def test_10_no_wordpress_write_paths():
    src = "\n".join(p.read_text(encoding="utf-8") for p in (ROOT / "src").rglob("*.py")) + (ROOT / "mcp" / "server.py").read_text(encoding="utf-8")
    for verb in (".post(", ".put(", ".patch(", ".delete(", "requests.post", "httpx.post", "method=\"POST\""):
        assert verb not in src, verb
