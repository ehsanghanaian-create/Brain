"""Pilot remediation: Atria proposes values; only allowlisted WordPress operations can write.

The issue table is replaced by each analysis run, so proposals bind to a stable issue
fingerprint and a snapshot of the evidence instead of the transient integer row ID.
"""
from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import unquote, urljoin, urlsplit, urlunsplit

import httpx
from bs4 import BeautifulSoup, NavigableString
from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError

from ..ai.config import ProviderConfigRepository
from ..ai.gateway.gateway import BudgetExceeded, CallMeta, RouteStep
from ..ai.types import AIMessage, AITask, TaskKind
from ..db.repositories.base import utcnow
from ..wordpress.auth import resolve_auth
from .playbooks import ROADMAPS, VERSION, methods_for

PILOT_SITE = "gearboxemdad"
WP_META_FIELDS = {"wp_meta_title": "emdad_meta_title", "wp_meta_description": "emdad_meta_description", "wp_canonical": "emdad_canonical"}
WP_CONTENT_KINDS = {"wp_insert_link", "wp_remove_link", "wp_add_h1", "wp_demote_h1", "wp_image_alt", "wp_append_content"}


def _template_owns(kind: str, post_type: str | None) -> bool:
    """Ownership observed in gearboxemdad's deployed Next.js r20260830 release."""
    return ((kind in {"wp_title", "wp_canonical"} and post_type in {"car_brand", "car_model"})
            or (kind == "wp_noindex_off" and post_type == "car_model"))


class RemediationError(RuntimeError):
    def __init__(self, code: str, message: str, status: int = 409):
        super().__init__(message)
        self.code, self.status = code, status


def _json(value, default=None):
    try:
        return json.loads(value) if isinstance(value, str) else value
    except (ValueError, TypeError):
        return default


def _url(value: str) -> str:
    parsed = urlsplit(unquote(value or ""))
    if parsed.scheme not in {"https", "http"} or not parsed.hostname:
        raise RemediationError("invalid_url", "URL مشکل معتبر نیست.", 422)
    path = (parsed.path or "/").rstrip("/") or "/"
    return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), path, "", ""))


def issue_key(site_id: str, problem_type: str, url: str, related_url: str = "") -> str:
    value = "\x1f".join((site_id, problem_type, _url(url), _url(related_url) if related_url else ""))
    return hashlib.sha256(value.encode()).hexdigest()[:32]


def _hash(value: dict) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode()).hexdigest()


def _same_url(left: str, right: str) -> bool:
    try:
        return _url(left) == _url(right)
    except RemediationError:
        return False


def public_run(run: dict) -> dict:
    """The browser and generic job endpoint never receive the private WordPress snapshot."""
    return {k: run.get(k) for k in ("id", "proposal_id", "site_id", "issue_key", "method_id", "status", "job_id", "error", "created_at", "updated_at")} | {
        "verification": {k: v for k, v in (run.get("verification") or {}).items() if k in {"ok", "reason", "crawl_run_id", "analysis_run_id"}} or None
    }


