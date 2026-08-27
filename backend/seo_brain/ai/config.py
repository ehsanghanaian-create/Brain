"""AI provider configuration (phase 6): CRUD in `ai_providers`, secrets in the SecretStore, connection tests,
task routes in `ai_routes`. Real completion providers arrive in phase 9; this module already exposes the
`describe()`/`test()` surface the UI needs and never returns a key.
"""
from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from typing import Any, Callable

import httpx
from sqlalchemy import Engine, and_, delete, select, text

from ..core.secrets import SecretStore, get_secret_store
from ..db.repositories.base import Repository, dumps, loads, utcnow
from ..db.tables import ai_providers, ai_routes

log = logging.getLogger("ai.config")

PROVIDER_KINDS: dict[str, dict[str, Any]] = {
    "anthropic": {"label": "Claude (Anthropic)", "base_url": "https://api.anthropic.com", "models": ["claude-sonnet-5", "claude-opus-5", "claude-haiku-4-5", "claude-opus-4-8", "claude-sonnet-4-6", "claude-fable-5"], "needs_key": True,
                  "setup": {"console_url": "https://platform.claude.com/settings/keys", "key_prefix": "sk-ant-", "docs": "https://platform.claude.com/docs/en/get-started",
                            "fa": "کلید API را از کنسول Anthropic (Settings → API keys) بسازید و همین‌جا وارد کنید. کلید فقط یک‌بار ارسال می‌شود، با DPAPI روی همین دستگاه رمزنگاری می‌شود و هرگز در پاسخ API، لاگ یا دیتابیس ظاهر نمی‌شود."}},
    "openai": {"label": "ChatGPT (OpenAI)", "base_url": "https://api.openai.com/v1", "models": ["gpt-5", "gpt-5-mini", "gpt-4.1", "gpt-4o"], "needs_key": True},
    "google": {"label": "Gemini (Google)", "base_url": "https://generativelanguage.googleapis.com/v1beta", "models": ["gemini-2.5-pro", "gemini-2.5-flash"], "needs_key": True},
    "openrouter": {"label": "OpenRouter", "base_url": "https://openrouter.ai/api/v1", "models": [], "needs_key": True},
    "groq": {"label": "Groq Cloud (سهمیه رایگان)", "base_url": "https://api.groq.com/openai/v1",
             "models": ["qwen/qwen3.6-27b", "openai/gpt-oss-120b", "openai/gpt-oss-20b"], "needs_key": True,
             "setup": {"console_url": "https://console.groq.com/keys", "key_prefix": "gsk_", "docs": "https://console.groq.com/docs/quickstart",
                       "fa": "کلید Groq Cloud روی سرور ذخیره می‌شود. پلن رایگان برای Qwen 3.6 روزانه ۱۰۰۰ درخواست و ۲۰۰هزار توکن دارد؛ در برخورد با محدودیت، SEO Brain سراغ مسیر جایگزین می‌رود."}},
    "cloudflare": {"label": "Cloudflare Workers AI (سهمیه رایگان)", "base_url": "",
                    "models": ["@cf/qwen/qwen3-30b-a3b-fp8", "@cf/openai/gpt-oss-20b"], "needs_key": True,
                    "setup": {"console_url": "https://dash.cloudflare.com/profile/api-tokens", "key_prefix": "", "docs": "https://developers.cloudflare.com/workers-ai/configuration/open-ai-compatibility/",
                              "fa": "یک API Token با دسترسی Workers AI و Account ID لازم است. Base URL باید به شکل https://api.cloudflare.com/client/v4/accounts/ACCOUNT_ID/ai/v1 ثبت شود؛ کلید فقط روی سرور نگهداری می‌شود."}},
    "ollama": {"label": "مدل محلی (Ollama)", "base_url": "http://127.0.0.1:11434", "models": [], "needs_key": False},
    "custom": {"label": "API سفارشی (سازگار با OpenAI)", "base_url": "", "models": [], "needs_key": False},
    # external routing gateway (OpenAI-compatible) — SEO Brain Gateway → OmniRoute → Claude/OpenAI/Gemini/…
    "omniroute": {"label": "OmniRoute (گیت‌وی مسیریابی)", "base_url": "http://127.0.0.1:20128/v1", "models": ["auto", "auto/fast", "auto/cheap", "auto/coding"], "needs_key": False, "is_gateway": True,
                  "setup": {"console_url": "http://127.0.0.1:20128/dashboard", "key_prefix": "", "docs": "https://github.com/diegosouzapw/OmniRoute",
                            "fa": "OmniRoute یک گیت‌وی متن‌باز است که Claude/OpenAI/Gemini و صدها ارائه‌دهنده دیگر را پشت یک endpoint سازگار با OpenAI قرار می‌دهد (پیش‌فرض http://127.0.0.1:20128/v1؛ نصب: npm i -g omniroute). کلید API اختیاری است (Dashboard → Endpoints) و فقط در SecretStore نگهداری می‌شود. Gateway خود SEO Brain (بودجه، دفتر مصرف، اعتبارسنجی، مسیردهی) دست‌نخورده می‌ماند."}},
}
KEYLESS_KINDS = ("ollama", "custom", "omniroute")      # configured without a stored key
GATEWAY_KINDS = ("omniroute",)                          # external routers (provider/model ids resolved upstream)
TASK_KINDS = ("content_writing", "seo_analysis", "research", "brief", "keyword_analysis", "internal_linking", "schema", "generic",
              # phase 9 task kinds
              "outline", "article_section", "article_long", "rewrite", "seo_review", "fact_check", "title_meta", "faq", "translation")


