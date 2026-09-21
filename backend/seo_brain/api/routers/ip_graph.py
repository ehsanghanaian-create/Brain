"""Entry-flow graph: who comes in, from where, to which page, and whether they called.

    source (channel / keyword · campaign)  →  visitor / IP  →  landing page  →  goal (تماس / فرم)

scope=seo  first-party cookieless tracker (track_sessions). It never stores IPs by design, so the middle column is the
           *daily anonymous visitor* hash — operationally the same thing: one device on one day.
scope=ads  ads collector (ads_click_events): real IPs, scored with the dashboard's own click-fraud risk (`_risk_score`).

One read-only snapshot; two grouped queries per scope (top actors, then only their flows) so it stays cheap on big tables.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import unquote

from fastapi import APIRouter, Depends, Query
from sqlalchemy import Engine, bindparam, text

from ..deps import engine
from .ads_data import _attach_geo, _cutoff, _ip_rows, ads_engine

router = APIRouter(prefix="/ip-graph", tags=["ip-graph"])

CHANNEL_FA = {"organic": "جست‌وجوی ارگانیک", "paid": "تبلیغات", "referral": "ارجاعی", "social": "شبکهٔ اجتماعی", "direct": "مستقیم"}
GOAL_FA = {"tel_click": "تماس", "form_submit": "فرم"}
RISK_FA = {"landing_velocity": "ورود پرتکرار از تبلیغ", "landing_velocity_watch": "ورود تکراری (زیر نظر)", "tel_click_burst": "کلیک تماس پشت‌سرهم",
           "many_sessions": "نشست‌های زیاد", "five_minute_burst": "انفجار رویداد در ۵ دقیقه", "ip_not_reliable": "IP قابل اتکا نیست"}
MAX_SOURCES, MAX_PAGES = 8, 10
OTHER_SRC, OTHER_PAGE = "سایر منبع‌ها", "سایر صفحه‌ها"


def _page(p: str | None) -> str:
    s = unquote((p or "/").split("?")[0]).strip() or "/"
    return s if len(s) <= 44 else s[:20] + "…" + s[-22:]


def _assemble(scope: str, site_id: str, hours: int, actors: list[dict[str, Any]], flows: list[tuple[str, str, str, str, int]], stats: dict[str, Any]) -> dict[str, Any]:
    """flows: (actor_id, source_label, page_label, kind, n) with kind in landing | tel_click | form_submit."""
    src_total: Counter[str] = Counter()
    page_total: Counter[str] = Counter()
    for _a, src, page, kind, n in flows:
        if kind == "landing":
            src_total[src] += n
            page_total[page] += n
    keep_src = {k for k, _ in src_total.most_common(MAX_SOURCES)}
    keep_page = {k for k, _ in page_total.most_common(MAX_PAGES)}
    e_src: Counter[tuple[str, str]] = Counter()
    e_page: Counter[tuple[str, str]] = Counter()
    e_goal: Counter[tuple[str, str]] = Counter()
    for a, src, page, kind, n in flows:
        if kind == "landing":
            e_src[(src if src in keep_src else OTHER_SRC, a)] += n
            e_page[(a, page if page in keep_page else OTHER_PAGE)] += n
        elif kind in GOAL_FA:
            e_goal[(a, kind)] += n
    nodes: list[dict[str, Any]] = []
    for label in sorted({s for s, _ in e_src}, key=lambda s: -sum(n for (ss, _), n in e_src.items() if ss == s)):
        nodes.append({"id": f"src:{label}", "kind": "source", "label": label, "sub": None, "status": "ok",
                      "weight": sum(n for (ss, _), n in e_src.items() if ss == label), "meta": {}})
    nodes += [{"id": f"ip:{a['id']}", "kind": "actor", "label": a["label"], "sub": a.get("sub"), "status": a["status"], "weight": a["weight"], "meta": a["meta"]} for a in actors]
    for label in sorted({p for _, p in e_page}, key=lambda p: -sum(n for (_, pp), n in e_page.items() if pp == p)):
        nodes.append({"id": f"page:{label}", "kind": "page", "label": label, "sub": None, "status": "ok",
                      "weight": sum(n for (_, pp), n in e_page.items() if pp == label), "meta": {}})
    for g in sorted({g for _, g in e_goal}):
        nodes.append({"id": f"goal:{g}", "kind": "goal", "label": GOAL_FA[g], "sub": None, "status": "hot",
                      "weight": sum(n for (_, gg), n in e_goal.items() if gg == g), "meta": {}})
    status = {a["id"]: a["status"] for a in actors}
    edges = [{"id": f"s:{s}>{a}", "source": f"src:{s}", "target": f"ip:{a}", "kind": "entry", "weight": n, "status": status.get(a, "ok")} for (s, a), n in e_src.items()]
    edges += [{"id": f"p:{a}>{p}", "source": f"ip:{a}", "target": f"page:{p}", "kind": "landing", "weight": n, "status": status.get(a, "ok")} for (a, p), n in e_page.items()]
    edges += [{"id": f"g:{a}>{g}", "source": f"ip:{a}", "target": f"goal:{g}", "kind": "goal", "weight": n, "status": "hot"} for (a, g), n in e_goal.items()]
    return {"scope": scope, "site_id": site_id, "hours": hours, "nodes": nodes, "edges": edges, "stats": stats,
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")}


def _seo(eng: Engine, site_id: str, hours: int, limit: int) -> dict[str, Any]:
    since = (datetime.now(timezone.utc) - timedelta(hours=hours)).date().isoformat()
    with eng.connect() as cx:
        totals = cx.execute(text("SELECT COUNT(*), COUNT(DISTINCT visitor_id), SUM(CASE WHEN COALESCE(conversion_type,'')<>'' THEN 1 ELSE 0 END) "
                                 "FROM track_sessions WHERE site_id=:s AND day>=:d"), {"s": site_id, "d": since}).one()
        top = cx.execute(text("""
            SELECT visitor_id, COUNT(*) AS sessions, SUM(pages_count) AS pages, MAX(last_seen_at) AS last_seen, MAX(device) AS device,
                   MAX(country) AS country, SUM(CASE WHEN COALESCE(conversion_type,'')<>'' THEN 1 ELSE 0 END) AS conversions,
                   MAX(duration_s) AS duration, MAX(max_scroll) AS scroll
            FROM track_sessions WHERE site_id=:s AND day>=:d GROUP BY visitor_id
            ORDER BY conversions DESC, sessions DESC, pages DESC LIMIT :n"""), {"s": site_id, "d": since, "n": limit}).mappings().all()
        ids = [r["visitor_id"] for r in top]
        rows = cx.execute(text("""
            SELECT visitor_id, channel, search_engine, referrer_host, landing_path, COALESCE(conversion_type,'') AS conv, COUNT(*) AS n
            FROM track_sessions WHERE site_id=:s AND day>=:d AND visitor_id IN :ids GROUP BY 1,2,3,4,5,6""").bindparams(bindparam("ids", expanding=True)),
                          {"s": site_id, "d": since, "ids": ids}).all() if ids else []
    actors = [{"id": r["visitor_id"], "label": f"بازدیدکننده {r['visitor_id'][:6]}", "status": "hot" if r["conversions"] else "ok", "weight": int(r["sessions"]),
               "sub": " · ".join(x for x in (r["device"], r["country"], f"{r['sessions']} نشست") if x),
               "meta": {"visitor_id": r["visitor_id"], "sessions": int(r["sessions"]), "pages": int(r["pages"] or 0), "conversions": int(r["conversions"] or 0),
                        "device": r["device"], "country": r["country"], "last_seen": r["last_seen"], "duration_s": int(r["duration"] or 0), "max_scroll": int(r["scroll"] or 0)}} for r in top]
    flows: list[tuple[str, str, str, str, int]] = []
    for vid, channel, engine_name, ref, landing, conv, n in rows:
        src = f"ارگانیک · {engine_name}" if channel == "organic" and engine_name else f"ارجاعی · {ref}" if channel == "referral" and ref else CHANNEL_FA.get(channel, channel or "مستقیم")
        flows.append((vid, src, _page(landing), "landing", int(n)))
        if conv in GOAL_FA:
            flows.append((vid, src, _page(landing), conv, int(n)))
    return _assemble("seo", site_id, hours, actors, flows, {"sessions": int(totals[0] or 0), "actors_total": int(totals[1] or 0), "conversions": int(totals[2] or 0), "shown": len(actors),
                                                            "note": "ردیاب بدون کوکی IP ذخیره نمی‌کند؛ هر گره یک «بازدیدکنندهٔ ناشناسِ روزانه» است (یک دستگاه در یک روز)."})


def _ads(eng: Engine, site_id: str, hours: int, limit: int) -> dict[str, Any]:
    since = _cutoff(hours)
    with eng.connect() as cx:
        allrows = [r for r in _ip_rows(cx, site_id, since, 5000) if int(r.get("landings") or 0) or int(r.get("tel_clicks") or 0) or int(r.get("form_submits") or 0)]
        allrows.sort(key=lambda r: (-int(r.get("risk_score") or 0), -int(r.get("ads_landings") or 0), -int(r.get("landings") or 0), -int(r.get("events") or 0)))
        top = _attach_geo(allrows[:limit])
        ids = [r["ip_hash"] for r in top]
        rows = cx.execute(text("""
            SELECT ip_hash,
                   COALESCE(NULLIF(keyword,''), NULLIF(utm_term,''), NULLIF(utm_campaign,''), NULLIF(campaign_id,''),
                            CASE WHEN COALESCE(gclid,'')<>'' OR COALESCE(gbraid,'')<>'' OR COALESCE(wbraid,'')<>'' THEN 'Google Ads' ELSE 'بدون نشان تبلیغ' END) AS src,
                   COALESCE(NULLIF(landing_path,''), NULLIF(page_path,''), '/') AS page, event_type, COUNT(*) AS n
            FROM ads_click_events WHERE site_id=:s AND received_at>=:since AND ip_hash IN :ids AND event_type IN ('landing','tel_click','form_submit')
            GROUP BY 1,2,3,4""").bindparams(bindparam("ids", expanding=True)), {"s": site_id, "since": since, "ids": ids}).all() if ids else []
    actors = []
    for r in top:
        risk = int(r.get("risk_score") or 0)
        calls = int(r.get("tel_clicks") or 0)
        actors.append({"id": r["ip_hash"], "label": r["ip_address"], "status": "risk" if risk >= 50 else "watch" if risk >= 15 else "hot" if calls else "ok", "weight": int(r.get("landings") or 0) or 1,
                       "sub": " · ".join(str(x) for x in (r.get("geo_city") or r.get("geo_country"), r.get("geo_isp"), f"ریسک {risk}" if risk else None) if x),
                       "meta": {"ip": r["ip_address"], "events": int(r.get("events") or 0), "sessions": int(r.get("sessions") or 0), "landings": int(r.get("landings") or 0),
                                "ads_landings": int(r.get("ads_landings") or 0), "tel_clicks": calls, "form_submits": int(r.get("form_submits") or 0), "risk_score": risk,
                                "risk_reasons": [RISK_FA.get(x, x) for x in (r.get("risk_reasons") or [])], "first_seen": r.get("first_seen"), "last_seen": r.get("last_seen"),
                                "country": r.get("geo_country"), "city": r.get("geo_city"), "isp": r.get("geo_isp"), "hosting": bool(r.get("geo_hosting")), "proxy": bool(r.get("geo_proxy")),
                                "ads_confirmed": int(r.get("google_ads_confirmed_events") or 0) > 0}})
    flows = [(h, str(src)[:40], _page(page), kind, int(n)) for h, src, page, kind, n in rows]
    return _assemble("ads", site_id, hours, actors, flows, {"actors_total": len(allrows), "shown": len(actors), "risky": sum(1 for r in allrows if int(r.get("risk_score") or 0) >= 50),
                                                            "calls": sum(int(r.get("tel_clicks") or 0) for r in allrows), "landings": sum(int(r.get("landings") or 0) for r in allrows)})


@router.get("")
def ip_graph(scope: str = Query("seo", pattern="^(seo|ads)$"), site_id: str = Query(min_length=2, max_length=120), hours: int = Query(168, ge=1, le=2160),
             limit: int = Query(30, ge=5, le=80), eng: Engine = Depends(engine), ads: Engine = Depends(ads_engine)) -> dict[str, Any]:
    return _ads(ads, site_id, hours, limit) if scope == "ads" else _seo(eng, site_id, hours, limit)
