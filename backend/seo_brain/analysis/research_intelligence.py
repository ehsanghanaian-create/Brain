"""First-party demand and explicitly tracked competitor-page research.

GSC query rows are a sampled first-party signal. They are never treated as
market-wide keyword volume or as transcripts of private AI conversations.
"""
from __future__ import annotations

import http.client
import ipaddress
import json
import re
import socket
import ssl
from datetime import date, datetime, timedelta, timezone
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit, urlunsplit

from sqlalchemy import Engine, text

from ..brain.keywords.normalize import normalize_keyword
from ..db.repositories.base import utcnow

MAX_HTML_BYTES = 1_000_000
QUESTION_PREFIX = re.compile(r"^(آیا|چرا|چطور|چگونه|چیست|چی|چه |چه‌|کدام|کی |کجا|از کجا|چند|فرق |تفاوت )")


def _json_list(value: str | None) -> list[str]:
    try:
        data = json.loads(value or "[]")
        return [str(item) for item in data] if isinstance(data, list) else []
    except (ValueError, TypeError):
        return []


def _public_https_target(url: str) -> tuple[str, str, str]:
    parts = urlsplit(url.strip())
    if (parts.scheme != "https" or not parts.hostname or parts.username or parts.password
            or parts.port not in (None, 443)):
        raise ValueError("public_https_required")
    host = parts.hostname.encode("idna").decode("ascii").lower().rstrip(".")
    if host == "localhost" or host.endswith((".local", ".internal")):
        raise ValueError("non_public_host")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        raise ValueError("ip_literal_forbidden")
    addresses = {item[4][0] for item in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)}
    if not addresses or any(not ipaddress.ip_address(ip).is_global for ip in addresses):
        raise ValueError("non_public_address")
    path = urlunsplit(("", "", parts.path or "/", parts.query, ""))
    return host, sorted(addresses)[0], path


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    """Connect to the prevalidated IP while verifying TLS against the hostname."""

    def __init__(self, host: str, ip: str):
        super().__init__(host, 443, timeout=8, context=ssl.create_default_context())
        self._pinned_ip = ip

    def connect(self) -> None:
        raw = socket.create_connection((self._pinned_ip, 443), timeout=self.timeout)
        try:
            self.sock = self._context.wrap_socket(raw, server_hostname=self.host)
        except Exception:
            raw.close()
            raise