@dataclass
class ProviderConfig:
    name: str
    kind: str
    base_url: str | None = None
    default_model: str | None = None
    models: list[str] = field(default_factory=list)
    enabled: bool = True
    secret_ref: str | None = None
    key_hint: str | None = None
    last_test: dict[str, Any] | None = None
    id: int | None = None
    created_at: str | None = None
    updated_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d.pop("secret_ref", None)                    # never leak the reference either
        d["has_key"] = bool(self.secret_ref)
        d["kind_label"] = PROVIDER_KINDS.get(self.kind, {}).get("label", self.kind)
        d["is_gateway"] = self.kind in GATEWAY_KINDS
        d["route_kind"] = "gateway" if self.kind in GATEWAY_KINDS else "direct"
        d["endpoint_url"] = self.base_url                # explicit alias for gateways (same column)
        d["configured"] = bool(self.enabled and (self.secret_ref or self.kind in KEYLESS_KINDS))
        return d


def _row(m) -> ProviderConfig:
    return ProviderConfig(id=m["id"], name=m["name"], kind=m["kind"], base_url=m["base_url"], default_model=m["default_model"], models=loads(m["models"], []),
                          enabled=bool(m["enabled"]), secret_ref=m["secret_ref"], key_hint=m["key_hint"], last_test=loads(m["last_test"], None),
                          created_at=m["created_at"], updated_at=m["updated_at"])


