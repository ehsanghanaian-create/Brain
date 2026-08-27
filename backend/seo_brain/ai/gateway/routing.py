"""Task Router — Task → priority → explicit route (user, ai_routes) or policy per kind → available models → cost/quality ranking → chain.

Routing is deterministic and explained (`reason`). Learning may *recommend* routes; only humans change ai_routes.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import Engine, select

from ...db.repositories.base import loads, utcnow
from ...db.tables import ai_routes
from ..config import GATEWAY_KINDS, KEYLESS_KINDS, ProviderConfigRepository, env_api_key
from .catalog import TIERS
from .gateway import Gateway, RouteStep

TASK_KINDS_V2 = ("research", "outline", "article_section", "article_long", "rewrite", "seo_review", "fact_check", "title_meta", "faq", "translation", "internal_linking", "schema", "brief", "keyword_analysis", "content_writing", "seo_analysis", "generic")
TASK_FA = {"research": "تحقیق", "outline": "ساختار (Outline)", "article_section": "نگارش بخش مقاله", "article_long": "نگارش مقاله بلند", "rewrite": "بازنویسی", "seo_review": "بازبینی سئو", "fact_check": "راستی‌آزمایی",
           "title_meta": "عنوان/متا", "faq": "سؤالات متداول", "translation": "ترجمه", "internal_linking": "لینک‌سازی داخلی", "schema": "اسکیما", "brief": "بریف", "keyword_analysis": "تحلیل کلمات کلیدی",
           "content_writing": "نگارش محتوا", "seo_analysis": "تحلیل سئو", "generic": "عمومی"}
# policy: preferred tiers in order + required/preferred tags
POLICY: dict[str, dict[str, Any]] = {
    "research": {"tiers": ["balanced", "quality", "reasoning", "fast"], "prefer": ["long_form"]},
    "outline": {"tiers": ["fast", "balanced", "quality"], "prefer": ["cheap", "json"]},
    "article_section": {"tiers": ["quality", "balanced", "reasoning"], "prefer": ["persian", "long_form"]},
    "article_long": {"tiers": ["quality", "reasoning", "balanced"], "prefer": ["persian", "long_form"]},
    "content_writing": {"tiers": ["quality", "balanced"], "prefer": ["persian", "long_form"]},
    "rewrite": {"tiers": ["fast", "balanced"], "prefer": ["cheap"]},
    "seo_review": {"tiers": ["reasoning", "quality", "balanced"], "prefer": ["reasoning", "json"]},
    "seo_analysis": {"tiers": ["reasoning", "quality", "balanced"], "prefer": ["reasoning", "json"]},
    "fact_check": {"tiers": ["reasoning", "quality", "balanced"], "prefer": ["reasoning", "json"]},
    "title_meta": {"tiers": ["fast", "balanced"], "prefer": ["cheap"]},
    "faq": {"tiers": ["fast", "balanced"], "prefer": ["cheap", "json"]},
    "translation": {"tiers": ["balanced", "quality", "fast"], "prefer": ["translation"]},
    "internal_linking": {"tiers": ["fast", "balanced"], "prefer": ["json", "cheap"]},
    "schema": {"tiers": ["fast", "balanced"], "prefer": ["json"]},
    "brief": {"tiers": ["balanced", "quality", "fast"], "prefer": ["json"]},
    "keyword_analysis": {"tiers": ["balanced", "fast"], "prefer": ["json"]},
    "generic": {"tiers": ["balanced", "fast", "quality"], "prefer": []},
}


@dataclass
class RoutingDecision:
    chain: list[RouteStep]
    reason: str
    policy: str                     # explicit | auto | echo
    candidates: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"chain": [s.__dict__ for s in self.chain], "reason": self.reason, "policy": self.policy, "candidates": self.candidates[:10]}


class TaskRouter:
    def __init__(self, engine: Engine, gateway: Gateway):
        self.engine = engine
        self.gw = gateway
        self.cfg = ProviderConfigRepository(engine)

    def _available(self, site_id: str | None) -> list[dict[str, Any]]:
        provs = {p.id: p for p in self.cfg.list() if p.enabled}
        health = {h["provider"]: h for h in self.gw.health()}
        now = utcnow()
        out = []
        for m in self.gw.models(enabled_only=True):
            p = provs.get(m["provider_id"])
            if not p:
                continue
            h = health.get(p.name)
            if h and h.get("breaker_open_until") and h["breaker_open_until"] > now:
                continue
            if p.kind in GATEWAY_KINDS and m.get("source") == "discovered":
                continue        # gateways: auto-routing uses only the curated auto* entries; discovered provider/model ids are for explicit selection
            out.append({**m, "provider": p.name, "kind": p.kind, "p50_ms": (h or {}).get("p50_ms"), "has_key": bool(p.secret_ref) or p.kind in KEYLESS_KINDS or bool(env_api_key(p.kind))})
        return [m for m in out if m["has_key"]]

    def resolve(self, task_kind: str, site_id: str | None, priority: str = "normal", quality_min: str | None = None, override: dict[str, str] | None = None) -> RoutingDecision:
        # 0) explicit override from the caller (Studio) — still validated against enabled models
        avail = self._available(site_id)
        if override and override.get("provider") and override.get("model"):
            chain = [RouteStep(override["provider"], override["model"], "انتخاب دستی کاربر")]
            chain += self._auto_chain(task_kind, avail, exclude={(override["provider"], override["model"])})[:2]
            return RoutingDecision(chain, "انتخاب دستی کاربر در Studio + جایگزین‌های خودکار", "explicit", avail)
        # 1) explicit route (site, then global) with fallbacks
        with self.engine.connect() as cx:
            rows = cx.execute(select(ai_routes).where(ai_routes.c.task_kind == task_kind)).all()
        provs = {p.id: p.name for p in self.cfg.list()}
        for scope in ([site_id] if site_id else []) + ["*"]:
            r = next((dict(x._mapping) for x in rows if x._mapping["site_id"] == scope), None)
            if r and r.get("provider_id") and provs.get(r["provider_id"]) and r.get("policy", "auto") in ("explicit", "auto"):
                pname = provs[r["provider_id"]]
                model = r.get("model") or next((m["model_id"] for m in avail if m["provider"] == pname), None)
                if model:
                    chain = [RouteStep(pname, model, "مسیر تنظیم‌شده توسط کاربر")]
                    for fb in loads(r.get("fallbacks"), []) or []:
                        fp = provs.get(fb.get("provider_id"))
                        if fp and fb.get("model"): chain.append(RouteStep(fp, fb["model"], "جایگزین تنظیم‌شده"))
                    if r.get("fallback_provider_id") and provs.get(r["fallback_provider_id"]):
                        chain.append(RouteStep(provs[r["fallback_provider_id"]], r.get("fallback_model") or model, "جایگزین تنظیم‌شده"))
                    chain += self._auto_chain(task_kind, avail, exclude={(s.provider, s.model) for s in chain})[:1]
                    return RoutingDecision(chain, f"مسیر صریح برای «{TASK_FA.get(task_kind, task_kind)}» ({'سایت' if scope != '*' else 'سراسری'})", "explicit", avail)
        # 2) policy
        chain = self._auto_chain(task_kind, avail, priority=priority, quality_min=quality_min)
        if not chain:
            return RoutingDecision([RouteStep("echo", "echo-1", "هیچ ارائه‌دهنده واقعی پیکربندی/فعال نیست")], "بدون ارائه‌دهنده واقعی — EchoProvider (خروجی نمایشی)", "echo", avail)
        pol = POLICY.get(task_kind, POLICY["generic"])
        return RoutingDecision(chain, f"سیاست خودکار «{TASK_FA.get(task_kind, task_kind)}»: رده {'/'.join(pol['tiers'][:2])}" + (f"، ترجیح {'/'.join(pol['prefer'])}" if pol['prefer'] else "") + f"؛ اولویت {priority}", "auto", avail)

    def _auto_chain(self, task_kind: str, avail: list[dict], priority: str = "normal", quality_min: str | None = None, exclude: set | None = None) -> list[RouteStep]:
        pol = POLICY.get(task_kind, POLICY["generic"])
        exclude = exclude or set()
        tier_rank = {t: i for i, t in enumerate(pol["tiers"])}
        min_rank = TIERS.index(quality_min) if quality_min in TIERS else 0
        scored = []
        for m in avail:
            if (m["provider"], m["model_id"]) in exclude or m["tier"] not in tier_rank:
                continue
            if TIERS.index(m["tier"]) < min_rank and m["tier"] != "reasoning":
                continue
            prefer_hits = sum(1 for t in pol["prefer"] if t in m["tags"])
            price = (m["price_in_per_m"] or 0) + 3 * (m["price_out_per_m"] or 0)
            # lower is better: tier order first, then fewer preferred tags → penalty, then price (priority high → price matters less), then latency
            key = (tier_rank[m["tier"]], -prefer_hits, price * (0.3 if priority == "high" else 1.0), m.get("p50_ms") or 5000)
            scored.append((key, m))
        scored.sort(key=lambda x: x[0])
        chain = []
        for key, m in scored[:3]:
            chain.append(RouteStep(m["provider"], m["model_id"], f"رده {m['tier']}" + (f"، برچسب‌ها {', '.join(t for t in pol['prefer'] if t in m['tags'])}" if pol["prefer"] else "") + f"، قیمت خروجی {m['price_out_per_m']}$/M"))
        return chain
