"""Daily, source-labelled organic SERP snapshots, separate from GSC average position."""
from __future__ import annotations

import base64
import json
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import Engine, text

from ..common.config import env
from ..db.repositories.base import utcnow

log = logging.getLogger("analysis.serp_rank")
try:
    TZ = ZoneInfo("Asia/Tehran")
except ZoneInfoNotFoundError:  # Windows may not ship IANA tzdata; Iran has used UTC+03:30 since 2022.
    TZ = timezone(timedelta(hours=3, minutes=30))
DEFAULTS = {"enabled": True, "provider": "serpkite", "market": "ir", "language": "fa",
            "device": "mobile", "depth": 10, "daily_hour": 6, "max_keywords_per_run": 30}


class ProviderError(Exception):
    def __init__(self, code: str, *, stop_run: bool = False):
        super().__init__(code)
        self.code = code
        self.stop_run = stop_run


@dataclass(frozen=True)
class SerpResult:
    organic: list[dict]
    task_id: str | None


def _secret(name: str) -> str:
    return (env(name, "") or "").strip()


def provider_ready(provider: str) -> bool:
    if provider == "serpkite":
        return bool(_secret("SERPKITE_API_KEY"))
    if provider == "serpapi":
        return bool(_secret("SERPAPI_API_KEY"))
    if provider == "dataforseo":
        return bool(_secret("DATAFORSEO_LOGIN") and _secret("DATAFORSEO_PASSWORD"))
    return False


def settings(engine: Engine, site_id: str) -> dict:
    with engine.connect() as cx:
        value = cx.execute(text("SELECT value FROM site_settings WHERE site_id=:s AND key='serp_rank'"),
                           {"s": site_id}).scalar()
    try:
        stored = json.loads(value) if value else {}
    except (ValueError, TypeError):
        stored = {}
    cfg = {**DEFAULTS, **{k: v for k, v in stored.items() if k in DEFAULTS}}
    if cfg["provider"] not in ("serpkite", "serpapi", "dataforseo"):
        cfg["provider"] = DEFAULTS["provider"]
    if cfg["market"] != "ir" or cfg["language"] != "fa":
        # First release is deliberately scoped to the Iranian Persian market.
        cfg["market"], cfg["language"] = "ir", "fa"
    if cfg["device"] not in ("mobile", "desktop"):
        cfg["device"] = "mobile"
    for key, low, high in (("depth", 10, 50), ("max_keywords_per_run", 1, 5000), ("daily_hour", 0, 23)):
        try:
            cfg[key] = min(high, max(low, int(cfg[key])))
        except (ValueError, TypeError):
            cfg[key] = DEFAULTS[key]
    cfg["provider_ready"] = provider_ready(cfg["provider"])
    cfg["timezone"] = "Asia/Tehran"
    return cfg


def save_settings(engine: Engine, site_id: str, *, provider: str, device: str, depth: int,
                  max_keywords_per_run: int, enabled: bool) -> dict:
    if provider not in ("serpkite", "serpapi", "dataforseo") or device not in ("mobile", "desktop"):
        raise ValueError("invalid_rank_settings")
    if depth not in (10, 20, 30, 50) or not 1 <= max_keywords_per_run <= 5000:
        raise ValueError("invalid_rank_settings")
    value = {"provider": provider, "device": device, "depth": depth,
             "max_keywords_per_run": max_keywords_per_run, "enabled": enabled,
             "market": "ir", "language": "fa", "daily_hour": 6}
    with engine.begin() as cx:
        cx.execute(text("""INSERT INTO site_settings(site_id,key,value,updated_at)
          VALUES(:s,'serp_rank',:v,:u) ON CONFLICT(site_id,key)
          DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at"""),
          {"s": site_id, "v": json.dumps(value), "u": utcnow()})
    return settings(engine, site_id)


def _host(url: str) -> str:
    host = (urlsplit(url).hostname or "").lower().rstrip(".")
    try:
        return host.encode("idna").decode("ascii").removeprefix("www.")
    except UnicodeError:
        return ""


def _owned(url: str, domain: str) -> bool:
    host = _host(url)
    return bool(host and (host == domain or host.endswith("." + domain)))


