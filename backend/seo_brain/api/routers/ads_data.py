"""Live, collection-only ad traffic telemetry and read-only dashboard queries.

The browser-facing collector is implemented by the Next.js proxy. It derives
the remote IP from trusted reverse-proxy headers and forwards the normalized
payload here with the internal API token. There are deliberately no delete or
blocking endpoints in this phase.
"""
from __future__ import annotations

import csv
import hashlib
import hmac
import io
import ipaddress
import json
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import Engine, text

from ...common.config import env
from ...db.engine import make_engine
from ...db.migrate import migrate
from ..deps import engine

router = APIRouter(prefix="/ads-data", tags=["ads-data"])

EVENT_TYPES = {
    "landing", "page_view", "heartbeat", "scroll", "tel_click",
    "whatsapp_click", "form_start", "form_submit", "page_exit",
}


class AdsEventIn(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    event_uuid: str = Field(min_length=8, max_length=80)
    site_id: str = Field(min_length=3, max_length=120)
    event_type: str = Field(min_length=3, max_length=40)
    occurred_at_client: str | None = Field(default=None, max_length=50)
    visitor_id: str | None = Field(default=None, max_length=100)
    session_id: str | None = Field(default=None, max_length=100)
    gclid: str | None = Field(default=None, max_length=300)
    gbraid: str | None = Field(default=None, max_length=300)
    wbraid: str | None = Field(default=None, max_length=300)
    campaign_id: str | None = Field(default=None, max_length=80)
    ad_group_id: str | None = Field(default=None, max_length=80)
    creative_id: str | None = Field(default=None, max_length=80)
    keyword: str | None = Field(default=None, max_length=500)
    match_type: str | None = Field(default=None, max_length=80)
    device: str | None = Field(default=None, max_length=80)
    network: str | None = Field(default=None, max_length=80)
    utm_source: str | None = Field(default=None, max_length=200)
    utm_medium: str | None = Field(default=None, max_length=200)
    utm_campaign: str | None = Field(default=None, max_length=300)
    utm_term: str | None = Field(default=None, max_length=500)
    utm_content: str | None = Field(default=None, max_length=300)
    landing_path: str | None = Field(default=None, max_length=1500)
    page_path: str | None = Field(default=None, max_length=1500)
    referrer: str | None = Field(default=None, max_length=1500)
    browser_language: str | None = Field(default=None, max_length=80)
    browser_timezone: str | None = Field(default=None, max_length=100)
    screen_size: str | None = Field(default=None, max_length=40)
    metadata: dict[str, Any] = Field(default_factory=dict)
    server_ip: str = Field(min_length=3, max_length=80)
    server_ip_source: str | None = Field(default=None, max_length=80)
    server_proxy_ip: str | None = Field(default=None, max_length=80)
    server_ip_confidence: str = Field(default="legacy_unverified", max_length=40)
    server_ip_resolution_version: str = Field(default="1", max_length=20)
    server_user_agent: str | None = Field(default=None, max_length=1000)

    @field_validator("event_type")
    @classmethod
    def known_event(cls, value: str) -> str:
        if value not in EVENT_TYPES:
            raise ValueError("unsupported event_type")
        return value

    @field_validator("metadata")
    @classmethod
    def bounded_metadata(cls, value: dict[str, Any]) -> dict[str, Any]:
        encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        if len(encoded.encode("utf-8")) > 8_000:
            raise ValueError("metadata is too large")
        return value


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _allowed_sites() -> set[str]:
    raw = env("ADS_COLLECTOR_SITES", "modirankhodro-emdad.com,renaultemdad.com") or ""
    return {item.strip().lower() for item in raw.split(",") if item.strip()}


def _ip_parts(raw: str) -> tuple[str, str]:
    try:
        parsed = ipaddress.ip_address(raw.strip())
    except ValueError as exc:
        raise HTTPException(422, "invalid server_ip") from exc
    if parsed.version == 4:
        prefix = str(ipaddress.ip_network(f"{parsed}/24", strict=False))
    else:
        prefix = str(ipaddress.ip_network(f"{parsed}/48", strict=False))
    return str(parsed), prefix


def _ip_hash(ip: str) -> str:
    secret = env("ADS_IP_HASH_SECRET") or env("API_TOKEN") or "local-development-only"
    return hmac.new(secret.encode("utf-8"), ip.encode("utf-8"), hashlib.sha256).hexdigest()


def _safe_metadata(value: dict[str, Any]) -> str:
    # Values only; arbitrary nested structures are retained but bounded by the model.
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _ads_attribution(row: dict[str, Any]) -> str:
    if row.get("gclid") or row.get("gbraid") or row.get("wbraid"):
        return "google_ads_confirmed"
    medium = str(row.get("utm_medium") or "").lower()
    if row.get("campaign_id") or row.get("ad_group_id") or row.get("creative_id"):
        return "google_ads_likely"
    if medium in {"cpc", "ppc", "paid", "paidsearch", "paid_search"}:
        return "paid_traffic_likely"
    return "unattributed"


# SQL fragments mirroring _ads_attribution, so the /events filter matches the
# per-row label exactly instead of only filtering the current page.
_SQL_ADS_CONFIRMED = "(COALESCE(gclid,'')<>'' OR COALESCE(gbraid,'')<>'' OR COALESCE(wbraid,'')<>'')"
_SQL_ADS_LIKELY = "(COALESCE(campaign_id,'')<>'' OR COALESCE(ad_group_id,'')<>'' OR COALESCE(creative_id,'')<>'')"
_SQL_ADS_PAID = "LOWER(COALESCE(utm_medium,'')) IN ('cpc','ppc','paid','paidsearch','paid_search')"
_SQL_ADS_ANY = f"({_SQL_ADS_CONFIRMED} OR {_SQL_ADS_LIKELY} OR {_SQL_ADS_PAID})"


def _attribution_clause(value: str | None) -> str | None:
    """Translate an attribution filter value into a SQL WHERE fragment (or None)."""
    if value in (None, "", "all"):
        return None
    if value == "ads":
        return _SQL_ADS_ANY
    if value == "confirmed":
        return _SQL_ADS_CONFIRMED
    if value == "unattributed":
        return f"NOT {_SQL_ADS_ANY}"
    raise HTTPException(422, "invalid attribution filter")


# ---------------------------------------------------------------------------
# IP geolocation — fully offline via local DB-IP Lite MMDB files (city + ASN),
# read with maxminddb. No external calls, no rate limits, commercial-friendly
# (DB-IP Lite, CC-BY "IP Geolocation by DB-IP"). Datacenter/proxy/mobile are
# inferred from the ASN org name, since the free MMDBs carry no such flag.
# Lookups are cheap and cached in-process; every helper degrades to empty data
# if the dependency or the .mmdb files are missing.
# ---------------------------------------------------------------------------
_GEOIP_DIR = env("GEOIP_DIR") or "/app/geoip"
_GEO_CITY_DB = "dbip-city-lite.mmdb"
_GEO_ASN_DB = "dbip-asn-lite.mmdb"

# ASN-org substrings marking hosting/cloud/datacenter networks — the primary
# click-fraud tell (bots run in datacenters, not on home/mobile connections).
_HOSTING_TOKENS = (
    "hosting", "cloud", "datacenter", "data center", "data-center", "colocation",
    "colo ", "dedicated", "vps", "cdn", "server ", "hetzner", "ovh", "digitalocean",
    "digital ocean", "amazon technologies", "amazon.com", "amazon data", "aws",
    "google llc", "microsoft", "azure", "oracle", "alibaba cloud", "tencent",
    "linode", "akamai", "vultr", "contabo", "leaseweb", "m247", "choopa", "scaleway",
    "g-core", "gcore", "zenlayer", "datacamp", "cdn77", "quadranet", "psychz",
    "colocrossing", "dataforest", "serverius", "servermania", "server mania",
    "limestone networks", "ionos", "hostinger", "namecheap", "incognet",
    "constant company", "hostwinds", "hostroyale", "cloudflare", "stark industries",
    "aeza", "melbicom", "internet-services",
)
_PROXY_TOKENS = ("vpn", "proxy", "anonym", "tor exit", "tor-exit")
_MOBILE_TOKENS = ("mobile", "cellular", "wireless", "gsm")

# IANA timezone -> set of ISO country codes, for detecting when a visitor's
# browser timezone contradicts the country of their IP (a common VPN/fraud tell).
try:
    import pytz  # noqa: PLC0415

    _TZ_TO_COUNTRIES: dict[str, set[str]] = {}
    for _cc, _zones in pytz.country_timezones.items():
        for _zone in _zones:
            _TZ_TO_COUNTRIES.setdefault(_zone, set()).add(_cc.upper())
except Exception:  # noqa: BLE001 — feature is optional; never break import
    _TZ_TO_COUNTRIES = {}


def _tz_country_mismatch(country_code: str | None, browser_timezone: str | None) -> bool:
    if not country_code or not browser_timezone or not _TZ_TO_COUNTRIES:
        return False
    countries = _TZ_TO_COUNTRIES.get(browser_timezone.strip())
    if not countries:
        return False  # unknown/unmappable timezone → do not flag
    return country_code.upper() not in countries

_EMPTY_GEO = {
    "geo_country": None, "geo_country_code": None, "geo_city": None,
    "geo_isp": None, "geo_asn": None, "geo_asname": None,
    "geo_mobile": False, "geo_proxy": False, "geo_hosting": False,
}


@lru_cache(maxsize=1)
def _geo_readers():
    import maxminddb  # imported lazily so the module loads even without the dep
    city = asn = None
    try:
        city = maxminddb.open_database(f"{_GEOIP_DIR}/{_GEO_CITY_DB}")
    except (FileNotFoundError, OSError, ValueError):
        city = None
    try:
        asn = maxminddb.open_database(f"{_GEOIP_DIR}/{_GEO_ASN_DB}")
    except (FileNotFoundError, OSError, ValueError):
        asn = None
    return city, asn


@lru_cache(maxsize=100_000)
def _geo_lookup(ip: str) -> dict[str, Any]:
    try:
        city_db, asn_db = _geo_readers()
    except Exception:  # noqa: BLE001 — missing dependency; never break reads
        return dict(_EMPTY_GEO)
    if city_db is None and asn_db is None:
        return dict(_EMPTY_GEO)
    out = dict(_EMPTY_GEO)
    try:
        crec = (city_db.get(ip) if city_db else None) or {}
    except (ValueError, KeyError):
        crec = {}
    country = crec.get("country") or {}
    out["geo_country"] = (country.get("names") or {}).get("en")
    out["geo_country_code"] = country.get("iso_code")
    out["geo_city"] = ((crec.get("city") or {}).get("names") or {}).get("en")
    try:
        arec = (asn_db.get(ip) if asn_db else None) or {}
    except (ValueError, KeyError):
        arec = {}
    asn_num = arec.get("autonomous_system_number")
    asn_org = arec.get("autonomous_system_organization") or ""
    if asn_org:
        out["geo_isp"] = asn_org
        out["geo_asname"] = asn_org
    if asn_num:
        out["geo_asn"] = f"AS{asn_num} {asn_org}".strip()
    low = asn_org.lower()
    if low:
        out["geo_hosting"] = any(tok in low for tok in _HOSTING_TOKENS)
        out["geo_proxy"] = any(tok in low for tok in _PROXY_TOKENS)
        out["geo_mobile"] = any(tok in low for tok in _MOBILE_TOKENS)
    return out


def _attach_geo(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    for row in items:
        row.update(_geo_lookup(row["ip_address"]))
        # Fold datacenter/proxy origin into the risk score — only for IPs whose
        # address is reliable (same gate as _risk_score); otherwise the flags
        # would describe a CDN edge, not the visitor.
        if "browser_timezone" in row:
            row.setdefault("geo_tz_mismatch", False)
        if row.get("ip_confidence") in {"trusted_proxy", "direct_peer"}:
            extra, reasons = 0, list(row.get("risk_reasons") or [])
            if row.get("geo_hosting"):
                extra += 40
                reasons.append("datacenter_ip")
            if row.get("geo_proxy"):
                extra += 40
                reasons.append("proxy_ip")
            if "browser_timezone" in row and _tz_country_mismatch(row.get("geo_country_code"), row.get("browser_timezone")):
                extra += 30
                reasons.append("tz_country_mismatch")
                row["geo_tz_mismatch"] = True
            if extra:
                row["risk_score"] = min(100, int(row.get("risk_score") or 0) + extra)
                row["risk_reasons"] = reasons
    return items


@lru_cache(maxsize=4)
def _dedicated_ads_engine(path: str) -> Engine:
    eng = make_engine("sqlite:///" + path)
    migrate(eng)
    return eng


def ads_engine(default: Engine = Depends(engine)) -> Engine:
    """Keep high-volume telemetry isolated from long-running SEO write jobs."""
    path = (env("ADS_DATABASE_PATH") or "").strip()
    return _dedicated_ads_engine(path) if path else default


@router.post("/events", status_code=202)
def collect_event(payload: AdsEventIn, eng: Engine = Depends(ads_engine)) -> dict[str, Any]:
    if payload.site_id.lower() not in _allowed_sites():
        raise HTTPException(403, "site_id is not allowed")
    ip, prefix = _ip_parts(payload.server_ip)
    received = _iso(_utcnow())
    cutoff = _iso(_utcnow() - timedelta(minutes=1))

    row = payload.model_dump()
    row.update({
        "received_at": received,
        "ip_address": ip,
        "ip_hash": _ip_hash(ip),
        "ip_prefix": prefix,
        "ip_source": payload.server_ip_source,
        "proxy_ip": payload.server_proxy_ip,
        "ip_confidence": payload.server_ip_confidence,
        "ip_resolution_version": payload.server_ip_resolution_version,
        "user_agent": payload.server_user_agent,
        "metadata_json": _safe_metadata(payload.metadata),
    })
    row.pop("metadata", None)
    row.pop("server_ip", None)
    row.pop("server_ip_source", None)
    row.pop("server_proxy_ip", None)
    row.pop("server_ip_confidence", None)
    row.pop("server_ip_resolution_version", None)
    row.pop("server_user_agent", None)

    columns = list(row)
    params = ",".join(f":{column}" for column in columns)
    with eng.begin() as cx:
        recent = int(cx.execute(text(
            "SELECT COUNT(*) FROM ads_click_events WHERE ip_hash=:ip_hash AND received_at>=:cutoff"
        ), {"ip_hash": row["ip_hash"], "cutoff": cutoff}).scalar_one())
        if recent >= 180:
            raise HTTPException(429, "collector rate limit exceeded")
        result = cx.execute(text(
            f"INSERT OR IGNORE INTO ads_click_events ({','.join(columns)}) VALUES ({params})"
        ), row)
    return {"accepted": bool(result.rowcount), "duplicate": not bool(result.rowcount), "received_at": received}


def _cutoff(hours: int) -> str:
    if hours == 0:
        return "1970-01-01T00:00:00.000Z"
    return _iso(_utcnow() - timedelta(hours=hours))


@router.get("/sites")
def collector_sites(eng: Engine = Depends(ads_engine)) -> dict[str, Any]:
    """Allowed collector sites + per-site event counts — drives the dashboard's site selector."""
    with eng.connect() as cx:
        counts = dict(cx.execute(text("SELECT site_id, COUNT(*) FROM ads_click_events GROUP BY site_id")).all())
    return {"sites": [{"site_id": s, "events": int(counts.get(s, 0))} for s in sorted(_allowed_sites())]}


@router.get("/summary")
def summary(hours: int = Query(default=24, ge=0, le=87_600), site_id: str = "modirankhodro-emdad.com",
            eng: Engine = Depends(ads_engine)) -> dict[str, Any]:
    since = _cutoff(hours)
    five_minutes = _iso(_utcnow() - timedelta(minutes=5))
    sixty_minutes = _iso(_utcnow() - timedelta(minutes=60))
    with eng.connect() as cx:
        totals = dict(cx.execute(text("""
            SELECT COUNT(*) AS events,
                   COUNT(DISTINCT ip_hash) AS unique_ips,
                   COUNT(DISTINCT visitor_id) AS visitors,
                   COUNT(DISTINCT session_id) AS sessions,
                   SUM(CASE WHEN event_type='landing' THEN 1 ELSE 0 END) AS landings,
                   SUM(CASE WHEN event_type='tel_click' THEN 1 ELSE 0 END) AS tel_clicks,
                   SUM(CASE WHEN event_type='form_submit' THEN 1 ELSE 0 END) AS form_submits,
                   SUM(CASE WHEN COALESCE(gclid,'')<>'' OR COALESCE(gbraid,'')<>'' OR COALESCE(wbraid,'')<>'' THEN 1 ELSE 0 END) AS google_ads_confirmed_events,
                   SUM(CASE WHEN COALESCE(campaign_id,'')<>'' OR COALESCE(ad_group_id,'')<>'' OR COALESCE(creative_id,'')<>'' THEN 1 ELSE 0 END) AS google_ads_likely_events
            FROM ads_click_events WHERE site_id=:site_id AND received_at>=:since
        """), {"site_id": site_id, "since": since}).mappings().one())
        recent = dict(cx.execute(text("""
            SELECT SUM(CASE WHEN received_at>=:five THEN 1 ELSE 0 END) AS events_5m,
                   SUM(CASE WHEN received_at>=:sixty THEN 1 ELSE 0 END) AS events_60m,
                   COUNT(DISTINCT CASE WHEN received_at>=:five THEN ip_hash END) AS ips_5m,
                   COUNT(DISTINCT CASE WHEN received_at>=:sixty THEN ip_hash END) AS ips_60m
            FROM ads_click_events WHERE site_id=:site_id
        """), {"site_id": site_id, "five": five_minutes, "sixty": sixty_minutes}).mappings().one())
        hourly = [dict(row) for row in cx.execute(text("""
            SELECT strftime('%Y-%m-%dT%H:00:00Z', received_at) AS hour,
                   COUNT(*) AS events,
                   COUNT(DISTINCT ip_hash) AS unique_ips,
                   SUM(CASE WHEN event_type='landing' THEN 1 ELSE 0 END) AS landings,
                   SUM(CASE WHEN event_type='tel_click' THEN 1 ELSE 0 END) AS tel_clicks
            FROM ads_click_events
            WHERE site_id=:site_id AND received_at>=:since
            GROUP BY hour ORDER BY hour
        """), {"site_id": site_id, "since": since}).mappings()]
        event_types = [dict(row) for row in cx.execute(text("""
            SELECT event_type, COUNT(*) AS count FROM ads_click_events
            WHERE site_id=:site_id AND received_at>=:since
            GROUP BY event_type ORDER BY count DESC, event_type
        """), {"site_id": site_id, "since": since}).mappings()]
        campaigns = [dict(row) for row in cx.execute(text("""
            SELECT COALESCE(NULLIF(utm_campaign,''), NULLIF(campaign_id,''), '(unknown)') AS campaign,
                   COUNT(*) AS events,
                   COUNT(DISTINCT session_id) AS sessions,
                   SUM(CASE WHEN event_type='landing' THEN 1 ELSE 0 END) AS landings,
                   SUM(CASE WHEN event_type='tel_click' THEN 1 ELSE 0 END) AS tel_clicks
            FROM ads_click_events
            WHERE site_id=:site_id AND received_at>=:since
            GROUP BY campaign ORDER BY events DESC LIMIT 20
        """), {"site_id": site_id, "since": since}).mappings()]

    normalized_totals = {key: int(value or 0) for key, value in totals.items()}
    normalized_recent = {key: int(value or 0) for key, value in recent.items()}
    return {
        "generated_at": _iso(_utcnow()), "site_id": site_id, "hours": hours,
        "totals": normalized_totals, "recent": normalized_recent,
        "hourly": hourly, "event_types": event_types, "campaigns": campaigns,
        "mode": "shadow", "blocking_enabled": False,
    }


def _risk_score(row: dict[str, Any]) -> tuple[int, list[str]]:
    if row.get("ip_confidence") not in {"trusted_proxy", "direct_peer"}:
        return 0, ["ip_not_reliable"]
    score, reasons = 0, []
    if int(row.get("landings") or 0) >= 10:
        score += 30; reasons.append("landing_velocity")
    elif int(row.get("landings") or 0) >= 5:
        score += 15; reasons.append("landing_velocity_watch")
    if int(row.get("tel_clicks") or 0) >= 3:
        score += 35; reasons.append("tel_click_burst")
    if int(row.get("sessions") or 0) >= 8:
        score += 20; reasons.append("many_sessions")
    if int(row.get("events_5m") or 0) >= 15:
        score += 35; reasons.append("five_minute_burst")
    return min(score, 100), reasons


def _ip_rows(cx, site_id: str, since: str, limit: int) -> list[dict[str, Any]]:
    rows = [dict(row) for row in cx.execute(text("""
        SELECT ip_address, ip_hash, ip_prefix, MAX(ip_source) AS ip_source,
               MAX(proxy_ip) AS proxy_ip, MAX(ip_confidence) AS ip_confidence,
               MAX(ip_resolution_version) AS ip_resolution_version,
               MIN(received_at) AS first_seen, MAX(received_at) AS last_seen,
               COUNT(*) AS events, COUNT(DISTINCT session_id) AS sessions,
               COUNT(DISTINCT visitor_id) AS visitors,
               COUNT(DISTINCT gclid) AS gclids,
               SUM(CASE WHEN COALESCE(gclid,'')<>'' OR COALESCE(gbraid,'')<>'' OR COALESCE(wbraid,'')<>'' THEN 1 ELSE 0 END) AS google_ads_confirmed_events,
               SUM(CASE WHEN COALESCE(campaign_id,'')<>'' OR COALESCE(ad_group_id,'')<>'' OR COALESCE(creative_id,'')<>'' THEN 1 ELSE 0 END) AS google_ads_likely_events,
               SUM(CASE WHEN event_type='landing' THEN 1 ELSE 0 END) AS landings,
               SUM(CASE WHEN event_type='tel_click' THEN 1 ELSE 0 END) AS tel_clicks,
               SUM(CASE WHEN event_type='form_submit' THEN 1 ELSE 0 END) AS form_submits,
               SUM(CASE WHEN received_at>=:five THEN 1 ELSE 0 END) AS events_5m,
               MAX(user_agent) AS latest_user_agent,
               MAX(page_path) AS latest_page_path,
               MAX(referrer) AS latest_referrer
        FROM ads_click_events
        WHERE site_id=:site_id AND received_at>=:since
        GROUP BY ip_address, ip_hash, ip_prefix
        ORDER BY last_seen DESC LIMIT :limit
    """), {"site_id": site_id, "since": since, "five": _iso(_utcnow() - timedelta(minutes=5)), "limit": limit}).mappings()]
    for row in rows:
        row["risk_score"], row["risk_reasons"] = _risk_score(row)
    return rows


@router.get("/ips")
def ips(hours: int = Query(default=24, ge=0, le=87_600), limit: int = Query(default=200, ge=1, le=10_000),
        site_id: str = "modirankhodro-emdad.com", eng: Engine = Depends(ads_engine)) -> dict[str, Any]:
    with eng.connect() as cx:
        items = _ip_rows(cx, site_id, _cutoff(hours), limit)
    items = _attach_geo(items)
    return {"generated_at": _iso(_utcnow()), "site_id": site_id, "hours": hours, "items": items, "count": len(items)}


@router.get("/ips.csv")
def ips_csv(hours: int = Query(default=24, ge=0, le=87_600), limit: int = Query(default=10000, ge=1, le=100_000),
            site_id: str = "modirankhodro-emdad.com", eng: Engine = Depends(ads_engine)) -> Response:
    with eng.connect() as cx:
        items = _ip_rows(cx, site_id, _cutoff(hours), limit)
    items = _attach_geo(items)
    stream = io.StringIO()
    columns = ["ip_address", "ip_prefix", "ip_source", "proxy_ip", "ip_confidence", "ip_resolution_version", "risk_score", "risk_reasons", "geo_country", "geo_city", "geo_isp", "geo_asn", "geo_asname", "geo_mobile", "geo_proxy", "geo_hosting", "events", "events_5m", "sessions", "visitors", "gclids", "google_ads_confirmed_events", "google_ads_likely_events", "landings", "tel_clicks", "form_submits", "first_seen", "last_seen", "latest_page_path", "latest_referrer", "latest_user_agent"]
    writer = csv.DictWriter(stream, fieldnames=columns, extrasaction="ignore")
    writer.writeheader()
    for item in items:
        writer.writerow({**item, "risk_reasons": "|".join(item["risk_reasons"])})
    filename = f"ads-ip-data-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.csv"
    return Response(stream.getvalue(), media_type="text/csv; charset=utf-8", headers={
        "Content-Disposition": f'attachment; filename="{filename}"', "Cache-Control": "no-store",
    })


EVENT_DB_COLUMNS = [
    "id", "event_uuid", "event_type", "occurred_at_client", "received_at",
    "ip_address", "ip_prefix", "ip_source", "proxy_ip", "ip_confidence", "ip_resolution_version", "visitor_id", "session_id",
    "gclid", "gbraid", "wbraid", "campaign_id", "ad_group_id", "creative_id",
    "keyword", "match_type", "device", "network", "utm_source", "utm_medium",
    "utm_campaign", "utm_term", "utm_content", "landing_path", "page_path",
    "referrer", "user_agent", "browser_language", "browser_timezone", "screen_size",
    "metadata_json",
]
EVENT_EXPORT_COLUMNS = EVENT_DB_COLUMNS[:-1] + ["ads_attribution", "metadata_json"]


def _event_rows(cx, site_id: str, hours: int, limit: int, offset: int = 0,
                event_type: str | None = None, query: str | None = None,
                attribution: str | None = None) -> tuple[list[dict[str, Any]], int]:
    clauses = ["site_id=:site_id", "received_at>=:since"]
    params: dict[str, Any] = {
        "site_id": site_id, "since": _cutoff(hours), "limit": limit, "offset": offset,
    }
    if event_type:
        clauses.append("event_type=:event_type"); params["event_type"] = event_type
    attribution_clause = _attribution_clause(attribution)
    if attribution_clause:
        clauses.append(attribution_clause)
    if query:
        params["query"] = f"%{query.strip()}%"
        clauses.append("(" + " OR ".join(
            f"COALESCE({column},'') LIKE :query" for column in (
                "ip_address", "visitor_id", "session_id", "gclid", "gbraid", "wbraid",
                "campaign_id", "ad_group_id", "creative_id", "keyword", "utm_campaign",
                "utm_term", "landing_path", "page_path", "referrer", "user_agent",
            )
        ) + ")")
    where = " AND ".join(clauses)
    total = int(cx.execute(text(
        f"SELECT COUNT(*) FROM ads_click_events WHERE {where}"
    ), params).scalar_one())
    rows = [dict(row) for row in cx.execute(text(f"""
        SELECT {','.join(EVENT_DB_COLUMNS)}
        FROM ads_click_events WHERE {where}
        ORDER BY received_at DESC, id DESC LIMIT :limit OFFSET :offset
    """), params).mappings()]
    for row in rows:
        row["ads_attribution"] = _ads_attribution(row)
        try:
            row["metadata"] = json.loads(row.get("metadata_json") or "{}")
        except ValueError:
            row["metadata"] = {}
    return rows, total


@router.get("/events")
def events(hours: int = Query(default=24, ge=0, le=87_600), limit: int = Query(default=100, ge=1, le=1000),
           offset: int = Query(default=0, ge=0, le=10_000_000),
           site_id: str = "modirankhodro-emdad.com", event_type: str | None = None,
           q: str | None = Query(default=None, max_length=500),
           attribution: str | None = Query(default=None, max_length=20),
           eng: Engine = Depends(ads_engine)) -> dict[str, Any]:
    with eng.connect() as cx:
        rows, total = _event_rows(cx, site_id, hours, limit, offset, event_type, q, attribution)
    for row in rows:
        row.pop("metadata_json", None)
    return {
        "generated_at": _iso(_utcnow()), "site_id": site_id, "hours": hours,
        "items": rows, "count": len(rows), "total": total, "limit": limit, "offset": offset,
    }


_SESSION_SCAN_LIMIT = 60_000  # newest N events scanned per request when grouping


def _session_rows(cx, site_id: str, since: str) -> list[dict[str, Any]]:
    """Collapse raw events into one row per visitor session (falls back to
    visitor_id, then ip_hash) so a single bot spamming heartbeats becomes ONE
    live entry instead of flooding the log."""
    raw = cx.execute(text("""
        SELECT received_at, event_type, ip_address, ip_hash, ip_confidence, ip_resolution_version,
               proxy_ip, ip_source, visitor_id, session_id, page_path, landing_path, referrer,
               utm_campaign, utm_medium, utm_term, utm_content, campaign_id, gclid, gbraid, wbraid, device, user_agent,
               browser_language, browser_timezone, screen_size
        FROM ads_click_events
        WHERE site_id=:site_id AND received_at>=:since
        ORDER BY received_at DESC
        LIMIT :scan
    """), {"site_id": site_id, "since": since, "scan": _SESSION_SCAN_LIMIT}).mappings()

    sessions: dict[str, dict[str, Any]] = {}
    for record in raw:
        r = dict(record)
        key = (r.get("session_id") or "").strip() or (r.get("visitor_id") or "").strip() or r["ip_hash"]
        s = sessions.get(key)
        if s is None:
            s = sessions[key] = {
                "person_key": key, "session_id": r.get("session_id"), "visitor_id": r.get("visitor_id"),
                "ip_address": r["ip_address"], "ip_hash": r["ip_hash"], "ip_confidence": r.get("ip_confidence"),
                "ip_resolution_version": r.get("ip_resolution_version"), "proxy_ip": r.get("proxy_ip"),
                "ip_source": r.get("ip_source"), "last_seen": r["received_at"], "first_seen": r["received_at"],
                "last_page": r.get("page_path"), "landing_path": r.get("landing_path"), "referrer": r.get("referrer"),
                "device": r.get("device"), "user_agent": r.get("user_agent"),
                "browser_language": r.get("browser_language"), "browser_timezone": r.get("browser_timezone"),
                "screen_size": r.get("screen_size"), "utm_campaign": r.get("utm_campaign"),
                "utm_medium": r.get("utm_medium"), "utm_term": r.get("utm_term"), "utm_content": r.get("utm_content"),
                "campaign_id": r.get("campaign_id"), "gclid": r.get("gclid"),
                "gbraid": r.get("gbraid"), "wbraid": r.get("wbraid"), "events": 0, "landings": 0, "page_views": 0,
                "scrolls": 0, "heartbeats": 0, "tel_clicks": 0, "form_submits": 0, "whatsapp_clicks": 0, "_pages": set(),
            }
        s["events"] += 1
        s["first_seen"] = r["received_at"]  # DESC scan → last write is the earliest event
        et = r.get("event_type")
        counter = {"landing": "landings", "page_view": "page_views", "scroll": "scrolls",
                   "heartbeat": "heartbeats", "tel_click": "tel_clicks", "form_submit": "form_submits",
                   "whatsapp_click": "whatsapp_clicks"}.get(et)
        if counter:
            s[counter] += 1
        if r.get("page_path"):
            s["_pages"].add(r["page_path"])
        if r.get("landing_path"):
            s["landing_path"] = r["landing_path"]
        if r.get("referrer"):
            s["referrer"] = r["referrer"]
        for f in ("gclid", "gbraid", "wbraid", "campaign_id", "utm_campaign", "utm_medium", "utm_term", "utm_content", "device"):
            if not s.get(f) and r.get(f):
                s[f] = r[f]

    items: list[dict[str, Any]] = []
    for s in sessions.values():
        s["distinct_pages"] = len(s.pop("_pages"))
        s["ads_attribution"] = _ads_attribution(s)
        score, reasons = 0, []
        if s["tel_clicks"] >= 3:
            score += 35; reasons.append("tel_click_burst")
        if s["events"] >= 30:
            score += 25; reasons.append("session_flood")
        elif s["events"] >= 15:
            score += 12; reasons.append("session_flood")
        s["risk_score"] = min(100, score)
        s["risk_reasons"] = reasons
        items.append(s)
    items.sort(key=lambda z: z["last_seen"], reverse=True)
    return items


def _visitor_stats(cx, site_id: str, since: str) -> dict[str, dict[str, Any]]:
    """Per-visitor_id totals over the window. visitor_id is a per-browser UUID
    that survives IP changes, so it exposes one identity hopping many IPs."""
    rows = cx.execute(text("""
        SELECT visitor_id,
               COUNT(*) AS events,
               COUNT(DISTINCT ip_address) AS ips,
               COUNT(DISTINCT session_id) AS sessions,
               SUM(CASE WHEN event_type='landing' THEN 1 ELSE 0 END) AS landings,
               SUM(CASE WHEN event_type='tel_click' THEN 1 ELSE 0 END) AS tel_clicks
        FROM ads_click_events
        WHERE site_id=:s AND received_at>=:since AND COALESCE(visitor_id,'')<>''
        GROUP BY visitor_id
    """), {"s": site_id, "since": since}).mappings()
    return {r["visitor_id"]: dict(r) for r in rows}


def _visitor_risk(stat: dict[str, Any] | None) -> tuple[int, list[str]]:
    """Risk from one browser identity: rotating across IPs, or clicking the ads
    repeatedly, are both strong invalid-traffic signals."""
    if not stat:
        return 0, []
    boost, reasons = 0, []
    ips = int(stat.get("ips") or 0)
    landings = int(stat.get("landings") or 0)
    if ips >= 3:
        boost += 40; reasons.append("visitor_ip_rotation")
    elif ips == 2:
        boost += 15; reasons.append("visitor_multi_ip")
    if landings >= 5:
        boost += 30; reasons.append("visitor_repeat_clicks")
    elif landings >= 3:
        boost += 12; reasons.append("visitor_repeat_clicks")
    return boost, reasons


@router.get("/sessions")
def sessions(hours: int = Query(default=24, ge=0, le=87_600), limit: int = Query(default=500, ge=1, le=5000),
             site_id: str = "modirankhodro-emdad.com", eng: Engine = Depends(ads_engine)) -> dict[str, Any]:
    since = _cutoff(hours)
    with eng.connect() as cx:
        items = _session_rows(cx, site_id, since)
        vstats = _visitor_stats(cx, site_id, since)
    items = _attach_geo(items)  # adds geo + folds datacenter/proxy into risk_score/reasons
    for s in items:
        st = vstats.get((s.get("visitor_id") or "").strip())
        s["visitor_events"] = int(st["events"]) if st else int(s.get("events") or 0)
        s["visitor_ips"] = int(st["ips"]) if st else 1
        s["visitor_sessions"] = int(st["sessions"]) if st else 1
        s["visitor_landings"] = int(st["landings"]) if st else int(s.get("landings") or 0)
        boost, vreasons = _visitor_risk(st)
        if boost:
            s["risk_score"] = min(100, int(s.get("risk_score") or 0) + boost)
            s["risk_reasons"] = list(s.get("risk_reasons") or []) + vreasons
    items = items[:limit]
    return {"generated_at": _iso(_utcnow()), "site_id": site_id, "hours": hours, "items": items, "count": len(items)}


@router.get("/keywords")
def keywords(hours: int = Query(default=24, ge=0, le=87_600), limit: int = Query(default=300, ge=1, le=2000),
             site_id: str = "modirankhodro-emdad.com", eng: Engine = Depends(ads_engine)) -> dict[str, Any]:
    """Per-keyword (utm_term) performance with a fraud rate derived from the
    per-IP risk score: fraud_rate = share of a keyword's events coming from
    high-risk (>=70) IPs; suspicious = the softer >=35 tier."""
    since = _cutoff(hours)
    with eng.connect() as cx:
        ip_items = _ip_rows(cx, site_id, since, 100_000)
        vstats = _visitor_stats(cx, site_id, since)
    ip_items = _attach_geo(ip_items)
    risk_by_ip = {r["ip_address"]: int(r.get("risk_score") or 0) for r in ip_items}
    suspicious_visitors = {vid for vid, st in vstats.items() if _visitor_risk(st)[0] >= 40}
    with eng.connect() as cx:
        rows = cx.execute(text("""
            SELECT TRIM(utm_term) AS keyword, ip_address, visitor_id, event_type, session_id, received_at
            FROM ads_click_events
            WHERE site_id=:s AND received_at>=:since AND COALESCE(TRIM(utm_term),'')<>''
        """), {"s": site_id, "since": since}).mappings().all()
    agg: dict[str, dict[str, Any]] = {}
    for r in rows:
        key = r["keyword"]
        a = agg.get(key)
        if a is None:
            a = agg[key] = {"keyword": key, "events": 0, "landings": 0, "tel_clicks": 0,
                            "fraud_events": 0, "last_seen": r["received_at"],
                            "_ips": set(), "_sessions": set(), "_susp_ips": set(), "_high_ips": set(),
                            "_visitors": set(), "_bot_visitors": set()}
        a["events"] += 1
        if r["event_type"] == "landing":
            a["landings"] += 1
        elif r["event_type"] == "tel_click":
            a["tel_clicks"] += 1
        ip = r["ip_address"]
        a["_ips"].add(ip)
        if r.get("session_id"):
            a["_sessions"].add(r["session_id"])
        vid = (r.get("visitor_id") or "").strip()
        if vid:
            a["_visitors"].add(vid)
        bad_visitor = vid in suspicious_visitors
        if bad_visitor:
            a["_bot_visitors"].add(vid)
        risk = risk_by_ip.get(ip, 0)
        if risk >= 35:
            a["_susp_ips"].add(ip)
        if risk >= 70:
            a["_high_ips"].add(ip)
        if risk >= 70 or bad_visitor:
            a["fraud_events"] += 1
        if r["received_at"] > a["last_seen"]:
            a["last_seen"] = r["received_at"]
    items = []
    for a in agg.values():
        events = a["events"]
        items.append({
            "keyword": a["keyword"], "events": events, "landings": a["landings"],
            "tel_clicks": a["tel_clicks"], "sessions": len(a["_sessions"]),
            "unique_ips": len(a["_ips"]), "suspicious_ips": len(a["_susp_ips"]),
            "high_risk_ips": len(a["_high_ips"]), "unique_visitors": len(a["_visitors"]),
            "bot_visitors": len(a["_bot_visitors"]), "fraud_events": a["fraud_events"],
            "fraud_rate": round(100 * a["fraud_events"] / events) if events else 0,
            "last_seen": a["last_seen"],
        })
    items.sort(key=lambda z: (z["fraud_rate"], z["events"]), reverse=True)
    return {"generated_at": _iso(_utcnow()), "site_id": site_id, "hours": hours, "items": items[:limit], "count": len(items)}


@router.get("/events.csv")
def events_csv(hours: int = Query(default=0, ge=0, le=87_600),
               limit: int = Query(default=500_000, ge=1, le=500_000),
               site_id: str = "modirankhodro-emdad.com", event_type: str | None = None,
               q: str | None = Query(default=None, max_length=500),
               attribution: str | None = Query(default=None, max_length=20),
               eng: Engine = Depends(ads_engine)) -> Response:
    with eng.connect() as cx:
        rows, _ = _event_rows(cx, site_id, hours, limit, 0, event_type, q, attribution)
    stream = io.StringIO()
    writer = csv.DictWriter(stream, fieldnames=EVENT_EXPORT_COLUMNS, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    filename = f"ads-event-log-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.csv"
    return Response(stream.getvalue(), media_type="text/csv; charset=utf-8", headers={
        "Content-Disposition": f'attachment; filename="{filename}"', "Cache-Control": "no-store",
    })
