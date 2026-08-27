"""The ONE WordPress writer (Phase 16 slot) — the only module in the codebase allowed to send outbound HTTP writes.

Everything else in SEO Brain stays strictly read-only; the acceptance guard (test_10) scans every other package
for write verbs. Publishing is:
  • authenticated with the site's Application Password (SecretStore ref wp-auth-{site}, never .env-only)
  • mode-gated: automatic callers (scheduler) publish ONLY when the site's publish mode is «خودکار» (autopilot);
    a human clicking «انتشار» in the UI may publish in any mode (that click IS the approval)
  • fully audited: the WP response (post id/link) + actor + timestamp land in content_plans.publishing and a
    plan event, and the linked content item is marked published.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from typing import Any, Callable

import httpx
from sqlalchemy import Engine, text

from ...common.urls import wp_rest_v2
from ...wordpress.auth import resolve_auth

log = logging.getLogger("integrations.wordpress.writer")

PUBLISH_ROLES = {"administrator", "editor", "author"}


def _md_to_html(md: str) -> str:
    """Small, dependency-free Markdown→HTML for publishing (headings, bold/italic, links, lists, paragraphs)."""
    out: list[str] = []
    in_list = False
    for raw in (md or "").replace("\r\n", "\n").split("\n"):
        line = raw.rstrip()
        if not line.strip():
            if in_list:
                out.append("</ul>"); in_list = False
            continue
        m = re.match(r"^(#{1,4})\s+(.*)$", line)
        if m:
            if in_list:
                out.append("</ul>"); in_list = False
            lvl = min(len(m.group(1)) + 1, 5)          # '#' → h2 … (h1 is the post title)
            out.append(f"<h{lvl}>{_inline(m.group(2))}</h{lvl}>")
            continue
        m = re.match(r"^[-*]\s+(.*)$", line)
        if m:
            if not in_list:
                out.append("<ul>"); in_list = True
            out.append(f"<li>{_inline(m.group(1))}</li>")
            continue
        if in_list:
            out.append("</ul>"); in_list = False
        out.append(f"<p>{_inline(line)}</p>")
    if in_list:
        out.append("</ul>")
    return "\n".join(out)


def _inline(s: str) -> str:
    s = re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)", r'<a href="\2">\1</a>', s)
    s = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<em>\1</em>", s)
    return s


class WordPressWriter:
    """`http` is injectable for tests (no network in CI)."""

    def __init__(self, engine: Engine, http: Callable[..., httpx.Response] | None = None):
        self.engine = engine
        self._http = http

    def _request(self, method: str, url: str, auth: tuple[str, str], **kw) -> httpx.Response:
        if self._http:
            return self._http(method, url, auth=auth, **kw)
        return httpx.request(method, url, auth=auth, timeout=30, follow_redirects=True,
                             headers={"User-Agent": "SEO-Brain-Writer/1.0"}, **kw)

    def _site(self, site_id: str):
        with self.engine.connect() as cx:
            return cx.execute(text("SELECT wp_url, mode, canonical_url FROM sites WHERE site_id=:s"), {"s": site_id}).first()

    # ------------------------------------------------------------------ capability (users/me?context=edit)
    def capability(self, site_id: str) -> dict[str, Any]:
        """Can this site's stored Application Password actually publish? (role check, no write performed)."""
        site = self._site(site_id)
        if not site or not site[0]:
            return {"configured": False, "can_publish": False, "message": "آدرس وردپرس برای این سایت تنظیم نشده است"}
        auth = resolve_auth(site_id)
        if not auth:
            return {"configured": False, "can_publish": False,
                    "message": "‏Application Password ذخیره نشده — در کارت وردپرس، نام‌کاربری و رمز برنامه را وارد و تست کنید"}
        base = wp_rest_v2(site[0]).rstrip("/")
        try:
            r = self._request("GET", f"{base}/users/me?context=edit", (auth.username, auth.app_password))
        except Exception as e:  # noqa: BLE001
            return {"configured": True, "can_publish": False, "message": f"اتصال برقرار نشد ({e.__class__.__name__})"}
        if r.status_code != 200:
            # هاست‌های LiteSpeed/پلاگین‌های امنیتی اغلب مسیر wp/v2/users* را با 403 (صفحه HTML) می‌بندند —
            # در این حالت با یک probe فقط‌خواندنی نیازمند مجوز ویرایش (posts?context=edit) دسترسی را می‌سنجیم.
            html_block = "json" not in (r.headers.get("content-type") or "").lower()
            if r.status_code in (401, 403) and html_block:
                try:
                    r2 = self._request("GET", f"{base}/posts?context=edit&per_page=1", (auth.username, auth.app_password))
                except Exception as e:  # noqa: BLE001
                    return {"configured": True, "can_publish": False, "message": f"اتصال برقرار نشد ({e.__class__.__name__})"}
                if r2.status_code == 200:
                    return {"configured": True, "can_publish": True, "username": auth.username, "roles": [],
                            "message": "انتشار مجاز است — مسیر users توسط فایروال هاست بسته است؛ دسترسی ویرایش با probe جایگزین تأیید شد"}
                return {"configured": True, "can_publish": False,
                        "message": "احراز هویت ناموفق — رمز برنامه یا مجوز کاربر را بررسی کنید (مسیر users هم توسط فایروال هاست بسته است)"}
            return {"configured": True, "can_publish": False,
                    "message": "احراز هویت ناموفق (401/403) — رمز برنامه یا مجوز کاربر را بررسی کنید" if r.status_code in (401, 403) else f"HTTP {r.status_code}"}
        me = r.json()
        roles = me.get("roles") or []
        ok = bool(PUBLISH_ROLES & set(roles))
        return {"configured": True, "can_publish": ok, "username": me.get("slug") or auth.username, "roles": roles,
                "message": f"انتشار مجاز است ({'، '.join(roles)})" if ok else f"نقش کاربر ({'، '.join(roles) or 'نامشخص'}) اجازه انتشار ندارد — نقش author یا بالاتر لازم است"}

    # ------------------------------------------------------------------ publish one plan
    def publish_plan(self, site_id: str, plan_id: int, actor: str = "human", wp_status: str = "publish") -> dict[str, Any]:
        site = self._site(site_id)
        if not site or not site[0]:
            return {"status": "error", "message": "آدرس وردپرس تنظیم نشده است"}
        if actor != "human" and site[1] != "autopilot":
            return {"status": "skipped_mode",
                    "message": "حالت انتشار سایت «خودکار» نیست — انتشار زمان‌بندی‌شده فقط در حالت خودکار انجام می‌شود؛ از دکمه «انتشار» استفاده کنید"}
        with self.engine.connect() as cx:
            plan = cx.execute(text("SELECT id, title, seo_title, meta_description, content_item_id, category_id, publish_date, publish_time, status, publishing FROM content_plans WHERE site_id=:s AND id=:p"),
                              {"s": site_id, "p": plan_id}).first()
        if not plan:
            return {"status": "error", "message": "برنامه محتوا پیدا نشد"}
        publishing = {}
        try:
            publishing = json.loads(plan[9] or "{}")
        except ValueError:
            pass
        if publishing.get("wp_post_id"):
            return {"status": "already_published", "wp_post_id": publishing["wp_post_id"], "link": publishing.get("link"),
                    "message": "این برنامه قبلاً منتشر شده است"}
        if not plan[4]:
            return {"status": "no_draft", "message": "هنوز پیش‌نویسی تولید نشده — ابتدا «تولید پیش‌نویس» را بزنید"}
        with self.engine.connect() as cx:
            draft = cx.execute(text("SELECT body, title, meta_description FROM content_drafts WHERE site_id=:s AND content_id=:c ORDER BY version DESC LIMIT 1"),
                               {"s": site_id, "c": plan[4]}).first()
        if not draft or not (draft[0] or "").strip():
            return {"status": "no_draft", "message": "پیش‌نویس خالی است — ابتدا محتوا را تولید کنید"}
        auth = resolve_auth(site_id)
        if not auth:
            return {"status": "not_authorized", "message": "‏Application Password ذخیره نشده است"}
        # WP category term id via the planner category (content_categories.wordpress_category_id)
        wp_cat = None
        if plan[5]:
            with self.engine.connect() as cx:
                wp_cat = cx.execute(text("SELECT wordpress_category_id FROM content_categories WHERE site_id=:s AND id=:c"),
                                    {"s": site_id, "c": plan[5]}).scalar()
        payload: dict[str, Any] = {"title": plan[2] or plan[1], "content": _md_to_html(draft[0]),
                                   "status": wp_status, "excerpt": plan[3] or draft[2] or ""}
        if wp_cat:
            payload["categories"] = [int(wp_cat)]
        if plan[6]:                                     # honor the calendar date/time (site-local)
            payload["date"] = f"{plan[6]}T{(plan[7] or '09:00')}:00"
        try:
            r = self._request("POST", f"{wp_rest_v2(site[0]).rstrip('/')}/posts", (auth.username, auth.app_password), json=payload)
        except Exception as e:  # noqa: BLE001
            return {"status": "error", "message": f"ارسال به وردپرس ناموفق بود ({e.__class__.__name__})"}
        if r.status_code not in (200, 201):
            msg = "احراز هویت/مجوز رد شد" if r.status_code in (401, 403) else f"HTTP {r.status_code}"
            log.error(f"WP publish failed for {site_id}/plan {plan_id}: {r.status_code}")
            return {"status": "error", "http": r.status_code, "message": f"انتشار ناموفق: {msg}"}
        post = r.json()
        result = {"wp_post_id": post.get("id"), "link": post.get("link"), "wp_status": post.get("status"),
                  "published_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"), "actor": actor,
                  "category_wp_id": wp_cat}
        with self.engine.begin() as cx:
            cx.execute(text("UPDATE content_plans SET publishing=:pub, status='published', updated_at=:t WHERE site_id=:s AND id=:p"),
                       {"pub": json.dumps({**publishing, **result}, ensure_ascii=False), "t": result["published_at"], "s": site_id, "p": plan_id})
            cx.execute(text("INSERT INTO content_plan_events(site_id, content_plan_id, event, actor, from_value, to_value, payload, created_at) "
                            "VALUES(:s,:p,'published',:a,:f,'published',:pl,:t)"),
                       {"s": site_id, "p": plan_id, "a": actor, "f": plan[8], "pl": json.dumps(result, ensure_ascii=False), "t": result["published_at"]})
            cx.execute(text("UPDATE content_items SET status='published', url=:u, updated_at=:t WHERE site_id=:s AND id=:c"),
                       {"u": post.get("link"), "t": result["published_at"], "s": site_id, "c": plan[4]})
        log.info(f"published plan {plan_id} → WP post {post.get('id')} ({actor})")
        return {"status": "published", **result}
