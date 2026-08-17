"""Drive mcp/server.py over stdio with the official MCP client — the same transport Claude Desktop uses.
Requires data/seo.db populated (WP sync + crawl + build-graph). Skips otherwise.
"""
import asyncio
import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
DB = ROOT / "data" / "seo.db"
EXPECTED_TOOLS = {
    "search_graph", "get_node", "get_neighbors", "get_subgraph", "find_path", "find_orphans", "find_cannibalization",
    "find_internal_link_opportunities", "get_gsc_page_data", "get_gsc_query_data", "get_page_seo_data", "get_site_structure",
    "get_categories", "get_models", "get_services", "get_locations", "get_seo_problems", "get_seo_opportunities", "get_site_summary",
}
FORBIDDEN = ("delete", "update", "publish", "edit", "move", "rename", "write", "create", "read_any_file")


def _payload(result):
    sc = getattr(result, "structured_content", None) or getattr(result, "structuredContent", None)
    if sc is not None:
        return sc["result"] if isinstance(sc, dict) and set(sc) == {"result"} else sc
    for c in result.content:
        if getattr(c, "type", "") == "text":
            try:
                return json.loads(c.text)
            except json.JSONDecodeError:
                return c.text
    return None


async def _session_run(fn):
    from mcp.client.session import ClientSession
    from mcp.client.stdio import StdioServerParameters, stdio_client
    params = StdioServerParameters(command=sys.executable, args=[str(ROOT / "backend" / "mcp_server" / "server.py")], env={**os.environ, "PYTHONUTF8": "1", "SEO_KG_ROOT": str(ROOT)})
    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()
            return await fn(s)


@pytest.mark.skipif(not DB.exists(), reason="database not built")
def test_tools_list_and_readonly_names():
    async def go(s):
        return await s.list_tools()
    res = asyncio.run(_session_run(go))
    names = {t.name for t in res.tools}
    assert EXPECTED_TOOLS <= names, EXPECTED_TOOLS - names
    for n in names:
        assert not any(f in n for f in FORBIDDEN), n
    for t in res.tools:
        assert t.annotations is not None and getattr(t.annotations, "read_only_hint", getattr(t.annotations, "readOnlyHint", None)) is True, t.name


@pytest.mark.skipif(not DB.exists(), reason="database not built")
def test_site_summary_and_orphans_and_structure():
    async def go(s):
        out = {}
        out["summary"] = _payload(await s.call_tool("get_site_summary", {}))
        out["orphans"] = _payload(await s.call_tool("find_orphans", {}))
        out["structure"] = _payload(await s.call_tool("get_site_structure", {}))
        out["gsc"] = _payload(await s.call_tool("get_gsc_page_data", {"min_position": 4, "max_position": 15}))
        out["cann"] = _payload(await s.call_tool("find_cannibalization", {}))
        out["models"] = _payload(await s.call_tool("get_models", {}))
        return out
    out = asyncio.run(_session_run(go))
    s = out["summary"]
    assert s["read_only"] is True and s["counts"]["crawled_urls"] > 0 and s["counts"]["wp_posts"] > 0
    assert isinstance(out["orphans"], list)
    st = out["structure"]
    assert st["category_tree"] and st["pages"]
    assert out["gsc"]["status"] in ("OK", "NO_GSC_DATA")
    assert isinstance(out["models"], list) and out["models"][0]["name"]


@pytest.mark.skipif(not DB.exists(), reason="database not built")
def test_no_secrets_in_any_tool_output():
    async def go(s):
        blobs = []
        for name in ("get_site_summary", "get_site_structure", "get_seo_problems", "get_seo_opportunities", "get_categories"):
            blobs.append(json.dumps(_payload(await s.call_tool(name, {})), ensure_ascii=False))
        blobs.append(json.dumps(_payload(await s.call_tool("search_graph", {"query": "امداد"})), ensure_ascii=False))
        return "\n".join(blobs)
    text = asyncio.run(_session_run(go))
    for key in ("WP_APP_PASSWORD", "GOOGLE_CLIENT_SECRET", "OBSIDIAN_API_KEY", "refresh_token", "client_secret"):
        assert key not in text
    for envk in ("WP_APP_PASSWORD", "GOOGLE_CLIENT_SECRET", "OBSIDIAN_API_KEY"):
        v = os.environ.get(envk)
        if v and len(v) > 3:
            assert v not in text