class ProviderConfigRepository(Repository):
    def __init__(self, engine: Engine, secrets: SecretStore | None = None):
        super().__init__(engine)
        self.secrets = secrets or get_secret_store()

    def list(self) -> list[ProviderConfig]:
        with self.engine.connect() as cx:
            return [_row(r._mapping) for r in cx.execute(select(ai_providers).order_by(ai_providers.c.id))]

    def get(self, pid: int) -> ProviderConfig | None:
        with self.engine.connect() as cx:
            r = cx.execute(select(ai_providers).where(ai_providers.c.id == pid)).first()
        return _row(r._mapping) if r else None

    def get_by_name(self, name: str) -> ProviderConfig | None:
        with self.engine.connect() as cx:
            r = cx.execute(select(ai_providers).where(ai_providers.c.name == name)).first()
        return _row(r._mapping) if r else None

    def create(self, name: str, kind: str, api_key: str | None = None, base_url: str | None = None, default_model: str | None = None,
               models: list[str] | None = None, enabled: bool = True) -> ProviderConfig:
        if kind not in PROVIDER_KINDS:
            raise ValueError(f"unknown provider kind '{kind}'")
        if self.get_by_name(name):
            raise ValueError(f"provider '{name}' already exists")
        kd = PROVIDER_KINDS[kind]
        now = utcnow()
        with self.engine.begin() as cx:
            res = cx.execute(ai_providers.insert().values(name=name, kind=kind, base_url=base_url or kd["base_url"] or None, default_model=default_model or (kd["models"][0] if kd["models"] else None),
                                                          models=dumps(models if models is not None else kd["models"]), enabled=int(enabled), created_at=now, updated_at=now))
            pid = int(res.inserted_primary_key[0])
        if api_key:
            self.set_key(pid, api_key)
        return self.get(pid)  # type: ignore[return-value]

    def update(self, pid: int, **fields) -> ProviderConfig | None:
        api_key = fields.pop("api_key", None)
        allowed = {k: v for k, v in fields.items() if k in ("name", "base_url", "default_model", "models", "enabled") and v is not None}
        if "models" in allowed:
            allowed["models"] = dumps(allowed["models"])
        if "enabled" in allowed:
            allowed["enabled"] = int(bool(allowed["enabled"]))
        if allowed:
            allowed["updated_at"] = utcnow()
            with self.engine.begin() as cx:
                cx.execute(ai_providers.update().where(ai_providers.c.id == pid).values(**allowed))
        if api_key:
            self.set_key(pid, api_key)
        return self.get(pid)

    def set_key(self, pid: int, api_key: str) -> None:
        ref = f"ai-provider-{pid}"
        self.secrets.set(ref, api_key)
        with self.engine.begin() as cx:
            cx.execute(ai_providers.update().where(ai_providers.c.id == pid).values(secret_ref=ref, key_hint=SecretStore.hint(api_key), updated_at=utcnow()))

    def clear_key(self, pid: int) -> None:
        p = self.get(pid)
        if p and p.secret_ref:
            self.secrets.delete(p.secret_ref)
        with self.engine.begin() as cx:
            cx.execute(ai_providers.update().where(ai_providers.c.id == pid).values(secret_ref=None, key_hint=None, updated_at=utcnow()))

    def api_key(self, p: ProviderConfig) -> str | None:
        return self.secrets.get(p.secret_ref)

    def delete(self, pid: int) -> bool:
        p = self.get(pid)
        if not p:
            return False
        if p.secret_ref:
            self.secrets.delete(p.secret_ref)
        with self.engine.begin() as cx:
            cx.execute(ai_routes.update().where(ai_routes.c.provider_id == pid).values(provider_id=None, model=None, updated_at=utcnow()))
            cx.execute(ai_routes.update().where(ai_routes.c.fallback_provider_id == pid).values(fallback_provider_id=None, fallback_model=None, updated_at=utcnow()))
            cx.execute(text("DELETE FROM ai_models WHERE provider_id=:p"), {"p": pid})          # catalog rows (FK) — phase 9 tables
            cx.execute(delete(ai_providers).where(ai_providers.c.id == pid))
        return True

    def record_test(self, pid: int, result: dict[str, Any]) -> None:
        with self.engine.begin() as cx:
            cx.execute(ai_providers.update().where(ai_providers.c.id == pid).values(last_test=dumps(result), updated_at=utcnow()))

    # ---- routes
    def routes(self, site_id: str | None = None) -> list[dict[str, Any]]:
        with self.engine.connect() as cx:
            rows = cx.execute(select(ai_routes).where(ai_routes.c.site_id.in_(["*"] + ([site_id] if site_id else [])))).all()
        by_kind: dict[str, dict] = {}
        for r in rows:
            m = dict(r._mapping)
            if m["site_id"] == "*" and m["task_kind"] in by_kind:
                continue
            by_kind[m["task_kind"]] = m
        names = {p.id: p for p in self.list()}
        out = []
        for k in TASK_KINDS:
            m = by_kind.get(k, {"task_kind": k, "site_id": "*", "provider_id": None, "model": None, "fallback_provider_id": None, "fallback_model": None, "updated_at": None, "fallbacks": "[]", "policy": "auto"})
            p = names.get(m["provider_id"]); f = names.get(m["fallback_provider_id"])
            fbs = loads(m.get("fallbacks"), []) or []
            out.append({**m, "fallbacks": [{**fb, "provider_name": (names.get(fb.get("provider_id")).name if names.get(fb.get("provider_id")) else None)} for fb in fbs],
                        "policy": m.get("policy") or "auto", "provider_name": p.name if p else None, "fallback_provider_name": f.name if f else None})
        return out

    def set_route(self, task_kind: str, provider_id: int | None, model: str | None, fallback_provider_id: int | None = None, fallback_model: str | None = None,
                  site_id: str = "*", policy: str | None = None, fallbacks: list[dict] | None = None) -> dict[str, Any]:
        if task_kind not in TASK_KINDS:
            raise ValueError(f"unknown task kind '{task_kind}'")
        if policy is not None and policy not in ("explicit", "auto", "echo"):
            raise ValueError("policy must be explicit|auto|echo")
        vals: dict[str, Any] = {"task_kind": task_kind, "site_id": site_id, "provider_id": provider_id, "model": model, "fallback_provider_id": fallback_provider_id,
                                "fallback_model": fallback_model, "updated_at": utcnow()}
        if policy is not None:
            vals["policy"] = policy
        if fallbacks is not None:
            vals["fallbacks"] = dumps([{"provider_id": int(f["provider_id"]), "model": str(f.get("model") or "")} for f in fallbacks if f.get("provider_id")])
        with self.engine.begin() as cx:
            self.upsert(cx, ai_routes, vals, conflict=["task_kind", "site_id"])
        return next(r for r in self.routes(site_id if site_id != "*" else None) if r["task_kind"] == task_kind)

    # ---- recommended routes per provider kind (applied only on explicit human action — routing never changes by itself)
    def recommended_routes(self, p: ProviderConfig) -> list[dict[str, Any]]:
        """Suggested explicit routes for a provider (model + fallback), by task kind. Only Claude has a curated table for now."""
        rec = RECOMMENDED_ROUTES.get(p.kind, {})
        return [{"task_kind": k, "provider_id": p.id, "provider_name": p.name, "model": v[0], "fallback_model": v[1], "policy": "explicit"} for k, v in rec.items() if k in TASK_KINDS]

    def apply_recommended_routes(self, pid: int, site_id: str = "*", overwrite: bool = True) -> list[dict[str, Any]]:
        p = self.get(pid)
        if not p:
            raise ValueError("provider not found")
        current = {r["task_kind"]: r for r in self.routes(None if site_id == "*" else site_id)}
        applied = []
        for rec in self.recommended_routes(p):
            cur = current.get(rec["task_kind"]) or {}
            if not overwrite and cur.get("provider_id"):
                continue
            applied.append(self.set_route(rec["task_kind"], pid, rec["model"], fallback_provider_id=pid if rec["fallback_model"] else None, fallback_model=rec["fallback_model"], site_id=site_id, policy="explicit"))
        return applied


