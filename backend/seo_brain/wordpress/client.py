"""WordPress REST API client — READ-ONLY (GET only).

Uses public endpoints; optionally authenticates with an Application Password
(WP_USERNAME / WP_APP_PASSWORD from .env) which unlocks menus/authors etc.
No method in this module can modify WordPress: there is no POST/PUT/PATCH/DELETE.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Iterator

from ..common.config import env, raw_data_dir
from ..common.http import ReadOnlyClient

log = logging.getLogger("wordpress")

# Post types that are WordPress/Elementor internals, never public content pages
INTERNAL_POST_TYPES = {
    "attachment", "nav_menu_item", "wp_block", "wp_template", "wp_template_part", "wp_global_styles",
    "wp_navigation", "wp_font_family", "wp_font_face", "elementor_library", "elementor_snippet",
    "e-floating-buttons", "e-landing-page", "product_variation", "shop_order", "shop_coupon",
}
INTERNAL_TAXONOMIES = {"nav_menu", "wp_pattern_category", "link_category", "post_format", "wp_theme", "wp_template_part_area", "elementor_library_type", "elementor_library_category"}


class WordPressClient:
    def __init__(self, wp_url: str, site_id: str, user_agent: str = "SEO-KG-WP-Client/0.1 (read-only)",
                 use_auth: bool = True, min_interval: float = 0.7, save_raw: bool = True):
        self.base = wp_url.rstrip("/") + "/wp-json"
        self.site_id = site_id
        auth = None
        self.authenticated = False
        if use_auth:
            from .auth import resolve_auth          # per-site SecretStore credentials first, then .env (legacy)
            a = resolve_auth(site_id)
            if a:
                auth = a.basic
                self.authenticated = True
        self.http = ReadOnlyClient(user_agent=user_agent, min_interval=min_interval, auth=auth)
        self.save_raw = save_raw
        self.raw_dir: Path = raw_data_dir() / "wordpress" / site_id
        if save_raw:
            self.raw_dir.mkdir(parents=True, exist_ok=True)

    def close(self):
        self.http.close()

    # -- low level -------------------------------------------------------------
    def get_json(self, route: str, params: dict | None = None) -> tuple[Any, dict]:
        url = self.base + route
        r = self.http.get(url, params=params, api="wordpress")
        if r.status_code >= 400:
            raise WPError(route, r.status_code, r.text[:300])
        return r.json(), dict(r.headers)

    def _dump(self, name: str, obj: Any) -> str | None:
        if not self.save_raw:
            return None
        p = self.raw_dir / f"{name}.json"
        p.write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")
        return str(p.relative_to(raw_data_dir().parent.parent))

    # -- discovery -----------------------------------------------------------------
    def root(self) -> dict:
        data, _ = self.get_json("/")
        self._dump("root", {k: v for k, v in data.items() if k != "routes"})
        return data

    def types(self) -> dict:
        data, _ = self.get_json("/wp/v2/types")
        self._dump("types", data)
        return data

    def taxonomies(self) -> dict:
        data, _ = self.get_json("/wp/v2/taxonomies")
        self._dump("taxonomies", data)
        return data

    def public_content_types(self) -> dict[str, dict]:
        """Post types that represent public content (post, page, public CPTs)."""
        out = {}
        for slug, t in self.types().items():
            if slug in INTERNAL_POST_TYPES:
                continue
            if not t.get("rest_base"):
                continue
            out[slug] = t
        return out

    def content_taxonomies(self) -> dict[str, dict]:
        return {s: t for s, t in self.taxonomies().items() if s not in INTERNAL_TAXONOMIES and t.get("rest_base")}

    # -- paginated collections ---------------------------------------------------------
    def iter_collection(self, rest_base: str, params: dict | None = None, per_page: int = 100) -> Iterator[dict]:
        page = 1
        params = dict(params or {})
        while True:
            q = {**params, "per_page": per_page, "page": page}
            data, headers = self.get_json(f"/wp/v2/{rest_base}", q)
            if not isinstance(data, list):
                raise WPError(rest_base, 200, f"unexpected payload type {type(data).__name__}")
            for item in data:
                yield item
            total_pages = int(headers.get("x-wp-totalpages") or headers.get("X-WP-TotalPages") or 1)
            if page >= total_pages or not data:
                break
            page += 1

    def fetch_all(self, rest_base: str, params: dict | None = None) -> list[dict]:
        items = list(self.iter_collection(rest_base, params))
        self._dump(rest_base.replace("/", "_"), items)
        log.info(f"fetched {len(items)} items from /wp/v2/{rest_base}", extra={"api": "wordpress", "endpoint": rest_base, "count": len(items)})
        return items

    def count(self, rest_base: str) -> int:
        _, headers = self.get_json(f"/wp/v2/{rest_base}", {"per_page": 1})
        return int(headers.get("x-wp-total") or headers.get("X-WP-Total") or 0)


class WPError(Exception):
    def __init__(self, route: str, status: int, body: str = ""):
        super().__init__(f"WordPress API error {status} on {route}: {body}")
        self.route, self.status, self.body = route, status, body