class RemediationService:
    def __init__(self, engine: Engine, gateway=None):
        self.engine, self.gateway = engine, gateway

    def _site(self, site_id: str) -> dict:
        with self.engine.connect() as cx:
            row = cx.execute(text("SELECT site_id, name, canonical_url, wp_url, language, gsc_property FROM sites WHERE site_id=:s"), {"s": site_id}).mappings().first()
        if not row:
            raise RemediationError("site_not_found", "سایت پیدا نشد.", 404)
        if site_id != PILOT_SITE:
            raise RemediationError("pilot_only", "رفع خودکار فعلاً فقط برای gearboxemdad فعال است.", 403)
        return dict(row)

    def _issues(self, site_id: str) -> list[dict]:
        self._site(site_id)
        with self.engine.connect() as cx:
            rows = cx.execute(text("SELECT problem_type, severity, url, COALESCE(related_url,'') related_url, detail, run_id FROM seo_problems WHERE site_id=:s ORDER BY CASE severity WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END, problem_type, url"), {"s": site_id}).mappings().all()
        return [{**dict(row), "detail": _json(row["detail"], {}), "issue_key": issue_key(site_id, row["problem_type"], row["url"], row["related_url"])} for row in rows]

    def list_issues(self, site_id: str, limit: int = 50, offset: int = 0, problem_type: str | None = None) -> dict:
        issues = [i for i in self._issues(site_id) if not problem_type or i["problem_type"] == problem_type]
        return {"total": len(issues), "items": issues[offset:offset + limit], "playbook_version": VERSION}

    def _issue(self, site_id: str, key: str) -> dict:
        issue = next((i for i in self._issues(site_id) if i["issue_key"] == key), None)
        if not issue:
            raise RemediationError("issue_stale", "این مشکل در تحلیل فعلی پیدا نشد؛ فهرست را تازه کنید.", 409)
        return issue

    def _evidence(self, site_id: str, issue: dict) -> dict:
        url = issue["url"]
        site = self._site(site_id)
        with self.engine.connect() as cx:
            page = cx.execute(text("SELECT title, meta_description, h1, h1_count, canonical, robots_meta, x_robots_tag, indexable, indexability_reason, word_count, images, images_missing_alt, content_hash, last_crawled, final_url FROM pages WHERE site_id=:s AND url=:u"), {"s": site_id, "u": url}).mappings().first()
            post = cx.execute(text("SELECT wp_id, type, url, slug, title, content_html, excerpt, modified_gmt FROM posts WHERE site_id=:s AND url=:u"), {"s": site_id, "u": url}).mappings().first()
            outbound = cx.execute(text("SELECT target_url, anchor_text, is_nav FROM links WHERE site_id=:s AND source_url=:u AND is_internal=1 ORDER BY is_nav, target_url LIMIT 120"), {"s": site_id, "u": url}).mappings().all()
            candidates = cx.execute(text("SELECT l.source_url, l.anchor, p.wp_id, p.type, p.slug, p.title, p.content_html, p.modified_gmt FROM link_suggestions l JOIN posts p ON p.site_id=l.site_id AND p.url=l.source_url WHERE l.site_id=:s AND l.target_url=:u AND l.status IN ('new','accepted') ORDER BY l.score DESC LIMIT 5"), {"s": site_id, "u": url}).mappings().all()
            if len(candidates) < 5:
                alternatives = cx.execute(text("SELECT o.url source_url, '' anchor, p.wp_id, p.type, p.slug, p.title, p.content_html, p.modified_gmt FROM seo_opportunities o JOIN posts p ON p.site_id=o.site_id AND p.url=o.url WHERE o.site_id=:s AND o.opp_type='internal_link' AND o.related_url=:u ORDER BY o.score DESC LIMIT 5"), {"s": site_id, "u": url}).mappings().all()
                seen = {c["source_url"] for c in candidates}
                candidates = list(candidates) + [c for c in alternatives if c["source_url"] not in seen][:5 - len(candidates)]
        safe_post = dict(post) if post else None
        if safe_post:
            safe_post["content_html"] = (safe_post.get("content_html") or "")[:14000]
        try:
            live = self._rendered(site, url)
            rendered = {k: live[k] for k in ("status", "url", "title", "h1", "description", "canonical", "robots", "x_robots_tag", "images_missing_alt", "word_count")}
        except RemediationError as exc:
            rendered = {"error": exc.code}
        return {"issue": {k: issue[k] for k in ("problem_type", "url", "related_url", "detail", "severity")},
                "page": {**dict(page), "h1": _json(page["h1"], []), "images": _json(page["images"], [])} if page else None,
                "rendered": rendered,
                "post": safe_post,
                "outbound_links": [dict(link) for link in outbound],
                "link_candidates": [{**dict(c), "content_html": (c["content_html"] or "")[:7000]} for c in candidates],
                "playbook_version": VERSION}

    def _atria(self, site_id: str, evidence: dict, templates: list[dict]) -> dict[str, dict]:
        if self.gateway is None:
            raise RemediationError("atria_unavailable", "درگاه Atria آماده نیست.")
        cfg = ProviderConfigRepository(self.engine)
        routes = cfg.routes(site_id)
        route = next((r for r in routes if r["task_kind"] == "seo_remediation"), None)
        provider = cfg.get(route["provider_id"]) if route and route.get("provider_id") else None
        if not provider or provider.kind != "atria" or not provider.enabled or not cfg.api_key(provider):
            raise RemediationError("atria_not_connected", "ابتدا کلید Atria و مسیر seo_remediation را در تنظیمات مدل‌ها ثبت کنید.")
        allowed = [{"id": m["id"], "kind": m["kind"], "title": m["title"]} for m in templates]
        prompt = ("برای هر روش مجاز، مقدار پیشنهادی و دلیل کوتاه بده. فقط JSON با کلید methods برگردان. "
                  "هر عضو: id، value، reason، confidence (high|medium|low)، uncertain، uncertainty_reason، source_url، href، alt_updates. "
                  "روش جدید یا دستور اجرایی تولید نکن. ادعای تجاری بدون شاهد نساز. برای لینک، source_url فقط از link_candidates و "
                  "value عبارت دقیقِ موجود در متن همان منبع باشد. برای alt فقط از شواهد متنی استفاده کن؛ اگر تصویر نامعلوم است uncertain=true. "
                  "برای wp_image_alt فهرست alt_updates با src و alt بده؛ alt خالی فقط با decorative=true برای تصویر تزئینی. برای wp_remove_link href واقعی خروجی صفحه را بده. "
                  "برای frontend فقط شرح تغییر در value بده. اگر داده کافی نیست value را خالی و uncertain=true بگذار.\n"
                  + json.dumps({"evidence": evidence, "roadmap": ROADMAPS[evidence["issue"]["problem_type"]], "allowed_methods": allowed}, ensure_ascii=False, default=str))
        task = AITask(kind=TaskKind.SEO_REMEDIATION, site_id=site_id,
                      messages=[AIMessage("system", "شما پیشنهاددهندهٔ اصلاح SEO هستید؛ خروجی شما فقط داده است و هرگز مجوز اجرای مستقیم ندارد."), AIMessage("user", prompt)],
                      json_schema={"type": "object", "required": ["methods"], "properties": {"methods": {"type": "array"}}},
                      max_tokens=3500 if evidence["issue"]["problem_type"] == "thin_content" else 1800)
        try:
            result = self.gateway.run(task, [RouteStep(provider.name, route.get("model") or provider.default_model or "Atria-Dawn-Preview", "explicit remediation")],
                                      CallMeta(site_id=site_id, agent="seo_remediation", route_reason="explicit Atria only"))
        except BudgetExceeded as exc:
            raise RemediationError("ai_budget_exceeded", "بودجهٔ AI این سایت تمام شده است؛ تنظیم بودجه را بررسی کنید.") from exc
        if not result.ok or not result.response:
            raise RemediationError("atria_failed", "Atria نتوانست پیشنهاد معتبر تولید کند؛ دوباره تلاش کنید.", 502)
        parsed = result.response.parsed if isinstance(result.response.parsed, dict) else _json(result.response.text, {})
        items = parsed.get("methods") if isinstance(parsed, dict) else None
        return {x["id"]: x for x in items if isinstance(x, dict) and isinstance(x.get("id"), str)} if isinstance(items, list) else {}

    def propose(self, site_id: str, key: str) -> dict:
        issue = self._issue(site_id, key)
        evidence = self._evidence(site_id, issue)
        templates = methods_for(issue["problem_type"])
        if not templates:
            raise RemediationError("unsupported_problem", "برای این نوع مشکل روش تعریف نشده است.", 422)
        suggestions = self._atria(site_id, evidence, templates)
        post = evidence.get("post")
        wp_connected = bool(resolve_auth(site_id))
        candidates = evidence.get("link_candidates") or []
        access_cache: dict[tuple[str, int], tuple[str, dict]] = {}
        methods = []
        for template in templates:
            suggestion = suggestions.get(template["id"], {})
            kind = template["kind"]
            value = suggestion.get("value")
            if isinstance(value, str):
                value = value.strip()[:6000 if kind == "wp_append_content" else 1800]
            else:
                value = ""
            source_url = suggestion.get("source_url") if kind == "wp_insert_link" else issue["url"]
            if kind == "wp_insert_link" and source_url not in [c["source_url"] for c in candidates]:
                source_url = None
            confidence = suggestion.get("confidence") if suggestion.get("confidence") in {"high", "medium", "low"} else "low"
            uncertain = bool(template["uncertain"] or suggestion.get("uncertain") or confidence != "high")
            uncertainty_reason = str(suggestion.get("uncertainty_reason") or "")[:400] if uncertain else ""
            if uncertain and not uncertainty_reason:
                uncertainty_reason = "شواهد برای تصمیم قطعی کافی نیست؛ مقدار پیشنهادی را پیش از اجرا بررسی کنید."
            available = True
            block_status = "needs_connection"
            reason = str(suggestion.get("reason") or "")[:600]
            owner = "frontend" if kind == "frontend" or _template_owns(kind, (post or {}).get("type")) else "wordpress"
            if kind == "frontend":
                available, reason = False, "اتصال انتشار نسخه‌دار قالب Next.js هنوز در SEO Brain ثبت نشده است. پیشنهاد نگهداری شد. " + reason
            elif owner == "frontend":
                available, reason = False, "این خروجی در قالب Next.js ساخته می‌شود و تغییر فیلد وردپرس آن را اصلاح نمی‌کند. پیشنهاد نگهداری شد. " + reason
            elif kind.startswith("wp_") and not wp_connected:
                available, reason = False, "اتصال نوشتن وردپرس ثبت نشده است. " + reason
            elif kind == "wp_insert_link" and not source_url:
                available, reason = False, "صفحهٔ منبع مرتبط و قابل ویرایش پیدا نشد. " + reason
                block_status = "insufficient_evidence"
            elif kind.startswith("wp_") and not post and kind != "wp_insert_link":
                available, reason = False, "این URL به محتوای قابل ویرایش وردپرس نگاشت نشده است. " + reason
            elif kind == "wp_noindex_off" and "noindex" not in str((evidence.get("page") or {}).get("indexability_reason") or "").lower():
                available, reason = False, "علت عدم ایندکس noindex وردپرس تأیید نشده است. " + reason
                block_status = "insufficient_evidence"
            elif kind == "wp_image_alt":
                updates = suggestion.get("alt_updates")
                value = [{"src": str(u.get("src") or ""), "alt": str(u.get("alt") or "")[:200], "decorative": bool(u.get("decorative"))} for u in updates if isinstance(u, dict)] if isinstance(updates, list) else []
                if not value:
                    available, reason = False, "توصیف قابل اتکا برای تصاویر پیشنهاد نشده است. " + reason
                    block_status = "insufficient_evidence"
            elif kind == "wp_remove_link":
                value = str(suggestion.get("href") or "")[:500]
            if owner != "frontend" and kind != "wp_demote_h1" and kind != "wp_noindex_off" and not value:
                available, reason = False, "Atria مقدار قابل اجرا پیشنهاد نکرد. " + reason
                block_status = "insufficient_evidence"
            body = ((next((c for c in candidates if c["source_url"] == source_url), None) or {}).get("content_html")
                    if kind == "wp_insert_link" else (post or {}).get("content_html")) or ""
            soup = BeautifulSoup(body, "html.parser")
            if kind == "wp_demote_h1" and not soup.find("h1"):
                available, reason = False, "H1 اضافی در محتوای وردپرس نیست؛ احتمالاً مالک آن قالب است. " + reason
            if kind == "wp_insert_link" and value and not any(value in str(node) and node.find_parent(["p", "li"]) and not node.find_parent("a") for node in soup.find_all(string=True)):
                available, reason = False, "عبارت پیشنهادی در متن منبع پیدا نشد. " + reason
                block_status = "insufficient_evidence"
            if kind == "wp_remove_link" and value and not any(_same_url(urljoin(issue["url"], a.get("href", "")), value) for a in soup.find_all("a", href=True)):
                available, reason = False, "لینک پیشنهادی در متن وردپرس پیدا نشد؛ احتمالاً در قالب است. " + reason
            if kind == "wp_image_alt" and value and not all(soup.find("img", src=item["src"]) for item in value):
                available, reason = False, "برخی تصاویر پیشنهادی در محتوای وردپرس نیستند؛ احتمالاً قالب مالک آن‌هاست. " + reason
            if evidence["rendered"].get("error"):
                uncertain = True
                reason = "صفحهٔ زنده هنگام پیشنهاد در دسترس نبود؛ پیش از اجرا دوباره بررسی می‌شود. " + reason
            access = {"status": "not_checked", "reason": "این روش به پیش‌بررسی وردپرس نیاز ندارد."}
            if owner == "wordpress" and kind.startswith("wp_"):
                target_post = post if source_url == issue["url"] else next(
                    (c for c in candidates if c["source_url"] == source_url), None)
                if not wp_connected:
                    access = {"status": "needs_connection", "reason": "رمز برنامهٔ وردپرس برای این سایت ثبت نشده است."}
                elif target_post and available:
                    access = self._probe_wp_access(site_id, kind, target_post, access_cache)
                    if access["status"] != "ready":
                        available, block_status = False, "needs_connection"
                        reason = access["reason"] + " " + reason
                elif not target_post:
                    access = {"status": "needs_connection", "reason": "این URL به رکورد وردپرس نگاشت نشده است."}
            affected = [] if owner == "frontend" else ([source_url, issue["url"]] if source_url and source_url != issue["url"] else [issue["url"]])
            methods.append({**template, "value": value, "source_url": source_url, "affected_urls": affected,
                            "owner": owner, "impact_unknown": owner == "frontend",
                            "confidence": confidence, "uncertain": uncertain, "uncertainty_reason": uncertainty_reason, "reason": reason, "available": available,
                            "status": "ready" if available else block_status, "rollback": owner != "frontend", "access": access})
        pid = "proposal-" + uuid.uuid4().hex[:20]
        now = datetime.now(timezone.utc)
        proposal = {"id": pid, "site_id": site_id, "issue_key": key, "problem_type": issue["problem_type"], "url": issue["url"],
                    "related_url": issue["related_url"], "evidence_hash": _hash(evidence), "evidence": evidence, "methods": methods,
                    "status": "ready", "created_at": now.isoformat(), "expires_at": (now + timedelta(minutes=30)).isoformat()}
        with self.engine.begin() as cx:
            cx.execute(text("INSERT INTO seo_remediation_proposals(id,site_id,issue_key,problem_type,url,related_url,evidence_hash,evidence,methods,status,created_at,expires_at) VALUES (:id,:site_id,:issue_key,:problem_type,:url,:related_url,:evidence_hash,:evidence,:methods,:status,:created_at,:expires_at)"),
                       {**proposal, "evidence": json.dumps(evidence, ensure_ascii=False, default=str), "methods": json.dumps(methods, ensure_ascii=False)})
        return {**{k: v for k, v in proposal.items() if k != "evidence"}, "roadmap": ROADMAPS[issue["problem_type"]]}

    def proposal(self, site_id: str, pid: str) -> dict:
        self._site(site_id)
        with self.engine.connect() as cx:
            row = cx.execute(text("SELECT * FROM seo_remediation_proposals WHERE site_id=:s AND id=:p"), {"s": site_id, "p": pid}).mappings().first()
        if not row:
            raise RemediationError("proposal_not_found", "پیشنهاد پیدا نشد.", 404)
        return {**dict(row), "evidence": _json(row["evidence"], {}), "methods": _json(row["methods"], [])}

    def create_run(self, site_id: str, pid: str, method_id: str, evidence_hash: str, idempotency_key: str, confirmed: bool = False) -> dict:
        proposal = self.proposal(site_id, pid)
        method = next((m for m in proposal["methods"] if m["id"] == method_id), None)
        if not method:
            raise RemediationError("method_not_found", "روش انتخابی معتبر نیست.", 422)
        if method["status"] == "insufficient_evidence":
            raise RemediationError("insufficient_evidence", "برای اجرای این روش شواهد کافی وجود ندارد؛ پیشنهاد تازه بگیرید.")
        if not idempotency_key or len(idempotency_key) > 100:
            raise RemediationError("invalid_idempotency_key", "کلید اجرای تکراری معتبر نیست.", 422)
        with self.engine.connect() as cx:
            old = cx.execute(text("SELECT * FROM seo_remediation_runs WHERE site_id=:s AND idempotency_key=:k"), {"s": site_id, "k": idempotency_key}).mappings().first()
        if old:
            if old["proposal_id"] != pid or old["method_id"] != method_id:
                raise RemediationError("idempotency_conflict", "این کلید قبلاً برای روش دیگری استفاده شده است.")
            return {**dict(old), "_created": False}
        if datetime.fromisoformat(proposal["expires_at"]) < datetime.now(timezone.utc):
            raise RemediationError("proposal_expired", "پیشنهاد منقضی شده؛ دوباره روش‌ها را دریافت کنید.")
        if evidence_hash != proposal["evidence_hash"]:
            raise RemediationError("evidence_mismatch", "نسخهٔ داده با پیشنهاد مطابقت ندارد.")
        issue = self._issue(site_id, proposal["issue_key"])
        if _hash(self._evidence(site_id, issue)) != evidence_hash:
            raise RemediationError("issue_changed", "دادهٔ صفحه تغییر کرده؛ روش‌ها را دوباره بررسی کنید.")
        if method["uncertain"] and not confirmed:
            raise RemediationError("second_confirmation_required", "این روش نامطمئن است و پیش از اجرا تأیید دوم لازم دارد.")
        status = "queued" if method["available"] else "needs_connection"
        connection_error = method.get("reason") if status == "needs_connection" else None
        if status == "queued" and method["kind"].startswith("wp_") and not resolve_auth(site_id):
            status = "needs_connection"
            connection_error = "رمز برنامهٔ وردپرس برای این سایت ثبت نشده است."
        if status == "queued" and method["owner"] == "wordpress":
            target = method.get("source_url") or proposal["url"]
            post = proposal["evidence"].get("post") if target == proposal["url"] else next(
                (c for c in proposal["evidence"].get("link_candidates", []) if c["source_url"] == target), None)
            access = self._probe_wp_access(site_id, method["kind"], post, {}) if post else {
                "status": "needs_connection", "reason": "این URL به محتوای وردپرس نگاشت نشده است."}
            if access["status"] != "ready":
                status = "needs_connection"
                connection_error = access["reason"]
        rid = "rem-" + uuid.uuid4().hex[:20]
        now = utcnow()
        values = {"id": rid, "proposal_id": pid, "site_id": site_id, "issue_key": proposal["issue_key"], "method_id": method_id,
                  "idempotency_key": idempotency_key, "status": status, "error": connection_error, "created_at": now, "updated_at": now}
        try:
            with self.engine.begin() as cx:
                inserted = cx.execute(text("INSERT INTO seo_remediation_runs(id,proposal_id,site_id,issue_key,method_id,idempotency_key,status,error,created_at,updated_at) VALUES (:id,:proposal_id,:site_id,:issue_key,:method_id,:idempotency_key,:status,:error,:created_at,:updated_at) ON CONFLICT(site_id,idempotency_key) DO NOTHING"), values)
                if not inserted.rowcount:
                    old = cx.execute(text("SELECT * FROM seo_remediation_runs WHERE site_id=:s AND idempotency_key=:k"), {"s": site_id, "k": idempotency_key}).mappings().first()
                    if old and (old["proposal_id"] != pid or old["method_id"] != method_id):
                        raise RemediationError("idempotency_conflict", "این کلید قبلاً برای روش دیگری استفاده شده است.")
                    return {**dict(old), "_created": False} if old else values
        except IntegrityError as exc:
            raise RemediationError("site_busy", "یک اصلاح دیگر برای این سایت در حال اجراست؛ پس از پایان آن دوباره تلاش کنید.") from exc
        return {**values, "_created": True}

    def get_run(self, site_id: str, run_id: str) -> dict:
        self._site(site_id)
        with self.engine.connect() as cx:
            row = cx.execute(text("SELECT * FROM seo_remediation_runs WHERE site_id=:s AND id=:r"), {"s": site_id, "r": run_id}).mappings().first()
        if not row:
            raise RemediationError("run_not_found", "اجرای اصلاح پیدا نشد.", 404)
        return {**dict(row), "before_snapshot": _json(row["before_snapshot"]), "after_snapshot": _json(row["after_snapshot"]), "verification": _json(row["verification"])}

    def run_history(self, site_id: str, key: str, limit: int = 5) -> list[dict]:
        self._site(site_id)
        with self.engine.connect() as cx:
            rows = cx.execute(text("SELECT * FROM seo_remediation_runs WHERE site_id=:s AND issue_key=:k ORDER BY created_at DESC LIMIT :n"),
                              {"s": site_id, "k": key, "n": limit}).mappings().all()
        return [public_run({**dict(row), "verification": _json(row["verification"])}) for row in rows]

    def resume_run(self, site_id: str, run_id: str) -> dict:
        run = self.get_run(site_id, run_id)
        if run["status"] != "needs_connection":
            raise RemediationError("resume_unavailable", "این اجرا در وضعیت نیازمند اتصال نیست.")
        proposal = self.proposal(site_id, run["proposal_id"])
        if datetime.fromisoformat(proposal["expires_at"]) < datetime.now(timezone.utc):
            raise RemediationError("proposal_expired", "پیشنهاد منقضی شده؛ روش‌ها را دوباره بررسی کنید.")
        method = next(m for m in proposal["methods"] if m["id"] == run["method_id"])
        if method["owner"] == "frontend":
            raise RemediationError("frontend_connector_required", "اتصال انتشار قالب هنوز آماده نیست.")
        if not resolve_auth(site_id):
            raise RemediationError("wordpress_auth_required", "اتصال نوشتن وردپرس را ثبت کنید.")
        target = method.get("source_url") or proposal["url"]
        evidence = proposal["evidence"]
        owned = evidence.get("post") if target == proposal["url"] else next((c for c in evidence.get("link_candidates", []) if c["source_url"] == target), None)
        if not owned:
            raise RemediationError("wordpress_owner_missing", "این URL به محتوای قابل ویرایش وردپرس نگاشت نشده؛ پیشنهاد تازه بگیرید.")
        access = self._probe_wp_access(site_id, method["kind"], owned, {})
        if access["status"] != "ready":
            raise RemediationError("wordpress_access_required", access["reason"])
        issue = self._issue(site_id, run["issue_key"])
        if _hash(self._evidence(site_id, issue)) != proposal["evidence_hash"]:
            raise RemediationError("issue_changed", "دادهٔ مشکل تغییر کرده؛ روش‌ها را دوباره بررسی کنید.")
        try:
            with self.engine.begin() as cx:
                changed = cx.execute(text("UPDATE seo_remediation_runs SET status='queued', error=NULL, updated_at=:t WHERE id=:r AND site_id=:s AND status='needs_connection'"),
                                     {"t": utcnow(), "r": run_id, "s": site_id})
                if not changed.rowcount:
                    raise RemediationError("resume_unavailable", "این اجرا قبلاً ادامه داده شده است.")
        except IntegrityError as exc:
            raise RemediationError("site_busy", "یک اصلاح دیگر برای این سایت در حال اجراست.") from exc
        return self.get_run(site_id, run_id)

    def update_run(self, run_id: str, **fields) -> None:
        allowed = {k: v for k, v in fields.items() if k in {"status", "job_id", "before_snapshot", "after_snapshot", "verification", "error"}}
        audit = [(key, allowed[key]) for key in ("before_snapshot", "after_snapshot", "verification") if key in allowed]
        if allowed.get("status") == "rolled_back":
            audit.append(("rollback", {"status": "rolled_back", "error": allowed.get("error")}))
        for key in ("before_snapshot", "after_snapshot", "verification"):
            if key in allowed:
                allowed[key] = json.dumps(allowed[key], ensure_ascii=False, default=str)
        if not allowed:
            return
        allowed["updated_at"] = utcnow()
        with self.engine.begin() as cx:
            cx.execute(text("UPDATE seo_remediation_runs SET " + ", ".join(f"{k}=:{k}" for k in allowed) + " WHERE id=:id"), {**allowed, "id": run_id})
            for event_type, payload in audit:
                cx.execute(text("INSERT INTO seo_remediation_events(run_id,event_type,payload,created_at) VALUES (:r,:t,:p,:c)"),
                           {"r": run_id, "t": event_type, "p": json.dumps(payload, ensure_ascii=False, default=str), "c": allowed["updated_at"]})

    def _wp_client(self, site_id: str, wp_url: str) -> httpx.Client:
        auth = resolve_auth(site_id)
        if not auth:
            raise RemediationError("wordpress_auth_required", "ابتدا اتصال نوشتن وردپرس را ثبت کنید.")
        return httpx.Client(auth=auth.basic, timeout=30, follow_redirects=False,
                            headers={"Accept": "application/json", "User-Agent": "SEO-Brain/0.2 remediation"})

    @staticmethod
    def _wp_request(client: httpx.Client, method: str, url: str, payload: dict | None = None) -> dict:
        try:
            response = client.request(method, url, json=payload)
        except httpx.HTTPError as exc:
            raise RemediationError("wordpress_unreachable", f"ارتباط وردپرس برقرار نشد: {exc.__class__.__name__}", 502) from exc
        if response.status_code == 401:
            raise RemediationError("wordpress_auth_invalid", "احراز هویت وردپرس رد شد؛ نام کاربری و رمز برنامهٔ این سایت را بررسی کنید.")
        if response.status_code == 403:
            raise RemediationError("wordpress_permission_denied", "وردپرس دسترسی به این محتوا یا فیلد را رد کرد؛ مجوز نقش کاربر و تنظیمات REST را بررسی کنید.")
        if response.status_code == 404:
            raise RemediationError("wordpress_resource_unavailable", "این نوع محتوا یا شناسه در REST وردپرس در دسترس نیست.")
        if response.status_code >= 400:
            raise RemediationError("wordpress_error", f"وردپرس درخواست را نپذیرفت (HTTP {response.status_code}).", 502)
        try:
            result = response.json()
        except ValueError as exc:
            raise RemediationError("wordpress_invalid_response", "پاسخ وردپرس JSON معتبر نیست.", 502) from exc
        if not isinstance(result, dict):
            raise RemediationError("wordpress_invalid_response", "پاسخ وردپرس ساختار معتبر ندارد.", 502)
        return result

    def _wp_resource(self, client: httpx.Client, site: dict, post: dict) -> tuple[str, dict]:
        typ = post["type"]
        if not re.fullmatch(r"[a-zA-Z0-9_-]+", typ):
            raise RemediationError("wordpress_type_invalid", "نوع محتوای وردپرس معتبر نیست.")
        root = site["wp_url"].rstrip("/") + "/wp-json/wp/v2"
        type_info = self._wp_request(client, "GET", f"{root}/types/{typ}")
        rest_base = type_info.get("rest_base")
        if not isinstance(rest_base, str) or not re.fullmatch(r"[a-zA-Z0-9_-]+", rest_base):
            raise RemediationError("wordpress_type_unavailable", "مسیر REST این نوع محتوا قابل استفاده نیست.")
        endpoint = f"{root}/{rest_base}/{int(post['wp_id'])}"
        remote = self._wp_request(client, "GET", endpoint + "?context=edit")
        if remote.get("id") != int(post["wp_id"]) or remote.get("type") != typ or (post.get("slug") and remote.get("slug") != post["slug"]):
            raise RemediationError("wordpress_identity_mismatch", "شناسهٔ محتوای وردپرس تغییر کرده است.")
        return endpoint, remote

    @staticmethod
    def _check_wp_field(kind: str, remote: dict) -> None:
        if kind in WP_META_FIELDS or kind == "wp_noindex_off":
            field = WP_META_FIELDS.get(kind, "emdad_noindex")
            if field not in (remote.get("meta") or {}):
                raise RemediationError("wordpress_meta_unavailable", f"فیلد {field} در REST این نوع محتوا دیده نمی‌شود؛ ثبت و مجوز ویرایش آن را بررسی کنید.")
        elif kind == "wp_title" and (not isinstance(remote.get("title"), dict) or "raw" not in remote["title"]):
            raise RemediationError("wordpress_title_unavailable", "فیلد عنوان در نمای ویرایش REST این محتوا دیده نمی‌شود.")
        elif kind in WP_CONTENT_KINDS and (not isinstance(remote.get("content"), dict) or "raw" not in remote["content"]):
            raise RemediationError("wordpress_content_unavailable", "فیلد بدنه در نمای ویرایش REST این محتوا دیده نمی‌شود.")

    def _probe_wp_access(self, site_id: str, kind: str, post: dict,
                         cache: dict[tuple[str, int], tuple[str, dict]]) -> dict:
        """Read-only, per-resource capability check; the write is checked again at execution."""
        try:
            site = self._site(site_id)
            if not site.get("wp_url"):
                raise RemediationError("wordpress_url_missing", "آدرس وردپرس برای این سایت ثبت نشده است.")
            cache_key = (str(post["type"]), int(post["wp_id"]))
            if cache_key not in cache:
                with self._wp_client(site_id, site["wp_url"]) as client:
                    cache[cache_key] = self._wp_resource(client, site, post)
            self._check_wp_field(kind, cache[cache_key][1])
        except (RemediationError, ValueError, KeyError, TypeError) as exc:
            reason = str(exc) if isinstance(exc, RemediationError) else "شناسهٔ محتوای وردپرس معتبر نیست."
            return {"status": "needs_connection", "reason": reason}
        return {"status": "ready", "reason": "نمای ویرایش همین محتوا و فیلد لازم در REST وردپرس تأیید شد؛ مجوز نوشتن هنگام اجرا دوباره بررسی می‌شود."}

    @staticmethod
    def _edit_body(content: str, method: dict, target_url: str) -> str:
        soup = BeautifulSoup(content, "html.parser")
        kind, value = method["kind"], method["value"]
        if kind == "wp_demote_h1":
            headings = soup.find_all("h1")
            if not headings:
                raise RemediationError("no_editable_h1", "H1 اضافی در بدنهٔ وردپرس پیدا نشد.")
            for heading in headings:
                heading.name = "h2"
        elif kind == "wp_add_h1":
            if soup.find("h1"):
                raise RemediationError("h1_already_present", "بدنهٔ وردپرس H1 دارد.")
            tag = soup.new_tag("h1"); tag.string = value
            soup.insert(0, tag)
        elif kind == "wp_append_content":
            tag = soup.new_tag("p"); tag.string = value
            soup.append(tag)
        elif kind == "wp_insert_link":
            phrase = str(value)
            inserted = False
            for node in list(soup.find_all(string=True)):
                if inserted or not isinstance(node, NavigableString) or not node.find_parent(["p", "li"]) or node.find_parent("a"):
                    continue
                raw = str(node)
                if phrase and phrase in raw:
                    before, after = raw.split(phrase, 1)
                    link = soup.new_tag("a", href=target_url); link.string = phrase
                    node.replace_with(NavigableString(before), link, NavigableString(after))
                    inserted = True
            if not inserted:
                raise RemediationError("anchor_not_found", "عبارت پیشنهادی در متن زندهٔ منبع پیدا نشد.")
        elif kind == "wp_remove_link":
            links = [a for a in soup.find_all("a", href=True) if _same_url(urljoin(target_url, a["href"]), value)]
            if len(links) != 1:
                raise RemediationError("link_not_unique", "لینک انتخابی در متن زنده یکتا نیست.")
            links[0].unwrap()
        elif kind == "wp_image_alt":
            updates = value if isinstance(value, list) else []
            for update in updates:
                matches = [img for img in soup.find_all("img", src=True) if img["src"] == update["src"] and not img.get("alt")]
                if len(matches) != 1 or (not update["alt"] and not update.get("decorative")):
                    raise RemediationError("image_not_unique", "تصویر پیشنهادی در متن زنده یکتا نیست یا توضیح ندارد.")
                matches[0]["alt"] = update["alt"]
            if not updates:
                raise RemediationError("image_updates_empty", "برای تصویر توضیحی آماده نشده است.")
        return str(soup)

    def _rendered(self, site: dict, url: str) -> dict:
        host = urlsplit(_url(site["canonical_url"])).hostname
        if urlsplit(_url(url)).hostname != host:
            raise RemediationError("outside_site", "URL خارج از سایت آزمایشی است.")
        try:
            current = url
            with httpx.Client(timeout=25, follow_redirects=False, headers={"User-Agent": "SEO-Brain/0.2 remediation-verifier"}) as client:
                for _ in range(6):
                    response = client.get(current)
                    if response.status_code not in {301, 302, 303, 307, 308}:
                        break
                    location = response.headers.get("location")
                    if not location:
                        break
                    current = urljoin(current, location)
                    if urlsplit(_url(current)).hostname != host:
                        raise RemediationError("verification_redirect_outside", "صفحه به خارج از سایت هدایت شده است.")
                else:
                    raise RemediationError("verification_redirect_loop", "زنجیرهٔ هدایت صفحه طولانی است.")
        except httpx.HTTPError as exc:
            raise RemediationError("verification_unreachable", "صفحه برای راستی‌آزمایی در دسترس نیست.", 502) from exc
        if response.url.host != host:
            raise RemediationError("verification_redirect_outside", "صفحه به خارج از سایت هدایت شده است.")
        soup = BeautifulSoup(response.text, "html.parser")
        canonical = soup.find("link", rel=lambda value: value and "canonical" in value)
        meta = soup.find("meta", attrs={"name": "description"})
        robots = soup.find("meta", attrs={"name": "robots"})
        return {"status": response.status_code, "url": str(response.url), "title": soup.title.get_text(" ", strip=True) if soup.title else "",
                "h1": [h.get_text(" ", strip=True) for h in soup.find_all("h1")], "description": meta.get("content", "") if meta else "",
                "canonical": canonical.get("href", "") if canonical else "", "robots": robots.get("content", "") if robots else "",
                "x_robots_tag": response.headers.get("x-robots-tag", ""),
                "links": [a.get("href") for a in soup.find_all("a", href=True)],
                "images": [{"src": img.get("src", ""), "alt": img.get("alt")} for img in soup.find_all("img")],
                "images_missing_alt": len([img for img in soup.find_all("img") if not img.has_attr("alt")]),
                "word_count": len(soup.get_text(" ", strip=True).split())}

    @staticmethod
    def _verify(kind: str, method: dict, before: dict, after: dict, target_url: str) -> dict:
        value = method["value"]
        if after["status"] != 200:
            return {"ok": False, "reason": "صفحه پاسخ ۲۰۰ نمی‌دهد."}
        if kind in {"wp_meta_title"}:
            ok = value == after["title"] and after["title"] != before.get("title")
        elif kind == "wp_meta_description":
            ok = value == after["description"]
        elif kind == "wp_canonical":
            ok = _url(value) == _url(after["canonical"])
        elif kind == "wp_noindex_off":
            ok = "noindex" not in (after["robots"] + " " + after["x_robots_tag"]).lower()
        elif kind in {"wp_title", "wp_add_h1", "wp_demote_h1"}:
            ok = len(after["h1"]) == 1 and (kind == "wp_demote_h1" or after["h1"][0] == value)
        elif kind == "wp_image_alt":
            ok = after["images_missing_alt"] == 0 and before.get("images_missing_alt", 0) > 0 and all(
                any(image["src"] == item["src"] and image["alt"] == item["alt"] for image in after["images"]) for item in value)
        elif kind == "wp_append_content":
            ok = after["word_count"] >= 300 and after["word_count"] > before.get("word_count", 0)
        elif kind == "wp_insert_link":
            ok = any(_url(h) == _url(target_url) for h in after["links"] if h and h.startswith("http"))
        elif kind == "wp_remove_link":
            ok = len(after["links"]) < len(before.get("links", [])) and value not in after["links"]
        else:
            ok = False
        return {"ok": bool(ok), "reason": "خروجی رندرشده تأیید شد." if ok else "تغییر هنوز در خروجی رندرشده تأیید نشد؛ ممکن است کش سایت تازه نشده باشد."}

    @staticmethod
    def _preflight(kind: str, rendered: dict) -> None:
        if rendered["status"] != 200:
            raise RemediationError("page_not_200", "صفحهٔ هدف پاسخ ۲۰۰ نمی‌دهد.")
        if kind == "wp_add_h1" and rendered["h1"]:
            raise RemediationError("issue_already_resolved", "صفحه اکنون H1 دارد.")
        if kind == "wp_demote_h1" and len(rendered["h1"]) < 2:
            raise RemediationError("issue_already_resolved", "صفحه اکنون چند H1 ندارد.")
        if kind == "wp_meta_description" and rendered["description"]:
            raise RemediationError("issue_already_resolved", "توضیح متای صفحه اکنون وجود دارد.")
        if kind == "wp_canonical" and rendered["canonical"]:
            raise RemediationError("issue_already_resolved", "canonical صفحه اکنون وجود دارد.")
        if kind == "wp_noindex_off" and "noindex" not in (rendered["robots"] + " " + rendered["x_robots_tag"]).lower():
            raise RemediationError("noindex_not_rendered", "مانع noindex در HTML فعلی دیده نشد.")
        if kind == "wp_image_alt" and rendered["images_missing_alt"] == 0:
            raise RemediationError("issue_already_resolved", "تصویر بدون alt در صفحهٔ فعلی دیده نشد.")

    def execute(self, site_id: str, run_id: str) -> dict:
        run = self.get_run(site_id, run_id)
        if run["status"] in {"verified", "needs_review", "rolled_back", "needs_connection", "stale", "failed"}:
            return run
        try:
            proposal = self.proposal(site_id, run["proposal_id"])
            method = next(m for m in proposal["methods"] if m["id"] == run["method_id"])
            issue = self._issue(site_id, run["issue_key"])
            if _hash(self._evidence(site_id, issue)) != proposal["evidence_hash"]:
                raise RemediationError("issue_changed", "دادهٔ مشکل پس از پیشنهاد تغییر کرده است.")
            site = self._site(site_id)
        except (RemediationError, StopIteration) as exc:
            self.update_run(run_id, status="stale", error=str(exc))
            return self.get_run(site_id, run_id)
        except Exception as exc:
            self.update_run(run_id, status="failed", error=f"preflight_failed: {exc.__class__.__name__}")
            return self.get_run(site_id, run_id)
        if not site.get("wp_url") or method["owner"] == "frontend":
            self.update_run(run_id, status="needs_connection", error="اتصال انتشار قالب یا وردپرس آماده نیست.")
            return self.get_run(site_id, run_id)
        target = method.get("source_url") or issue["url"]
        post = proposal["evidence"].get("post") if target == issue["url"] else next((c for c in proposal["evidence"].get("link_candidates", []) if c["source_url"] == target), None)
        if not post:
            self.update_run(run_id, status="needs_connection", error="محتوای قابل ویرایش پیدا نشد.")
            return self.get_run(site_id, run_id)
        self.update_run(run_id, status="running")
        try:
            before_rendered = self._rendered(site, target)
            if not run["before_snapshot"]:
                self._preflight(method["kind"], before_rendered)
            with self._wp_client(site_id, site["wp_url"]) as client:
                endpoint, remote = self._wp_resource(client, site, post)
                self._check_wp_field(method["kind"], remote)
                if run["after_snapshot"]:
                    if remote.get("modified_gmt") != run["after_snapshot"].get("modified_gmt"):
                        raise RemediationError("write_state_unknown", "محتوا پس از اجرا تغییر کرده و اجرای مجدد متوقف شد.")
                elif run["before_snapshot"] and remote.get("modified_gmt") != run["before_snapshot"]["wordpress"].get("modified_gmt"):
                    raise RemediationError("write_state_unknown", "وضعیت نوشتن قبلی مشخص نیست؛ اجرای مجدد متوقف شد.")
                elif post.get("modified_gmt") and remote.get("modified_gmt") != post["modified_gmt"]:
                    raise RemediationError("wordpress_stale", "محتوا در وردپرس پس از همگام‌سازی تغییر کرده است.")
                snapshot = {"endpoint": endpoint, "modified_gmt": remote.get("modified_gmt"), "title": remote.get("title", {}).get("raw"),
                            "content": remote.get("content", {}).get("raw"), "meta": remote.get("meta") or {}}
                if not run["before_snapshot"]:
                    self.update_run(run_id, before_snapshot={"wordpress": snapshot, "rendered": before_rendered})
                kind, value = method["kind"], method["value"]
                if kind in WP_META_FIELDS:
                    if not isinstance(value, str) or not value or len(value) > 500:
                        raise RemediationError("invalid_value", "مقدار پیشنهادی معتبر نیست.")
                    if WP_META_FIELDS[kind] not in snapshot["meta"]:
                        raise RemediationError("wordpress_meta_unavailable", "فیلد SEO این نوع محتوا در REST وردپرس قابل ویرایش نیست.")
                    if kind == "wp_canonical" and (urlsplit(_url(value)).hostname != urlsplit(site["canonical_url"]).hostname or urlsplit(value).scheme != urlsplit(site["canonical_url"]).scheme):
                        raise RemediationError("outside_site", "canonical باید در دامنه و پروتکل اصلی همین سایت باشد.")
                    payload = {"meta": {WP_META_FIELDS[kind]: value}}
                elif kind == "wp_noindex_off":
                    if "emdad_noindex" not in snapshot["meta"]:
                        raise RemediationError("wordpress_meta_unavailable", "فیلد noindex در REST وردپرس قابل ویرایش نیست.")
                    if not snapshot["meta"].get("emdad_noindex"):
                        raise RemediationError("noindex_not_owned", "noindex در فیلد وردپرس این صفحه فعال نیست.")
                    payload = {"meta": {"emdad_noindex": False}}
                elif kind == "wp_title":
                    if not isinstance(value, str) or not 5 <= len(value) <= 160:
                        raise RemediationError("invalid_title", "عنوان پیشنهادی معتبر نیست.")
                    payload = {"title": value}
                elif kind in WP_CONTENT_KINDS:
                    if kind in {"wp_append_content", "wp_add_h1"} and (not isinstance(value, str) or not 10 <= len(value) <= (6000 if kind == "wp_append_content" else 1800)):
                        raise RemediationError("invalid_content", "متن پیشنهادی معتبر نیست.")
                    payload = {"content": self._edit_body(snapshot["content"] or "", method, issue["url"])}
                else:
                    raise RemediationError("method_not_supported", "اجرای این روش هنوز اتصال ندارد.")
                # Recovery after a process restart: if the write already landed, do not send it twice.
                if run["after_snapshot"]:
                    after_remote = remote
                else:
                    after_remote = self._wp_request(client, "POST", endpoint, payload)
                self.update_run(run_id, after_snapshot={"modified_gmt": after_remote.get("modified_gmt"), "payload": payload})
            self.verify_run(site_id, run_id)
        except RemediationError as exc:
            wrote = bool(self.get_run(site_id, run_id)["after_snapshot"])
            access_errors = {"wordpress_auth_required", "wordpress_auth_invalid", "wordpress_permission_denied",
                             "wordpress_resource_unavailable", "wordpress_type_unavailable", "wordpress_meta_unavailable",
                             "wordpress_title_unavailable", "wordpress_content_unavailable", "wordpress_unreachable"}
            status = "needs_review" if wrote else "needs_connection" if exc.code in access_errors else "failed"
            self.update_run(run_id, status=status, error=f"{exc.code}: {exc}")
        except Exception as exc:  # avoid leaking credentials or response bodies into job logs
            wrote = bool(self.get_run(site_id, run_id)["after_snapshot"])
            self.update_run(run_id, status="needs_review" if wrote else "failed", error=f"unexpected: {exc.__class__.__name__}")
        return self.get_run(site_id, run_id)

    def verify_run(self, site_id: str, run_id: str) -> dict:
        run = self.get_run(site_id, run_id)
        if not run["after_snapshot"] or not run["before_snapshot"] or run["status"] in {"rolled_back", "needs_connection"}:
            raise RemediationError("verification_unavailable", "این اجرا هنوز قابل راستی‌آزمایی نیست.")
        proposal = self.proposal(site_id, run["proposal_id"])
        method = next(m for m in proposal["methods"] if m["id"] == run["method_id"])
        site = self._site(site_id)
        target = method.get("source_url") or proposal["url"]
        rendered = self._rendered(site, target)
        baseline = run["before_snapshot"]["rendered"]
        verdict = self._verify(method["kind"], method, baseline, rendered, proposal["url"])
        if verdict["ok"] and proposal["problem_type"] in {"duplicate_title", "duplicate_h1"}:
            peers = (proposal["evidence"].get("issue", {}).get("detail") or {}).get("shared_with") or []
            field = "title" if proposal["problem_type"] == "duplicate_title" else "h1"
            own = rendered[field] if field == "title" else (rendered["h1"] or [""])[0]
            for peer in peers[:20]:
                other = self._rendered(site, peer)
                other_value = other[field] if field == "title" else (other["h1"] or [""])[0]
                if own == other_value:
                    verdict = {"ok": False, "reason": "عنوان هنوز با صفحهٔ مرتبط تکراری است."}
                    break
        if verdict["ok"] and method["kind"] == "wp_canonical":
            destination = self._rendered(site, method["value"])
            if destination["status"] != 200:
                verdict = {"ok": False, "reason": "مقصد canonical پاسخ ۲۰۰ نمی‌دهد."}
        if verdict["ok"]:
            try:
                refresh = self._refresh_analysis(site, method.get("affected_urls") or [proposal["url"]])
                verdict.update({"crawl_run_id": refresh["crawl"]["run_id"], "analysis_run_id": refresh["analysis"]["run_id"]})
                with self.engine.connect() as cx:
                    remains = cx.execute(text("SELECT 1 FROM seo_problems WHERE site_id=:s AND problem_type=:t AND url=:u AND COALESCE(related_url,'')=:r LIMIT 1"),
                                         {"s": site_id, "t": proposal["problem_type"], "u": proposal["url"], "r": proposal["related_url"]}).first()
                if remains:
                    verdict = {**verdict, "ok": False, "reason": "خزش و تحلیل تازه انجام شد، اما مشکل هنوز در فهرست تحلیل وجود دارد."}
            except Exception as exc:
                verdict = {**verdict, "ok": False, "reason": "خزش دوباره کامل نشد؛ تغییر اعمال شده و نیازمند بررسی است."}
                self.update_run(run_id, error=f"recrawl_failed: {exc.__class__.__name__}")
        self.update_run(run_id, status="verified" if verdict["ok"] else "needs_review",
                        verification={"before": baseline, "after": rendered, **verdict})
        return self.get_run(site_id, run_id)

    def _refresh_analysis(self, site: dict, affected_urls: list[str]) -> dict:
        """Refresh only affected pages, then recompute detector findings from the cached site graph."""
        from ..analysis.seo import run_analysis
        from ..common.config import SiteConfig
        from ..crawler.crawler import Crawler
        from ..database.db import connect

        if self.engine.dialect.name != "sqlite" or not self.engine.url.database:
            raise RemediationError("recrawl_backend_unavailable", "خزش هدفمند برای این پایگاه داده آماده نیست.")
        urls = list(dict.fromkeys(u for u in affected_urls if u))
        config = SiteConfig(site_id=site["site_id"], name=site["name"], canonical_url=site["canonical_url"],
                            wp_url=site["wp_url"] or "", language=site["language"] or "fa", gsc_property=site["gsc_property"] or "")
        conn = connect(self.engine.url.database)
        try:
            crawl = Crawler(config, max_urls=len(urls)).run(conn, seeds=urls)
            analysis = run_analysis(conn, config)
            return {"crawl": crawl, "analysis": analysis}
        finally:
            conn.close()

    def rollback(self, site_id: str, run_id: str) -> dict:
        run = self.get_run(site_id, run_id)
        if run["status"] not in {"verified", "needs_review"} or not run["before_snapshot"] or not run["after_snapshot"]:
            raise RemediationError("rollback_unavailable", "این اجرا هنوز قابل بازگردانی نیست.")
        snapshot = run["before_snapshot"]["wordpress"]
        endpoint = snapshot["endpoint"]
        site = self._site(site_id)
        if not endpoint.startswith(site["wp_url"].rstrip("/") + "/wp-json/wp/v2/"):
            raise RemediationError("rollback_target_invalid", "هدف بازگردانی معتبر نیست.")
        with self._wp_client(site_id, site["wp_url"]) as client:
            current = self._wp_request(client, "GET", endpoint + "?context=edit")
            applied = run["after_snapshot"].get("payload") or {}
            if "meta" in applied:
                matches_applied = all((current.get("meta") or {}).get(k) == v for k, v in applied["meta"].items())
            elif "title" in applied:
                matches_applied = current.get("title", {}).get("raw") == applied["title"]
            else:
                matches_applied = current.get("content", {}).get("raw") == applied.get("content")
            if not run["after_snapshot"].get("modified_gmt") or current.get("modified_gmt") != run["after_snapshot"].get("modified_gmt") or not matches_applied:
                raise RemediationError("rollback_conflict", "محتوا بعد از اصلاح دوباره تغییر کرده؛ بازگردانی خودکار مجاز نیست.")
            method = next(m for m in self.proposal(site_id, run["proposal_id"])["methods"] if m["id"] == run["method_id"])
            kind = method["kind"]
            if kind in WP_META_FIELDS:
                field = WP_META_FIELDS[kind]; payload = {"meta": {field: snapshot["meta"].get(field, "")}}
            elif kind == "wp_noindex_off":
                payload = {"meta": {"emdad_noindex": snapshot["meta"].get("emdad_noindex", False)}}
            elif kind == "wp_title":
                payload = {"title": snapshot["title"]}
            else:
                payload = {"content": snapshot["content"]}
            self._wp_request(client, "POST", endpoint, payload)
        self.update_run(run_id, status="rolled_back")
        try:
            method = next(m for m in self.proposal(site_id, run["proposal_id"])["methods"] if m["id"] == run["method_id"])
            self._refresh_analysis(site, method.get("affected_urls") or [self.proposal(site_id, run["proposal_id"])["url"]])
        except Exception as exc:
            self.update_run(run_id, error=f"rollback_recrawl_failed: {exc.__class__.__name__}")
        return self.get_run(site_id, run_id)