def _fetch_json(request: Request) -> dict:
    try:
        with urlopen(request, timeout=35) as response:
            raw = response.read(2_000_001)
    except HTTPError as error:
        try:
            detail = json.loads(error.read(4096))
            provider_code = str((detail.get("error") or {}).get("code") or "")
        except (ValueError, AttributeError, TypeError):
            provider_code = ""
        if error.code in (402, 429) or provider_code in (
                "key_limit_reached", "spend_cap_reached", "daily_limit_reached", "insufficient_credits"):
            raise ProviderError("provider_quota_or_rate_limit", stop_run=True) from None
        if error.code in (401, 403):
            raise ProviderError("provider_auth_failed", stop_run=True) from None
        raise ProviderError("provider_http_error", stop_run=error.code >= 500) from None
    except (URLError, TimeoutError):
        raise ProviderError("provider_network_error") from None
    if len(raw) > 2_000_000:
        raise ProviderError("provider_response_too_large")
    try:
        return json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        raise ProviderError("provider_invalid_json") from None


def fetch_serp(keyword: str, cfg: dict) -> SerpResult:
    """One paid provider task per keyword. No direct Google scraping or GSC substitution."""
    if cfg["provider"] == "serpkite":
        key = _secret("SERPKITE_API_KEY")
        if not key:
            raise ProviderError("provider_not_configured", stop_run=True)
        payload = {"q": keyword, "country": "ir", "language": "fa", "device": cfg["device"],
                   "num": cfg["depth"], "page": 1, "engine": "google",
                   "fields": "results.position,results.link,results.domain"}
        request = Request("https://api.serpkite.com/v1/search",
                          data=json.dumps(payload, ensure_ascii=False).encode(), method="POST",
                          headers={"Authorization": "Bearer " + key, "Content-Type": "application/json",
                                   "Accept": "application/json", "User-Agent": "SEO-Brain/1.0"})
        data = _fetch_json(request)
        rows = data.get("results")
        meta = data.get("meta") or {}
        if not isinstance(rows, list):
            raise ProviderError("provider_missing_organic_results")
        if meta.get("parse_quality") == "empty":
            # A provider returning no SERP cannot establish that our site is outside the top N.
            raise ProviderError("provider_empty_results")
        if meta.get("parse_quality") not in (None, "ok"):
            raise ProviderError("provider_incomplete_response")
        organic = [{"position": item["position"], "absolute_position": item["position"],
                    "url": item["link"]} for item in rows
                   if isinstance(item, dict) and isinstance(item.get("position"), int)
                   and isinstance(item.get("link"), str) and item["link"].startswith("https://")]
        return SerpResult(organic[:cfg["depth"]], str(meta.get("request_id") or "") or None)
    if cfg["provider"] == "serpapi":
        key = _secret("SERPAPI_API_KEY")
        if not key:
            raise ProviderError("provider_not_configured", stop_run=True)
        params = {"engine": "google", "q": keyword, "gl": "ir", "hl": "fa",
                  "device": cfg["device"], "num": cfg["depth"], "output": "json", "api_key": key}
        request = Request("https://serpapi.com/search.json?" + urlencode(params),
                          headers={"Accept": "application/json", "User-Agent": "SEO-Brain/1.0"})
        data = _fetch_json(request)
        if data.get("error"):
            raise ProviderError("provider_rejected_request", stop_run=True)
        metadata = data.get("search_metadata") or {}
        if metadata.get("status") not in (None, "Success"):
            raise ProviderError("provider_incomplete_response")
        rows = data.get("organic_results")
        if not isinstance(rows, list):
            raise ProviderError("provider_missing_organic_results")
        organic = [{"position": int(item["position"]), "absolute_position": int(item["position"]),
                    "url": str(item["link"])} for item in rows
                   if isinstance(item, dict) and isinstance(item.get("position"), int)
                   and isinstance(item.get("link"), str) and item["link"].startswith("https://")]
        return SerpResult(organic[:cfg["depth"]], str(metadata.get("id") or "") or None)
    if cfg["provider"] == "dataforseo":
        login, password = _secret("DATAFORSEO_LOGIN"), _secret("DATAFORSEO_PASSWORD")
        if not login or not password:
            raise ProviderError("provider_not_configured", stop_run=True)
        auth = base64.b64encode(f"{login}:{password}".encode()).decode()
        payload = [{"keyword": keyword, "location_name": "Iran", "language_code": "fa",
                    "device": cfg["device"], "depth": cfg["depth"]}]
        request = Request("https://api.dataforseo.com/v3/serp/google/organic/live/advanced",
                          data=json.dumps(payload, ensure_ascii=False).encode(), method="POST",
                          headers={"Authorization": "Basic " + auth, "Content-Type": "application/json",
                                   "Accept": "application/json", "User-Agent": "SEO-Brain/1.0"})
        data = _fetch_json(request)
        tasks = data.get("tasks") or []
        task = tasks[0] if tasks else {}
        if data.get("status_code") != 20000 or task.get("status_code") != 20000:
            raise ProviderError("provider_rejected_request", stop_run=True)
        result = (task.get("result") or [{}])[0] or {}
        items = result.get("items")
        if not isinstance(items, list):
            raise ProviderError("provider_missing_organic_results")
        organic = [{"position": int(item["rank_group"]),
                    "absolute_position": int(item.get("rank_absolute") or item["rank_group"]),
                    "url": str(item["url"])} for item in items
                   if isinstance(item, dict) and item.get("type") == "organic"
                   and isinstance(item.get("rank_group"), int)
                   and isinstance(item.get("url"), str) and item["url"].startswith("https://")]
        return SerpResult(organic[:cfg["depth"]], str(task.get("id") or "") or None)
    raise ProviderError("provider_unsupported", stop_run=True)


