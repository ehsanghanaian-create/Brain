"""Evidence-first AI search pilot: official observations, referrals, and prompt samples.

Prompt samples are explicitly separate from real user traffic and official
Search Console/Bing reporting. The API never fabricates an AI ranking.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from typing import Literal
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field, HttpUrl
from sqlalchemy import Engine, text

from ...db.repositories.base import utcnow
from ..deps import engine, require_site
from ..errors import ApiError

router = APIRouter(prefix="/sites/{site_id}/ai-visibility", tags=["ai-visibility"],
                   dependencies=[Depends(require_site)])


class PromptCreate(BaseModel):
    question: str = Field(min_length=8, max_length=600)
    topic: str = Field(default="", max_length=120)
    target_url: HttpUrl | None = None
    intent: Literal["informational", "commercial", "transactional"] = "commercial"
    locale: str = Field(default="fa-IR", min_length=2, max_length=20)
    market: str = Field(default="IR", min_length=2, max_length=10)


class PromptUpdate(BaseModel):
    active: bool


class CitationInput(BaseModel):
    url: HttpUrl
    kind: Literal["inline", "source", "other"] = "source"
    position: int | None = Field(default=None, ge=0, le=30000)


class ObservationCreate(BaseModel):
    provider: str = Field(min_length=2, max_length=60)
    model: str = Field(default="", max_length=120)
    observed_at: date
    answer_text: str = Field(min_length=1, max_length=30000)
    brand_mentioned: bool | None = None
    competitors: list[str] = Field(default_factory=list, max_length=30)
    citations: list[CitationInput] = Field(default_factory=list, max_length=60)
    run_status: Literal["complete", "partial"] = "complete"


class ObservationReview(BaseModel):
    brand_mentioned: bool
    competitors: list[str] = Field(default_factory=list, max_length=30)


class OfficialRow(BaseModel):
    date: date
    platform: Literal["google_ai_search", "google_ai_discover", "bing_ai"]
    page_url: HttpUrl | None = None
    impressions: int | None = Field(default=None, ge=0)
    citations: int | None = Field(default=None, ge=0)


class OfficialImport(BaseModel):
    source_label: str = Field(min_length=3, max_length=160)
    rows: list[OfficialRow] = Field(min_length=1, max_length=2000)


def _site_host(cx, site_id: str) -> str:
    canonical = cx.execute(text("SELECT canonical_url FROM sites WHERE site_id=:s"), {"s": site_id}).scalar() or ""
    host = (urlsplit(canonical).hostname or "").lower().rstrip(".")
    return host.removeprefix("www.")


def _own_domain(url: str, host: str) -> bool:
    candidate = (urlsplit(url).hostname or "").lower().rstrip(".").removeprefix("www.")
    return bool(host and (candidate == host or candidate.endswith("." + host)))


@router.get("/summary")
def summary(site_id: str, days: int = Query(28, ge=7, le=90), eng: Engine = Depends(engine)) -> dict:
    end = datetime.now(timezone.utc).date() - timedelta(days=1)
    start = end - timedelta(days=days - 1)
    params = {"s": site_id, "a": start.isoformat(), "b": end.isoformat()}
    sample_params = {**params, "sample_end": datetime.now(timezone.utc).date().isoformat()}
    with eng.connect() as cx:
        latest_sync = cx.execute(text("""SELECT status,params,notes,finished_at FROM sync_runs
            WHERE site_id=:s AND source='ga4' ORDER BY started_at DESC,rowid DESC LIMIT 1"""), params).mappings().first()
        try:
            sync_notes = json.loads(latest_sync["notes"] or "{}") if latest_sync else {}
            sync_params = json.loads(latest_sync["params"] or "{}") if latest_sync else {}
        except ValueError:
            sync_notes, sync_params = {}, {}
        if not isinstance(sync_notes, dict):
            sync_notes = {}
        if not isinstance(sync_params, dict):
            sync_params = {}
        acquisition_status = sync_notes.get("ai_referral_status") or "not_measured"
        ref = cx.execute(text("""SELECT SUM(sessions) sessions,SUM(engaged_sessions) engaged_sessions,
            SUM(transactions) transactions,SUM(purchase_revenue) purchase_revenue,MAX(date) latest_date,
            MAX(currency) currency,COUNT(DISTINCT currency) currency_count
            FROM ga4_ai_referrals_daily WHERE site_id=:s AND date BETWEEN :a AND :b"""), params).mappings().one()
        sources = [dict(r) for r in cx.execute(text("""SELECT platform,SUM(sessions) sessions,
            SUM(engaged_sessions) engaged_sessions,SUM(transactions) transactions,
            SUM(purchase_revenue) purchase_revenue FROM ga4_ai_referrals_daily
            WHERE site_id=:s AND date BETWEEN :a AND :b GROUP BY platform ORDER BY sessions DESC"""), params).mappings()]
        landing = [dict(r) for r in cx.execute(text("""SELECT landing_page,SUM(sessions) sessions,
            SUM(transactions) transactions,SUM(purchase_revenue) purchase_revenue
            FROM ga4_ai_referrals_daily WHERE site_id=:s AND date BETWEEN :a AND :b
            GROUP BY landing_page ORDER BY sessions DESC LIMIT 15"""), params).mappings()]
        daily = [dict(r) for r in cx.execute(text("""SELECT date,SUM(sessions) sessions,
            SUM(engaged_sessions) engaged_sessions FROM ga4_ai_referrals_daily
            WHERE site_id=:s AND date BETWEEN :a AND :b GROUP BY date ORDER BY date"""), params).mappings()]
        official = [dict(r) for r in cx.execute(text("""SELECT platform,
            SUM(CASE WHEN page_url='' THEN impressions END) impressions,
            SUM(CASE WHEN page_url='' THEN citations END) citations,
            SUM(CASE WHEN page_url<>'' THEN impressions END) page_impressions,
            SUM(CASE WHEN page_url<>'' THEN citations END) page_citations,
            COUNT(*) records,MAX(date) latest_date,MAX(imported_at) imported_at
            FROM ai_visibility_official_daily WHERE site_id=:s AND date BETWEEN :a AND :b
            GROUP BY platform ORDER BY platform"""), params).mappings()]
        official_daily = [dict(r) for r in cx.execute(text("""SELECT date,platform,SUM(impressions) impressions,
            SUM(citations) citations FROM ai_visibility_official_daily
            WHERE site_id=:s AND date BETWEEN :a AND :b AND page_url=''
            GROUP BY date,platform ORDER BY date"""), params).mappings()]
        prompt_count = cx.execute(text("SELECT COUNT(*) FROM ai_visibility_prompts WHERE site_id=:s AND active=1"), params).scalar() or 0
        probe = cx.execute(text("""SELECT COUNT(*) samples,COUNT(brand_mentioned) assessed,
            SUM(CASE WHEN brand_mentioned=1 THEN 1 ELSE 0 END) mentions
            FROM ai_visibility_observations WHERE site_id=:s AND observed_at BETWEEN :a AND :sample_end"""), sample_params).mappings().one()
        citations = cx.execute(text("""SELECT COUNT(*) all_citations,
            SUM(CASE WHEN c.is_own_domain=1 THEN 1 ELSE 0 END) own_citations
            FROM ai_visibility_citations c JOIN ai_visibility_observations o ON o.id=c.observation_id
            WHERE o.site_id=:s AND o.observed_at BETWEEN :a AND :sample_end"""), sample_params).mappings().one()
    covered = bool(sync_params.get("start") and sync_params.get("end") and
                   sync_params["start"] <= start.isoformat() and sync_params["end"] >= end.isoformat())
    complete_referrals = acquisition_status in ("reported", "commerce_unavailable") and covered
    return {
        "site_id": site_id, "period": {"start": start.isoformat(), "end": end.isoformat(), "days": days},
        "referrals": {"status": acquisition_status, "coverage": "full_window" if covered else "partial_or_unknown",
                      "last_sync": latest_sync["finished_at"] if latest_sync else None,
                      "sessions": int(ref["sessions"] or 0) if complete_referrals else None,
                      "engaged_sessions": int(ref["engaged_sessions"] or 0) if complete_referrals else None,
                      "transactions": float(ref["transactions"] or 0) if complete_referrals and acquisition_status == "reported" else None,
                      "purchase_revenue": float(ref["purchase_revenue"] or 0) if complete_referrals and acquisition_status == "reported" and ref["currency_count"] <= 1 else None,
                      "currency": ref["currency"] if ref["currency_count"] == 1 else None,
                      "latest_date": ref["latest_date"], "sources": sources, "landing_pages": landing, "daily": daily,
                      "attribution_note": "Only recognizable GA4 session sources; direct and Google AI traffic are not inferred."},
        "official": {"status": "imported" if official else "not_imported", "platforms": official,
                     "daily": official_daily, "source": "manual_import_from_official_console"},
        "prompts": {"active": int(prompt_count), "samples": int(probe["samples"] or 0),
                    "assessed": int(probe["assessed"] or 0), "mentions": int(probe["mentions"] or 0),
                    "mention_rate": (int(probe["mentions"] or 0) / int(probe["assessed"])) if probe["assessed"] else None,
                    "citations": int(citations["all_citations"] or 0),
                    "own_citations": int(citations["own_citations"] or 0),
                    "scope": "fixed_prompt_samples_not_actual_user_traffic",
                    "period_end": sample_params["sample_end"]},
    }


@router.get("/prompts")
def list_prompts(site_id: str, eng: Engine = Depends(engine)) -> dict:
    with eng.connect() as cx:
        rows = [dict(r) for r in cx.execute(text("""SELECT p.id,p.question,p.topic,p.target_url,p.intent,p.locale,p.market,
            p.active,p.created_at,COUNT(o.id) samples,MAX(o.observed_at) last_observed_at
            FROM ai_visibility_prompts p LEFT JOIN ai_visibility_observations o ON o.prompt_id=p.id
            WHERE p.site_id=:s GROUP BY p.id ORDER BY p.active DESC,p.id DESC LIMIT 300"""), {"s": site_id}).mappings()]
    from ...ai.config import ProviderConfigRepository
    repo = ProviderConfigRepository(eng)
    probe_available = any(p.enabled and p.kind == "openai" and repo.api_key(p) for p in repo.list())
    return {"site_id": site_id, "items": rows, "probe_available": bool(probe_available)}


@router.get("/prompt-suggestions")
def prompt_suggestions(site_id: str, eng: Engine = Depends(engine)) -> dict:
    """Recent GSC queries are candidates, not proof of AI demand or visibility."""
    with eng.connect() as cx:
        latest = cx.execute(text("SELECT MAX(date_to) FROM gsc_query_page WHERE site_id=:s"), {"s": site_id}).scalar()
        if not latest:
            return {"site_id": site_id, "source": "gsc_query_page", "date_to": None, "items": []}
        rows = [dict(r) for r in cx.execute(text("""SELECT query,page,SUM(clicks) clicks,SUM(impressions) impressions,
            ROUND(SUM(position*impressions)/NULLIF(SUM(impressions),0),1) position
            FROM gsc_query_page WHERE site_id=:s AND date_to=:latest AND query<>''
            AND query NOT IN (SELECT question FROM ai_visibility_prompts WHERE site_id=:s)
            GROUP BY query,page HAVING SUM(impressions)>=10
            ORDER BY impressions DESC LIMIT 12"""), {"s": site_id, "latest": latest}).mappings()]
    return {"site_id": site_id, "source": "gsc_query_page", "date_to": latest, "items": rows}


@router.post("/prompts", status_code=201)
def create_prompt(site_id: str, body: PromptCreate, eng: Engine = Depends(engine)) -> dict:
    now = utcnow()
    with eng.begin() as cx:
        url = str(body.target_url) if body.target_url else ""
        if url and not _own_domain(url, _site_host(cx, site_id)):
            raise ApiError(422, "صفحهٔ هدف باید متعلق به همین سایت باشد", code="invalid_target")
        existing = cx.execute(text("""SELECT id FROM ai_visibility_prompts
            WHERE site_id=:s AND question=:q AND locale=:l AND market=:m"""),
            {"s": site_id, "q": body.question.strip(), "l": body.locale, "m": body.market}).scalar()
        if existing:
            raise ApiError(409, "این پرسش قبلاً برای همین بازار ثبت شده است", code="duplicate_prompt")
        result = cx.execute(text("""INSERT INTO ai_visibility_prompts
            (site_id,question,topic,target_url,intent,locale,market,active,created_at,updated_at)
            VALUES (:s,:q,:t,:u,:i,:l,:m,1,:now,:now)"""),
            {"s": site_id, "q": body.question.strip(), "t": body.topic.strip(), "u": url,
             "i": body.intent, "l": body.locale, "m": body.market, "now": now})
    return {"id": result.lastrowid, "site_id": site_id, "created_at": now}


@router.patch("/prompts/{prompt_id}")
def update_prompt(site_id: str, prompt_id: int, body: PromptUpdate, eng: Engine = Depends(engine)) -> dict:
    with eng.begin() as cx:
        result = cx.execute(text("UPDATE ai_visibility_prompts SET active=:a,updated_at=:now WHERE site_id=:s AND id=:p"),
                            {"a": int(body.active), "now": utcnow(), "s": site_id, "p": prompt_id})
        if not result.rowcount:
            raise ApiError(404, "پرسش پیدا نشد", code="not_found")
    return {"id": prompt_id, "active": body.active}


@router.get("/observations")
def list_observations(site_id: str, limit: int = Query(50, ge=1, le=200), eng: Engine = Depends(engine)) -> dict:
    with eng.connect() as cx:
        rows = [dict(r) for r in cx.execute(text("""SELECT o.id,o.prompt_id,p.question,p.target_url,o.provider,o.model,
            o.observed_at,o.capture_method,o.answer_text,o.brand_mentioned,o.mention_method,
            o.competitors_json,o.run_status,o.created_at FROM ai_visibility_observations o
            JOIN ai_visibility_prompts p ON p.id=o.prompt_id AND p.site_id=o.site_id
            WHERE o.site_id=:s ORDER BY o.observed_at DESC,o.id DESC LIMIT :n"""), {"s": site_id, "n": limit}).mappings()]
        ids = [r["id"] for r in rows]
        citation_map: dict[int, list[dict]] = {rid: [] for rid in ids}
        if ids:
            for row in cx.execute(text("""SELECT observation_id,url,domain,citation_kind,position,is_own_domain
                FROM ai_visibility_citations WHERE observation_id IN (""" + ",".join(str(int(i)) for i in ids) + ") ORDER BY id"), {}).mappings():
                citation_map[row["observation_id"]].append(dict(row))
    for row in rows:
        row["competitors"] = json.loads(row.pop("competitors_json") or "[]")
        row["citations"] = citation_map[row["id"]]
    return {"site_id": site_id, "items": rows}


@router.post("/prompts/{prompt_id}/observations", status_code=201)
def create_observation(site_id: str, prompt_id: int, body: ObservationCreate,
                       eng: Engine = Depends(engine)) -> dict:
    with eng.begin() as cx:
        prompt = cx.execute(text("SELECT id FROM ai_visibility_prompts WHERE site_id=:s AND id=:p"),
                            {"s": site_id, "p": prompt_id}).first()
        if not prompt:
            raise ApiError(404, "پرسش پیدا نشد", code="not_found")
        own_host = _site_host(cx, site_id)
        result = cx.execute(text("""INSERT INTO ai_visibility_observations
            (site_id,prompt_id,provider,model,observed_at,capture_method,answer_text,brand_mentioned,
             mention_method,competitors_json,run_status,created_at)
            VALUES (:s,:p,:provider,:model,:observed,'manual',:answer,:mentioned,'manual',:competitors,:status,:now)"""),
            {"s": site_id, "p": prompt_id, "provider": body.provider.strip(), "model": body.model.strip(),
             "observed": body.observed_at.isoformat(), "answer": body.answer_text.strip(),
             "mentioned": None if body.brand_mentioned is None else int(body.brand_mentioned),
             "competitors": json.dumps([c.strip() for c in body.competitors if c.strip()], ensure_ascii=False),
             "status": body.run_status, "now": utcnow()})
        seen = set()
        for citation in body.citations:
            url = str(citation.url)
            if (url, citation.kind) in seen:
                continue
            seen.add((url, citation.kind))
            host = (urlsplit(url).hostname or "").lower()
            cx.execute(text("""INSERT INTO ai_visibility_citations
                (observation_id,url,domain,citation_kind,position,is_own_domain)
                VALUES (:o,:u,:d,:k,:pos,:own)"""),
                {"o": result.lastrowid, "u": url, "d": host, "k": citation.kind,
                 "pos": citation.position, "own": int(_own_domain(url, own_host))})
    return {"id": result.lastrowid, "site_id": site_id, "citations": len(seen)}


@router.post("/prompts/{prompt_id}/probe", status_code=201)
def run_prompt_probe(site_id: str, prompt_id: int, eng: Engine = Depends(engine)) -> dict:
    """One explicit, billable API sample; never presented as consumer ChatGPT reach."""
    from ...ai.config import ProviderConfigRepository
    from ...ai.visibility_probe import ProbeUnavailable, probe_openai

    today = datetime.now(timezone.utc).date().isoformat()
    with eng.connect() as cx:
        prompt = cx.execute(text("""SELECT question,locale,market,active FROM ai_visibility_prompts
            WHERE site_id=:s AND id=:p"""), {"s": site_id, "p": prompt_id}).mappings().first()
        if not prompt:
            raise ApiError(404, "پرسش پیدا نشد", code="not_found")
        if not prompt["active"]:
            raise ApiError(409, "پرسش غیرفعال است", code="inactive_prompt")
        count = cx.execute(text("""SELECT COUNT(*) FROM ai_visibility_observations
            WHERE site_id=:s AND prompt_id=:p AND observed_at=:today AND capture_method='provider_api'"""),
                           {"s": site_id, "p": prompt_id, "today": today}).scalar() or 0
        if count >= 3:
            raise ApiError(429, "سقف سه نمونهٔ API برای این پرسش در امروز پر شده است", code="probe_limit")
    repo = ProviderConfigRepository(eng)
    configured = [(p, repo.api_key(p)) for p in repo.list() if p.kind == "openai" and p.enabled]
    selected = next(((p, key) for p, key in configured if key), None)
    if selected is None:
        raise ApiError(409, "برای نمونهٔ خودکار باید کلید OpenAI در تنظیمات AI ثبت شود", code="probe_not_configured")
    provider, key = selected
    try:
        result = probe_openai(prompt["question"], prompt["locale"], prompt["market"],
                              provider.default_model or "gpt-4.1-mini", key)
    except ProbeUnavailable as exc:
        raise ApiError(502, "نمونهٔ جست‌وجوی AI کامل نشد؛ داده‌ای ثبت نشد", code="probe_failed") from exc
    with eng.begin() as cx:
        own_host = _site_host(cx, site_id)
        inserted = cx.execute(text("""INSERT INTO ai_visibility_observations
            (site_id,prompt_id,provider,model,observed_at,capture_method,answer_text,brand_mentioned,
             mention_method,competitors_json,run_status,created_at)
            VALUES (:s,:p,'OpenAI API web search',:model,:today,'provider_api',:answer,NULL,
                    'pending_review','[]',:status,:now)"""),
            {"s": site_id, "p": prompt_id, "model": result["model"], "today": today,
             "answer": result["answer_text"], "status": result["status"], "now": utcnow()})
        for citation in result["citations"]:
            url = citation["url"]
            cx.execute(text("""INSERT INTO ai_visibility_citations
                (observation_id,url,domain,citation_kind,position,is_own_domain)
                VALUES (:o,:u,:d,:k,:pos,:own)"""),
                {"o": inserted.lastrowid, "u": url, "d": (urlsplit(url).hostname or "").lower(),
                 "k": citation["kind"], "pos": citation["position"],
                 "own": int(_own_domain(url, own_host))})
    return {"id": inserted.lastrowid, "site_id": site_id, "capture_method": "provider_api",
            "citations": len(result["citations"]), "assessment": "pending_review"}


@router.patch("/observations/{observation_id}/review")
def review_observation(site_id: str, observation_id: int, body: ObservationReview,
                       eng: Engine = Depends(engine)) -> dict:
    with eng.begin() as cx:
        changed = cx.execute(text("""UPDATE ai_visibility_observations SET
            brand_mentioned=:mentioned,mention_method='manual_review',competitors_json=:competitors
            WHERE site_id=:s AND id=:id"""),
            {"mentioned": int(body.brand_mentioned), "competitors": json.dumps(
                [name.strip() for name in body.competitors if name.strip()], ensure_ascii=False),
             "s": site_id, "id": observation_id})
        if not changed.rowcount:
            raise ApiError(404, "پاسخ پیدا نشد", code="not_found")
    return {"id": observation_id, "brand_mentioned": body.brand_mentioned, "reviewed": True}


@router.post("/official-import")
def import_official(site_id: str, body: OfficialImport, eng: Engine = Depends(engine)) -> dict:
    now = utcnow()
    with eng.begin() as cx:
        own_host = _site_host(cx, site_id)
        for row in body.rows:
            if row.platform.startswith("google") and (row.impressions is None or row.citations is not None):
                raise ApiError(422, "گزارش گوگل باید فقط تعداد نمایش داشته باشد", code="invalid_metric")
            if row.platform == "bing_ai" and (row.citations is None or row.impressions is not None):
                raise ApiError(422, "گزارش بینگ باید فقط تعداد استناد داشته باشد", code="invalid_metric")
            url = str(row.page_url) if row.page_url else ""
            if url and not _own_domain(url, own_host):
                raise ApiError(422, "URL گزارش باید متعلق به همین سایت باشد", code="invalid_page")
            cx.execute(text("""INSERT INTO ai_visibility_official_daily
                (site_id,date,platform,page_url,impressions,citations,source_label,imported_at)
                VALUES (:s,:d,:p,:u,:i,:c,:source,:now)
                ON CONFLICT(site_id,date,platform,page_url) DO UPDATE SET
                  impressions=excluded.impressions,citations=excluded.citations,
                  source_label=excluded.source_label,imported_at=excluded.imported_at"""),
                {"s": site_id, "d": row.date.isoformat(), "p": row.platform, "u": url,
                 "i": row.impressions, "c": row.citations, "source": body.source_label.strip(), "now": now})
    return {"site_id": site_id, "imported": len(body.rows), "imported_at": now,
            "source": "manual_import_from_official_console"}