# task_kind → (primary model, fallback model) — Sonnet balanced, Opus quality, Haiku fast
RECOMMENDED_ROUTES: dict[str, dict[str, tuple[str, str | None]]] = {
    # Cloud-only free-tier routes. A second model handles model-specific throttling.
    "groq": {k: (("openai/gpt-oss-20b", "qwen/qwen3.6-27b") if k in ("outline", "rewrite", "title_meta", "faq", "internal_linking", "schema", "keyword_analysis", "generic") else ("qwen/qwen3.6-27b", "openai/gpt-oss-120b")) for k in TASK_KINDS},
    "cloudflare": {k: (("@cf/openai/gpt-oss-20b", "@cf/qwen/qwen3-30b-a3b-fp8") if k in ("outline", "rewrite", "title_meta", "faq", "internal_linking", "schema", "keyword_analysis", "generic") else ("@cf/qwen/qwen3-30b-a3b-fp8", "@cf/openai/gpt-oss-20b")) for k in TASK_KINDS},
    # OmniRoute: let its own router pick upstreams; fast tasks → auto/fast; everything falls back to plain auto
    "omniroute": {k: (("auto/fast", "auto") if k in ("outline", "rewrite", "title_meta", "faq", "internal_linking", "schema", "keyword_analysis", "generic") else ("auto", "auto/fast")) for k in TASK_KINDS},
    "anthropic": {
        "article_long": ("claude-sonnet-5", "claude-opus-5"), "article_section": ("claude-sonnet-5", "claude-opus-5"), "content_writing": ("claude-sonnet-5", "claude-opus-5"),
        "seo_review": ("claude-sonnet-5", "claude-haiku-4-5"), "seo_analysis": ("claude-sonnet-5", "claude-haiku-4-5"), "fact_check": ("claude-sonnet-5", "claude-opus-5"),
        "research": ("claude-sonnet-5", "claude-haiku-4-5"), "brief": ("claude-sonnet-5", "claude-haiku-4-5"), "translation": ("claude-sonnet-5", "claude-haiku-4-5"),
        "outline": ("claude-haiku-4-5", "claude-sonnet-5"), "rewrite": ("claude-haiku-4-5", "claude-sonnet-5"), "title_meta": ("claude-haiku-4-5", "claude-sonnet-5"), "faq": ("claude-haiku-4-5", "claude-sonnet-5"),
        "internal_linking": ("claude-haiku-4-5", "claude-sonnet-5"), "schema": ("claude-haiku-4-5", "claude-sonnet-5"), "keyword_analysis": ("claude-haiku-4-5", "claude-sonnet-5"), "generic": ("claude-haiku-4-5", "claude-sonnet-5"),
    },
}