def _date(now: datetime | None = None) -> str:
    return (now or datetime.now(timezone.utc)).astimezone(TZ).date().isoformat()


def due(engine: Engine, site_id: str, now: datetime | None = None) -> bool:
    now = now or datetime.now(timezone.utc)
    cfg = settings(engine, site_id)
    if not cfg["enabled"] or not cfg["provider_ready"] or now.astimezone(TZ).hour < cfg["daily_hour"]:
        return False
    with engine.connect() as cx:
        exists = cx.execute(text("SELECT 1 FROM serp_rank_runs WHERE site_id=:s AND local_date=:d"),
                            {"s": site_id, "d": _date(now)}).first()
    return not bool(exists)


def create_run(engine: Engine, site_id: str, now: datetime | None = None) -> dict:
    cfg = settings(engine, site_id)
    if not cfg["provider_ready"]:
        return {"status": "needs_provider"}
    if not cfg["enabled"]:
        return {"status": "disabled"}
    day = _date(now)
    with engine.begin() as cx:
        existing = cx.execute(text("SELECT id,status FROM serp_rank_runs WHERE site_id=:s AND local_date=:d"),
                              {"s": site_id, "d": day}).mappings().first()
        if existing:
            return {"status": "already_scheduled", "run_id": existing["id"], "run_status": existing["status"]}
        count = cx.execute(text("SELECT COUNT(*) FROM keywords WHERE site_id=:s AND status!='ignored'"),
                           {"s": site_id}).scalar() or 0
        result = cx.execute(text("""INSERT INTO serp_rank_runs
          (site_id,local_date,timezone,provider,market,language,device,requested_depth,keywords_total)
          VALUES(:s,:d,'Asia/Tehran',:p,'ir','fa',:dev,:depth,:total)"""),
          {"s": site_id, "d": day, "p": cfg["provider"], "dev": cfg["device"],
           "depth": cfg["depth"], "total": count})
        return {"status": "queued", "run_id": int(result.lastrowid), "keywords_total": count,
                "request_cap": cfg["max_keywords_per_run"]}


