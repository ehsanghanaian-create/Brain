# Graph schema

## Node types and IDs

| Type | node_id | Source of truth | Obsidian folder |
|---|---|---|---|
| SITE | `site:<site_id>` | `sites` | 00-Sites |
| PAGE | `page:<normalized url>` | `pages` (+ `posts` type=page) | 01-Pages |
| POST | `post:<normalized url>` | `pages` + `posts` type=post | 02-Posts |
| CATEGORY | `category:<taxonomy>:<slug>` | `categories` (+ crawl data of the archive URL) | 03-Categories |
| TAG | `tag:<taxonomy>:<slug>` | `tags` | 04-Tags |
| BRAND / MODEL / SERVICE / LOCATION | `brand:<slug>` … | `entities` (rule-based extraction with evidence) | 05–08 |
| QUERY | `query:<sha1[:12]>` | `queries` where `is_important=1` (capped by `graph.max_query_nodes`) | 09-Queries |
| SCHEMA | `schema:<Type>` | `schemas` (structural helper types skipped) | 10-Schemas |
| SEO_PROBLEM | `problem:<problem_type>` | `seo_problems` | 11-Problems |
| SEO_OPPORTUNITY | `opportunity:<opp_type>` | `seo_opportunities` | 12-Opportunities |

One node per normalized URL: a crawled category archive URL is merged into the CATEGORY node (no duplicate PAGE node). Uniqueness is validated after each build (`dup urls` = only SITE ↔ home page share a URL).

## Edge types

| Edge | From → To | Evidence |
|---|---|---|
| HAS_PAGE / HAS_POST / HAS_CATEGORY / HAS_TAG | SITE → … | WordPress |
| BELONGS_TO | POST → CATEGORY, CATEGORY → parent CATEGORY, MODEL → BRAND, BRAND → parent BRAND | `post_terms`, category parent, entity parent |
| LINKS_TO | PAGE/POST/CATEGORY → PAGE/POST/CATEGORY | crawled `<a href>` (weight = link count; `nav_only` flag; anchors) |
| ABOUT | page → BRAND/MODEL | entity mention in title/H1/URL/taxonomy or ≥5 body mentions |
| OFFERS | page → SERVICE | same rule |
| TARGETS | page → LOCATION | same rule |
| RANKS_FOR | page → QUERY | `gsc_query_page` (impressions ≥ 5), props: clicks/impressions/position |
| HAS_SCHEMA | page → SCHEMA (page-specific types); SITE → SCHEMA (site-wide types) | ld+json |
| HAS_PROBLEM / HAS_OPPORTUNITY | page → SEO_PROBLEM / SEO_OPPORTUNITY | analysis tables |

## Metrics

* `pagerank`: weighted PageRank on the LINKS_TO subgraph (pure-Python power iteration, α=0.85).
* `community`: Louvain on the undirected LINKS_TO graph (networkx, seed 42).
* `graph_fts`: FTS5 (unicode61, diacritics removed) over label, decoded URL, title/H1/description/excerpt/aliases.

## Entity extraction rules (see `src/analysis/entities.py`)

R1 service = dominant leading generic phrase of titles/categories · R2 location = trailing "در X" · R3 brand = content category name minus generic words (hierarchy follows category tree) · R4 alias = digit-free title subject in ≥ 50 % of a brand category's post titles · R5 model = other title subjects inside a brand category (most specific category wins) · R6 token-subset merge. Overrides: `config/entities.yaml` (`aliases:`, `types:`), empty by default. Every entity stores its `evidence` JSON.

Result for emdadmodiran.com (2026-08-16): SERVICE امداد خودرو · BRAND مدیران خودرو → MVM (alias ام وی ام), چری · MODEL تیگو 5, تیگو 7, فونیکس (→ چری) · LOCATION تهران.