# --------------------------------------------------------------------------- connection tests (read-only GETs)
def test_provider(p: ProviderConfig, api_key: str | None, fetch: Callable[..., httpx.Response] | None = None) -> dict[str, Any]:
    """Probe the provider's model-list endpoint. Never sends prompts, never logs the key."""
    kd = PROVIDER_KINDS.get(p.kind, {})
    base = (p.base_url or kd.get("base_url") or "").rstrip("/")
    get = fetch or (lambda url, headers=None: httpx.get(url, headers=headers or {}, timeout=20))
    if kd.get("needs_key") and not api_key:
        return {"ok": False, "status": "not_configured", "message": "کلید API ثبت نشده است", "tested_at": utcnow()}
    try:
        if p.kind == "anthropic":
            r = get(f"{base}/v1/models", {"x-api-key": api_key or "", "anthropic-version": "2023-06-01"})
            models = [m.get("id") for m in (r.json().get("data") or [])] if r.status_code == 200 else []
        elif p.kind == "cloudflare":
            marker = "/accounts/"
            if marker not in base or "/ai" not in base.split(marker, 1)[1]:
                return {"ok": False, "status": "error", "message": "Base URL کلادفلر نامعتبر است", "tested_at": utcnow()}
            root, rest = base.split(marker, 1)
            account_id = rest.split("/", 1)[0]
            r = get(f"{root}{marker}{account_id}/tokens/verify", {"Authorization": f"Bearer {api_key}"})
            models = list(p.models or kd.get("models") or [])
        elif p.kind in ("openai", "openrouter", "groq", "custom", "omniroute"):
            r = get(f"{base}/models", {"Authorization": f"Bearer {api_key}"} if api_key else {})
            models = [m.get("id") for m in (r.json().get("data") or [])] if r.status_code == 200 else []
        elif p.kind == "google":
            r = get(f"{base}/models?key={api_key}")
            models = [str(m.get("name", "")).replace("models/", "") for m in (r.json().get("models") or [])] if r.status_code == 200 else []
        elif p.kind == "ollama":
            r = get(f"{base}/api/tags")
            models = [m.get("name") for m in (r.json().get("models") or [])] if r.status_code == 200 else []
        else:
            return {"ok": False, "status": "error", "message": f"نوع ناشناخته {p.kind}", "tested_at": utcnow()}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "status": "error", "message": f"اتصال برقرار نشد: {e.__class__.__name__}", "tested_at": utcnow()}
    if r.status_code in (401, 403):
        return {"ok": False, "status": "not_authorized", "message": f"کلید نامعتبر یا بدون دسترسی (HTTP {r.status_code})", "tested_at": utcnow()}
    if r.status_code != 200:
        return {"ok": False, "status": "error", "message": f"پاسخ غیرمنتظره HTTP {r.status_code}", "tested_at": utcnow()}
    return {"ok": True, "status": "ok", "message": f"اتصال برقرار است — {len(models)} مدل در دسترس", "models_found": [m for m in models if m][:50], "tested_at": utcnow()}