def execute_run(engine: Engine, site_id: str, run_id: int, fetch=fetch_serp) -> dict:
    with engine.connect() as cx:
        run = cx.execute(text("SELECT * FROM serp_rank_runs WHERE id=:i AND site_id=:s"),
                         {"i": run_id, "s": site_id}).mappings().first()
        domain = _host(cx.execute(text("SELECT canonical_url FROM sites WHERE site_id=:s"),
                                  {"s": site_id}).scalar() or "")
    if not run or not domain:
        raise ValueError("rank_run_or_site_missing")
    if run["status"] in ("succeeded", "partial", "blocked"):
        return {"run_id": run_id, "status": run["status"]}
    cfg = settings(engine, site_id)
    # A saved run retains its original provider, device and depth even if settings change mid-run.
    cfg.update({"provider": run["provider"], "device": run["device"], "depth": run["requested_depth"]})
    with engine.begin() as cx:
        cx.execute(text("UPDATE serp_rank_runs SET status='running',started_at=COALESCE(started_at,:now) WHERE id=:i"),
                   {"now": utcnow(), "i": run_id})
    with engine.connect() as cx:
        keywords = cx.execute(text("""SELECT id,keyword,target_url FROM keywords WHERE site_id=:s AND status!='ignored'
          AND id NOT IN (SELECT keyword_id FROM serp_rank_observations WHERE run_id=:r)
          ORDER BY COALESCE((SELECT MAX(o.checked_at) FROM serp_rank_observations o
                             WHERE o.site_id=keywords.site_id AND o.keyword_id=keywords.id), ''), id"""),
          {"s": site_id, "r": run_id}).mappings().all()
    with engine.connect() as cx:
        recent = cx.execute(text("""SELECT status FROM serp_rank_observations
          WHERE run_id=:r ORDER BY id DESC LIMIT 3"""), {"r": run_id}).scalars().all()
    consecutive_errors = 0
    for status in recent:
        if status != "provider_error":
            break
        consecutive_errors += 1
    stopped = "provider_repeated_errors" if consecutive_errors >= 3 else None
    for row in keywords:
        if stopped:
            break
        with engine.connect() as cx:
            requests = cx.execute(text("SELECT provider_requests FROM serp_rank_runs WHERE id=:i"),
                                  {"i": run_id}).scalar() or 0
        if requests >= cfg["max_keywords_per_run"]:
            stopped = "daily_request_cap_reached"
            break
        try:
            snapshot = fetch(row["keyword"], cfg)
            own = [item for item in snapshot.organic if _owned(item["url"], domain)]
            best = min(own, key=lambda item: item["position"]) if own else None
            competitors = [{"position": item["position"], "url": item["url"], "domain": _host(item["url"])}
                           for item in snapshot.organic if not _owned(item["url"], domain)][:5]
            values = {"status": "found" if best else "not_found_in_results",
                      "position": best["position"] if best else None,
                      "absolute": best["absolute_position"] if best else None,
                      "ranking_url": best["url"] if best else None,
                      "count": len(snapshot.organic), "competitors": json.dumps(competitors, ensure_ascii=False),
                      "task_id": snapshot.task_id, "error": None}
            consecutive_errors = 0
        except ProviderError as error:
            values = {"status": "provider_error", "position": None, "absolute": None,
                      "ranking_url": None, "count": 0, "competitors": "[]", "task_id": None,
                      "error": error.code}
            consecutive_errors += 1
            if error.stop_run:
                stopped = error.code
            elif consecutive_errors >= 3:
                stopped = "provider_repeated_errors"
        with engine.begin() as cx:
            cx.execute(text("""INSERT OR IGNORE INTO serp_rank_observations
              (run_id,site_id,keyword_id,keyword,status,organic_position,absolute_position,
               ranking_url,target_url,returned_organic_count,competitors_json,provider_task_id,error_code,checked_at)
              VALUES(:r,:s,:k,:keyword,:status,:position,:absolute,:ranking_url,:target,:count,
                     :competitors,:task_id,:error,:now)"""),
              {"r": run_id, "s": site_id, "k": row["id"], "keyword": row["keyword"],
               "target": row["target_url"], "now": utcnow(), **values})
            cx.execute(text("""UPDATE serp_rank_runs SET provider_requests=provider_requests+1,
              keywords_checked=(SELECT COUNT(*) FROM serp_rank_observations WHERE run_id=:i),
              keywords_failed=(SELECT COUNT(*) FROM serp_rank_observations WHERE run_id=:i AND status='provider_error')
              WHERE id=:i"""), {"i": run_id})
        if stopped:
            break
        time.sleep(0.2)
    with engine.begin() as cx:
        current = cx.execute(text("SELECT keywords_total,keywords_checked,keywords_failed FROM serp_rank_runs WHERE id=:i"),
                             {"i": run_id}).first()
        status = "blocked" if stopped and stopped != "daily_request_cap_reached" else (
                 "partial" if stopped or current[1] < current[0] or current[2] else "succeeded")
        cx.execute(text("UPDATE serp_rank_runs SET status=:st,error_code=:error,finished_at=:now WHERE id=:i"),
                   {"st": status, "error": stopped, "now": utcnow(), "i": run_id})
    return {"run_id": run_id, "status": status, "checked": current[1],
            "total": current[0], "failed": current[2], "error_code": stopped}