class _PageMetadata(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.title_parts: list[str] = []
        self.headings: dict[str, list[str]] = {"h1": [], "h2": []}
        self.description = ""
        self.canonical = ""
        self.visible: list[str] = []
        self._capture: str | None = None
        self._parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = dict(attrs)
        if tag in ("script", "style", "noscript"):
            self._skip += 1
        if tag in ("title", "h1", "h2") and not self._skip:
            self._capture, self._parts = tag, []
        if tag == "meta" and (attr.get("name") or "").lower() == "description":
            self.description = (attr.get("content") or "").strip()[:500]
        if tag == "link" and "canonical" in (attr.get("rel") or "").lower().split():
            self.canonical = (attr.get("href") or "").strip()[:2000]

    def handle_endtag(self, tag: str) -> None:
        if self._capture == tag:
            value = " ".join(" ".join(self._parts).split())[:300]
            if value:
                if tag == "title":
                    self.title_parts.append(value)
                elif len(self.headings[tag]) < 20:
                    self.headings[tag].append(value)
            self._capture, self._parts = None, []
        if tag in ("script", "style", "noscript") and self._skip:
            self._skip -= 1

    def handle_data(self, data: str) -> None:
        if self._skip:
            return
        if self._capture:
            self._parts.append(data)
        if data.strip() and len(self.visible) < 10000:
            self.visible.append(data.strip())


def fetch_public_metadata(url: str) -> dict:
    """Fetch at most one public HTML page, with pinned DNS and bounded redirects/body."""
    current = url
    for _ in range(4):
        host, ip, path = _public_https_target(current)
        conn = _PinnedHTTPSConnection(host, ip)
        try:
            conn.request("GET", path, headers={"Host": host, "User-Agent": "SEOBrainResearch/1.0 (+site comparison)",
                                               "Accept": "text/html", "Accept-Encoding": "identity"})
            response = conn.getresponse()
            status = response.status
            if status in (301, 302, 303, 307, 308):
                location = response.getheader("Location")
                if not location:
                    raise ValueError("redirect_without_location")
                current = urljoin(current, location)
                continue
            if status != 200:
                raise ValueError(f"http_{status}")
            if "text/html" not in (response.getheader("Content-Type") or "").lower():
                raise ValueError("not_html")
            if (response.getheader("Content-Encoding") or "identity").lower() != "identity":
                raise ValueError("unsupported_encoding")
            body = response.read(MAX_HTML_BYTES + 1)
            if len(body) > MAX_HTML_BYTES:
                raise ValueError("html_too_large")
            parser = _PageMetadata()
            parser.feed(body.decode("utf-8", errors="replace"))
            return {"http_status": status, "title": " ".join(parser.title_parts)[:300],
                    "meta_description": parser.description, "h1_json": json.dumps(parser.headings["h1"], ensure_ascii=False),
                    "h2_json": json.dumps(parser.headings["h2"], ensure_ascii=False),
                    "canonical": parser.canonical or current, "word_count": len(" ".join(parser.visible).split())}
        finally:
            conn.close()
    raise ValueError("too_many_redirects")


def refresh_competitor(engine: Engine, site_id: str, competitor_id: int) -> dict:
    with engine.connect() as cx:
        row = cx.execute(text("SELECT url FROM research_competitor_pages WHERE site_id=:s AND id=:i"),
                         {"s": site_id, "i": competitor_id}).mappings().first()
    if not row:
        return {"status": "missing"}
    now = utcnow()
    try:
        data = fetch_public_metadata(row["url"])
        with engine.begin() as cx:
            cx.execute(text("""UPDATE research_competitor_pages SET status='ready',http_status=:http_status,
                title=:title,meta_description=:meta_description,h1_json=:h1_json,h2_json=:h2_json,
                canonical=:canonical,word_count=:word_count,error_code='',last_checked_at=:now,updated_at=:now
                WHERE site_id=:s AND id=:i"""), {**data, "now": now, "s": site_id, "i": competitor_id})
        return {"status": "ready", "id": competitor_id}
    except (OSError, ssl.SSLError, http.client.HTTPException, ValueError, UnicodeError) as exc:
        code = str(exc) if isinstance(exc, ValueError) else exc.__class__.__name__.lower()
        code = code[:80] if re.fullmatch(r"[a-z0-9_]+", code) else "fetch_failed"
        with engine.begin() as cx:
            cx.execute(text("""UPDATE research_competitor_pages SET status='error',error_code=:error,
                last_checked_at=:now,updated_at=:now WHERE site_id=:s AND id=:i"""),
                {"error": code, "now": now, "s": site_id, "i": competitor_id})
        return {"status": "error", "id": competitor_id, "error_code": code}


def due_competitors(engine: Engine, limit: int = 2) -> list[dict]:
    """Reserve stale targets so successive scheduler ticks do not duplicate work."""
    now = datetime.now(timezone.utc)
    stale = (now - timedelta(hours=24)).isoformat(timespec="seconds").replace("+00:00", "Z")
    retry = (now - timedelta(hours=2)).isoformat(timespec="seconds").replace("+00:00", "Z")
    ids: list[dict] = []
    with engine.begin() as cx:
        rows = cx.execute(text("""SELECT id,site_id FROM research_competitor_pages WHERE
            (last_checked_at IS NULL OR last_checked_at<:stale) AND
            (status<>'queued' OR last_requested_at IS NULL OR last_requested_at<:retry)
            ORDER BY COALESCE(last_checked_at,'') ASC,id ASC LIMIT :n"""),
            {"stale": stale, "retry": retry, "n": limit}).mappings().all()
        for row in rows:
            cx.execute(text("""UPDATE research_competitor_pages SET status='queued',last_requested_at=:now,
                updated_at=:now WHERE id=:i"""), {"now": utcnow(), "i": row["id"]})
            ids.append(dict(row))
    return ids


def overview(engine: Engine, site_id: str, days: int = 28) -> dict:
    with engine.connect() as cx:
        latest = cx.execute(text("SELECT MAX(date) FROM gsc_daily WHERE site_id=:s AND query<>''"), {"s": site_id}).scalar()
        latest_sync = cx.execute(text("""SELECT status,finished_at FROM sync_runs WHERE site_id=:s
            AND source='gsc_pipeline' ORDER BY started_at DESC,rowid DESC LIMIT 1"""),
            {"s": site_id}).mappings().first()
        if not latest_sync:
            latest_sync = cx.execute(text("""SELECT status,finished_at FROM sync_runs WHERE site_id=:s
                AND source='gsc' ORDER BY started_at DESC,rowid DESC LIMIT 1"""),
                {"s": site_id}).mappings().first()
        competitors = [dict(row) for row in cx.execute(text("""SELECT * FROM research_competitor_pages
            WHERE site_id=:s ORDER BY id DESC LIMIT 100"""), {"s": site_id}).mappings()]
        citations = [dict(row) for row in cx.execute(text("""SELECT c.domain,COUNT(*) mentions,
            MAX(o.observed_at) last_observed_at,MIN(c.url) example_url
            FROM ai_visibility_citations c JOIN ai_visibility_observations o ON o.id=c.observation_id
            WHERE o.site_id=:s AND c.is_own_domain=0 GROUP BY c.domain
            ORDER BY mentions DESC,last_observed_at DESC LIMIT 20"""), {"s": site_id}).mappings()]
        prompts = [dict(row) for row in cx.execute(text("""SELECT p.id,p.question,p.topic,p.target_url,
            p.active,COUNT(o.id) samples,MAX(o.observed_at) last_observed_at
            FROM ai_visibility_prompts p LEFT JOIN ai_visibility_observations o ON o.prompt_id=p.id
            WHERE p.site_id=:s GROUP BY p.id ORDER BY p.active DESC,p.id DESC LIMIT 40"""),
            {"s": site_id}).mappings()]
        known = {row[0] for row in cx.execute(text("SELECT normalized FROM keywords WHERE site_id=:s"),
                                               {"s": site_id}).all()}
        for row in competitors:
            own_url = row["own_url"]
            own_parts = urlsplit(own_url)
            alternate_path = own_parts.path.rstrip("/") or "/"
            if alternate_path == own_parts.path:
                alternate_path += "/"
            alternate_url = urlunsplit((own_parts.scheme, own_parts.netloc,
                                        alternate_path, own_parts.query, ""))
            own = cx.execute(text("""SELECT title,meta_description,h1,h2,word_count,last_crawled
                FROM pages WHERE site_id=:s AND url IN (:u,:v) ORDER BY last_crawled DESC LIMIT 1"""),
                {"s": site_id, "u": own_url, "v": alternate_url}).mappings().first() if own_url else None
            row["h1"] = _json_list(row.pop("h1_json"))
            row["h2"] = _json_list(row.pop("h2_json"))
            row["own_page"] = ({**dict(own), "h1": _json_list(own["h1"]), "h2": _json_list(own["h2"])}
                               if own else None)
        daily: list[dict] = []
        candidates: list[dict] = []
        observed_questions: list[dict] = []
        current_days = previous_days = 0
        period = None
        if latest:
            end = date.fromisoformat(latest)
            start = end - timedelta(days=days - 1)
            prev_start = start - timedelta(days=days)
            args = {"s": site_id, "a": start.isoformat(), "b": end.isoformat(), "p": prev_start.isoformat()}
            coverage = cx.execute(text("""SELECT COUNT(DISTINCT CASE WHEN date BETWEEN :a AND :b THEN date END) current_days,
                COUNT(DISTINCT CASE WHEN date BETWEEN :p AND date(:a,'-1 day') THEN date END) previous_days
                FROM gsc_daily WHERE site_id=:s AND date BETWEEN :p AND :b"""), args).mappings().one()
            current_days, previous_days = int(coverage["current_days"]), int(coverage["previous_days"])
            daily = [dict(row) for row in cx.execute(text("""SELECT date,SUM(impressions) impressions,
                SUM(clicks) clicks FROM gsc_daily WHERE site_id=:s AND date BETWEEN :a AND :b
                AND query<>'' GROUP BY date ORDER BY date"""), args).mappings()]
            rows = [dict(row) for row in cx.execute(text("""SELECT query,
                SUM(CASE WHEN date BETWEEN :a AND :b THEN impressions ELSE 0 END) impressions,
                SUM(CASE WHEN date BETWEEN :a AND :b THEN clicks ELSE 0 END) clicks,
                SUM(CASE WHEN date BETWEEN :p AND date(:a,'-1 day') THEN impressions ELSE 0 END) previous_impressions,
                SUM(CASE WHEN date BETWEEN :a AND :b THEN position*impressions ELSE 0 END) weighted_position
                FROM gsc_daily WHERE site_id=:s AND date BETWEEN :p AND :b AND query<>''
                GROUP BY query HAVING impressions>0 ORDER BY impressions DESC LIMIT 1500"""), args).mappings()]
            unsaved = [row for row in rows if normalize_keyword(row["query"]) not in known][:150]
            raw_questions = [row for row in rows if QUESTION_PREFIX.match(row["query"].strip())
                             or "؟" in row["query"]][:24]
            if unsaved or raw_questions:
                names = list(dict.fromkeys([row["query"] for row in unsaved + raw_questions]))
                bind = {f"q{i}": name for i, name in enumerate(names)}
                top_pages = cx.execute(text("""SELECT query,page,SUM(impressions) impressions FROM gsc_daily
                    WHERE site_id=:s AND date BETWEEN :a AND :b AND query IN ("""
                    + ",".join(f":q{i}" for i in range(len(names))) + ") GROUP BY query,page ORDER BY impressions DESC"),
                    {**args, **bind}).mappings()
                page_by_query: dict[str, str] = {}
                for page in top_pages:
                    page_by_query.setdefault(page["query"], page["page"])
                for row in unsaved:
                    row["position"] = (round(row.pop("weighted_position") / row["impressions"], 1)
                                       if row["impressions"] else None)
                    row["top_page"] = page_by_query.get(row["query"])
                    row["signal"] = ("new_in_sample" if previous_days >= max(7, days // 2)
                                     and row["previous_impressions"] == 0 else
                                     "growing_in_sample" if previous_days >= max(7, days // 2)
                                     and row["impressions"] >= 2 * row["previous_impressions"]
                                     and row["impressions"] >= 10 else "observed")
                    row["is_question"] = bool(QUESTION_PREFIX.match(row["query"].strip()) or "؟" in row["query"])
                    candidates.append(row)
                observed_questions = [{"query": row["query"], "impressions": row["impressions"],
                                       "clicks": row["clicks"], "top_page": page_by_query.get(row["query"]),
                                       "source": "gsc_daily"} for row in raw_questions]
            period = {"start": start.isoformat(), "end": end.isoformat(), "days": days}
    modeled_questions = [{"query": row["query"], "question": f"برای «{row['query']}» چه گزینه‌هایی مناسب‌اند؟",
                          "impressions": row["impressions"], "top_page": row["top_page"],
                          "source": "derived_from_gsc_query"}
                         for row in candidates if not row["is_question"]][:12]
    return {"site_id": site_id, "generated_at": utcnow(), "period": period,
            "gsc": {"latest_date": latest, "latest_sync": dict(latest_sync) if latest_sync else None,
                    "current_days": current_days, "previous_days": previous_days,
                    "coverage": "retained_gsc_query_page_rows_not_full_market",
                    "daily": daily, "candidates": candidates,
                    "candidate_limit": 150, "query_scan_limit": 1500},
            "questions": {"observed_search_questions": observed_questions,
                          "modeled_buyer_questions": modeled_questions, "tracked_prompts": prompts,
                          "scope": "no_access_to_private_ai_user_prompts"},
            "competitors": {"tracked_pages": competitors, "ai_citation_domains": citations,
                            "scope": "tracked_public_pages_and_recorded_ai_samples_not_serp_rankings"}}
