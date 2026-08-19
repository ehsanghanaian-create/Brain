# WordPress connector (read-only)

Endpoint: `https://example.com/wp-json/` (discovered 2026-08-16: WordPress + Elementor 4.2.2 + Yoast SEO 28.2).

## What it does

1. `GET /wp-json/` → site name/description/namespaces (raw saved to `data/raw/wordpress/<site_id>/root.json`).
2. `GET /wp/v2/types` and `/wp/v2/taxonomies` → **dynamic discovery**. Internal/Elementor types (`elementor_library`, `e-floating-buttons`, `wp_block`, `nav_menu_item`, …) are excluded; anything else with a `rest_base` is treated as public content (so future CPTs are picked up automatically).
3. For each content type: paginated `GET /wp/v2/<rest_base>?status=publish&per_page=100` → table `posts` (columns include `type`, so pages, posts and CPT items share one table). Yoast `yoast_head_json` fields (title, description, canonical, robots, schema) are stored.
4. For each taxonomy: terms → `categories` (hierarchical) or `tags` (flat), relations → `post_terms`.
5. `GET /wp/v2/media?_fields=…` → `media` (alt text is used for the images-missing-alt analysis).

Discovered structure of example.com: 3 pages, 11 posts, 5 categories (2-level tree), 0 tags, 62 media, **no public CPTs, no custom taxonomies**.

## Authentication

Public endpoints need no auth. Optional `WP_USERNAME` + `WP_APP_PASSWORD` (WordPress **Application Password**, never the admin password) unlock `users`, `menus`, `menu-items`, `elementor_library`. Configure in `.env`. Not required for the MVP.

## robots.txt note

`robots.txt` disallows `/wp-json/` for crawlers. The HTML crawler therefore never touches `/wp-json/`. The WordPress connector is an API client (documented REST API, low rate, GET only) — a different access path from web crawling; if the site owner prefers, set `WP_USERNAME/WP_APP_PASSWORD` to make the access explicitly authorised, or disable the connector and rely on crawl data only.

## Guarantees

* Only `GET` requests exist in `backend/seo_brain/common/http.py` / `backend/seo_brain/wordpress/client.py`.
* Rate limit 0.7 s between requests, retry with exponential backoff on 429/5xx, stop on 401/403.