def overview(engine: Engine, site_id: str, days: int = 30) -> dict:
    cfg = settings(engine, site_id)
    with engine.connect() as cx:
        total = cx.execute(text("SELECT COUNT(*) FROM keywords WHERE site_id=:s AND status!='ignored'"),
                           {"s": site_id}).scalar() or 0
        runs = [dict(row) for row in cx.execute(text("""SELECT id,local_date,provider,market,language,device,
          requested_depth,status,keywords_total,keywords_checked,keywords_failed,provider_requests,
          started_at,finished_at,error_code FROM serp_rank_runs WHERE site_id=:s
          ORDER BY local_date DESC LIMIT :days"""), {"s": site_id, "days": days}).mappings()]
        rows = [dict(row) for row in cx.execute(text("""SELECT k.id keyword_id,k.keyword,k.priority,k.target_url,
          o.status,o.organic_position,o.absolute_position,o.ranking_url,o.returned_organic_count,
          o.competitors_json,o.checked_at,r.local_date,r.provider,r.device,r.requested_depth,
          r.market,r.language FROM keywords k
          LEFT JOIN serp_rank_observations o ON o.id=(
            SELECT o2.id FROM serp_rank_observations o2 JOIN serp_rank_runs r2 ON r2.id=o2.run_id
            WHERE o2.site_id=k.site_id AND o2.keyword_id=k.id
              AND o2.status IN ('found','not_found_in_results')
              AND r2.status IN ('succeeded','partial','blocked')
            ORDER BY r2.local_date DESC,o2.id DESC LIMIT 1)
          LEFT JOIN serp_rank_runs r ON r.id=o.run_id
          WHERE k.site_id=:s AND k.status!='ignored' ORDER BY k.id"""), {"s": site_id}).mappings()]
        history = [dict(row) for row in cx.execute(text("""SELECT o.keyword_id,r.local_date,o.organic_position,
          o.status FROM serp_rank_observations o JOIN serp_rank_runs r ON r.id=o.run_id
          WHERE o.site_id=:s AND o.status IN ('found','not_found_in_results')
            AND r.status IN ('succeeded','partial','blocked')
            AND r.local_date >= :earliest
          ORDER BY r.local_date DESC"""),
          {"s": site_id, "earliest": (datetime.now(TZ).date() - timedelta(days=days + 1)).isoformat()}).mappings()]
    by_keyword: dict[int, list[dict]] = {}
    for item in history:
        by_keyword.setdefault(item["keyword_id"], []).append(item)
    for row in rows:
        hist = by_keyword.get(row["keyword_id"], [])[:days]
        row["history"] = list(reversed(hist))
        previous = next((x for x in hist if x["local_date"] != row["local_date"] and x["status"] == "found"), None)
        row["previous_position"] = previous["organic_position"] if previous else None
        row["delta"] = (previous["organic_position"] - row["organic_position"]
                        if previous and row["organic_position"] is not None else None)
        row["competitors"] = json.loads(row.pop("competitors_json") or "[]")
        if row["status"] == "found" and row["target_url"] and row["ranking_url"] and (
                urlsplit(row["target_url"]).path.rstrip("/") != urlsplit(row["ranking_url"]).path.rstrip("/")):
            row["action"] = "review_target_page"
        elif row["status"] == "found" and row["delta"] is not None and row["delta"] <= -4:
            row["action"] = "check_rank_drop"
        elif row["status"] == "found" and row["organic_position"] and 4 <= row["organic_position"] <= 10:
            row["action"] = "review_snippet_and_links"
        elif row["status"] == "not_found_in_results":
            row["action"] = "review_indexing_and_intent"
        else:
            row["action"] = None
    latest = runs[0] if runs else None
    return {"site_id": site_id, "generated_at": utcnow(), "settings": cfg,
            "keywords_total": total, "latest_run": latest, "runs": runs, "keywords": rows,
            "scope": "independent_organic_serp_snapshot_not_gsc_average",
            "next_local_run": "06:00 Asia/Tehran",
            "provider_note": "No live position is shown until a SERP provider is configured and a run succeeds."}
