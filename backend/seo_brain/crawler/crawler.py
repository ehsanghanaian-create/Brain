"""Read-only, robots-respecting, same-site crawler.

- seeds from robots.txt sitemaps (sitemap index supported), then follows internal links (BFS)
- hard cap `max_urls` (first run: 20), conservative concurrency (default 2), fixed delay per request
- respects robots.txt (protego), never crawls external hosts, never fetches excluded patterns
- records everything into SQLite (`pages`, `links`, `schemas`) + raw HTML snapshots under data/raw/crawler
"""
from __future__ import annotations

import gzip
import json
import logging
import re
import sqlite3
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit
from xml.etree import ElementTree as ET

import httpx
from protego import Protego

from ..common.config import SiteConfig, raw_data_dir
from ..common.http import ReadOnlyClient
from ..common.logging_setup import new_run_id
from ..database.db import ensure_site, j, upsert, utcnow
from ..normalizer import is_same_site, normalize_url
from .parser import parse_html

log = logging.getLogger("crawler")
_SM_NS = "{http://www.sitemaps.org/schemas/sitemap/0.9}"


@dataclass
class CrawlResult:
    url: str
    final_url: str | None = None
    status_code: int | None = None
    redirect_chain: list = field(default_factory=list)
    content_type: str | None = None
    response_time_ms: int | None = None
    x_robots_tag: str | None = None
    parsed: object | None = None
    error: str | None = None
    crawl_status: str = "ok"
    html: str | None = None


class Crawler:
    def __init__(self, site: SiteConfig, max_urls: int | None = None):
        self.site = site
        self.cfg = site.crawler
        self.max_urls = max_urls or self.cfg.max_urls
        self.host = site.host
        self.allowed = set(self.cfg.allowed_hosts) or {self.host}
        self.http = ReadOnlyClient(user_agent=self.cfg.user_agent, timeout=self.cfg.timeout_seconds,
                                   max_retries=self.cfg.max_retries, min_interval=self.cfg.delay_seconds,
                                   follow_redirects=False)
        self.robots: Protego | None = None
        self.sitemap_urls: list[str] = []
        # Keep the URL written in the sitemap separate from our database identity.
        # Normalization may add a slash that the live site redirects away from.
        self.sitemap_sources: dict[str, str] = {}
        self.raw_dir: Path = raw_data_dir() / "crawler" / site.site_id
        self.raw_dir.mkdir(parents=True, exist_ok=True)

    # -- policy -----------------------------------------------------------------
    def norm(self, url: str) -> str:
        return normalize_url(url, site_host=self.host,
                             extra_tracking_params=self.cfg.ignored_query_params)

    def excluded(self, url: str) -> bool:
        return any(pat in url for pat in self.cfg.exclude_patterns)

    def allowed_by_robots(self, url: str) -> bool:
        if not self.cfg.respect_robots or self.robots is None:
            return True
        return self.robots.can_fetch(url, self.cfg.user_agent)

    def crawlable(self, url: str) -> tuple[bool, str]:
        if not is_same_site(url, self.allowed):
            return False, "skipped_external"
        if self.excluded(url):
            return False, "skipped_excluded"
        path = urlsplit(url).path.lower()
        for prefix, limit in self.cfg.max_query_params_by_path.items():
            if path.startswith(prefix.lower()) and len({key for key, _ in parse_qsl(urlsplit(url).query)}) > limit:
                return False, "skipped_query_combination"
        if re.search(r"\.(jpe?g|png|gif|webp|svg|ico|css|js|pdf|zip|mp4|mp3|woff2?|ttf|xml|json|txt)$", path):
            return False, "skipped_asset"
        if not self.allowed_by_robots(url):
            return False, "skipped_robots"
        return True, "ok"

    # -- discovery ---------------------------------------------------------------
    def load_robots(self) -> str:
        url = f"{self.site.canonical_url.rstrip('/')}/robots.txt"
        r = self.http.get(url, follow_redirects=True, api="crawler")
        txt = r.text if r.status_code == 200 else ""
        self.robots = Protego.parse(txt)
        (self.raw_dir / "robots.txt").write_text(txt, encoding="utf-8")
        self.sitemap_urls = list(self.robots.sitemaps) if txt else []
        if not self.sitemap_urls:
            for cand in ("sitemap_index.xml", "sitemap.xml", "wp-sitemap.xml"):
                self.sitemap_urls.append(f"{self.site.canonical_url.rstrip('/')}/{cand}")
        log.info(f"robots.txt {r.status_code}; sitemaps: {self.sitemap_urls}")
        return txt

    def read_sitemaps(self, limit_docs: int = 50) -> list[str]:
        self.sitemap_sources = {}
        seen_docs, urls, queue = set(), [], deque(self.sitemap_urls)
        while queue and len(seen_docs) < limit_docs:
            sm = queue.popleft()
            if sm in seen_docs:
                continue
            seen_docs.add(sm)
            try:
                r = self.http.get(sm, follow_redirects=True, api="crawler")
            except httpx.HTTPError as e:
                log.warning(f"sitemap fetch failed {sm}: {e}")
                continue
            if r.status_code != 200:
                log.warning(f"sitemap {sm} -> {r.status_code}")
                continue
            body = r.content
            if sm.endswith(".gz"):
                body = gzip.decompress(body)
            try:
                root = ET.fromstring(body)
            except ET.ParseError as e:
                log.warning(f"sitemap parse error {sm}: {e}")
                continue
            (self.raw_dir / ("sitemap_" + re.sub(r"[^a-z0-9]+", "_", sm.split("/")[-1].lower()) + ".xml")).write_bytes(body)
            if root.tag == _SM_NS + "sitemapindex":
                for loc in root.iter(_SM_NS + "loc"):
                    if loc.text:
                        queue.append(loc.text.strip())
            else:
                for u in root.iter(_SM_NS + "url"):
                    loc = u.find(_SM_NS + "loc")
                    if loc is not None and loc.text:
                        urls.append(loc.text.strip())
        uniq = []
        seen = set()
        for u in urls:
            n = self.norm(u)
            if n not in seen:
                seen.add(n)
                uniq.append(n)
                self.sitemap_sources[n] = u
        log.info(f"sitemap inventory: {len(uniq)} URLs from {len(seen_docs)} sitemap docs")
        return uniq

    def ordered_seeds(self, conn: sqlite3.Connection, sitemap: set[str],
                      seeds: list[str] | None = None) -> list[str]:
        """Rotate a capped site crawl through unseen and oldest pages first.

        A fixed alphabetical order makes a daily 20-URL budget revisit the same
        20 pages forever. Explicit targeted crawls retain the caller's order.
        """
        if seeds is not None:
            return list(dict.fromkeys(self.norm(url) for url in seeds))
        home = self.norm(self.site.canonical_url)
        urls = sitemap | {home}
        last_crawled = {
            row[0]: row[1] for row in conn.execute(
                "SELECT url,last_crawled FROM pages WHERE site_id=?", (self.site.site_id,)
            )
        }
        return sorted(urls, key=lambda url: (
            0 if url == home and not last_crawled.get(url) else 1,
            bool(last_crawled.get(url)), last_crawled.get(url) or "", url,
        ))

    def record_sitemap_inventory(self, conn: sqlite3.Connection, sitemap: set[str]) -> None:
        """Keep every current sitemap URL visible, including those awaiting crawl."""
        if not sitemap:
            return  # A failed sitemap fetch is not evidence that URLs disappeared.
        current = sorted(url for url in sitemap if is_same_site(url, self.allowed))
        if not current:
            return
        conn.execute("UPDATE pages SET in_sitemap=0 WHERE site_id=? AND in_sitemap=1", (self.site.site_id,))
        conn.executemany(
            "INSERT OR IGNORE INTO pages(site_id,url,in_sitemap,crawl_status) VALUES(?,?,1,'pending')",
            ((self.site.site_id, url) for url in current),
        )
        conn.executemany(
            "UPDATE pages SET in_sitemap=1 WHERE site_id=? AND url=?",
            ((self.site.site_id, url) for url in current),
        )

    # -- fetch ----------------------------------------------------------------------
    def fetch(self, url: str, depth: int, request_url: str | None = None) -> CrawlResult:
        res = CrawlResult(url=url)
        chain = []
        cur = request_url or url
        t0 = time.monotonic()
        try:
            for _ in range(6):
                r = self.http.get(cur, follow_redirects=False, api="crawler")
                if r.status_code in (301, 302, 303, 307, 308) and r.headers.get("location"):
                    nxt = httpx.URL(cur).join(r.headers["location"])
                    chain.append([cur, r.status_code])
                    cur = str(nxt)
                    if not is_same_site(cur, self.allowed):
                        res.crawl_status = "redirect_external"
                        break
                    continue
                break
            res.response_time_ms = int((time.monotonic() - t0) * 1000)
            res.final_url = self.norm(cur) if is_same_site(cur, self.allowed) else cur
            res.status_code = r.status_code
            res.redirect_chain = chain
            res.content_type = r.headers.get("content-type")
            res.x_robots_tag = r.headers.get("x-robots-tag")
            if r.status_code == 200 and "html" in (res.content_type or ""):
                res.html = r.text
                res.parsed = parse_html(r.text, cur)
        except httpx.HTTPError as e:
            res.error = f"{e.__class__.__name__}: {e}"
            res.crawl_status = "error"
        return res

    # -- persist -----------------------------------------------------------------------
    def persist(self, conn: sqlite3.Connection, res: CrawlResult, depth: int, discovered_from: str | None,
                in_sitemap: bool, run_id: str) -> list[str]:
        """Write page + links; return newly discovered internal URLs (normalized)."""
        p = res.parsed
        new_urls: list[str] = []
        indexable, reason = None, None
        if res.status_code is not None:
            if res.status_code != 200:
                indexable, reason = 0, f"status_{res.status_code}"
            elif p is None:
                indexable, reason = 0, "non_html"
            else:
                robots = ((p.robots_meta or "") + " " + (res.x_robots_tag or "")).lower()
                if "noindex" in robots:
                    indexable, reason = 0, "noindex"
                elif p.canonical and self.norm(p.canonical) != (res.final_url or res.url):
                    indexable, reason = 0, "canonicalized_elsewhere"
                else:
                    indexable, reason = 1, "indexable"
        internal, external = 0, 0
        if p is not None:
            # A fresh crawl is authoritative for this source. Keeping old rows makes
            # removed links look present during remediation verification.
            conn.execute("DELETE FROM links WHERE site_id=? AND source_url=?", (self.site.site_id, res.final_url or res.url))
            html_path = self.raw_dir / (re.sub(r"[^a-z0-9]+", "_", res.url.lower())[:150] + ".html")
            html_path.write_text(res.html or "", encoding="utf-8")
            for lk in p.links:
                if is_same_site(lk.href, self.allowed):
                    tgt = self.norm(lk.href)
                    internal += 1
                    new_urls.append(tgt)
                    is_int = 1
                else:
                    tgt = lk.href
                    external += 1
                    is_int = 0
                conn.execute(
                    "INSERT OR IGNORE INTO links(site_id, source_url, target_url, anchor_text, rel, is_internal, is_nav, position, crawl_run_id) VALUES (?,?,?,?,?,?,?,?,?)",
                    (self.site.site_id, res.final_url or res.url, tgt, lk.anchor, lk.rel, is_int, 1 if lk.is_nav else 0, lk.position, run_id))
            for i, blk in enumerate(p.ld_json):
                items = blk.get("@graph", [blk]) if isinstance(blk, dict) else (blk if isinstance(blk, list) else [])
                for it in items:
                    if not isinstance(it, dict):
                        continue
                    t = it.get("@type")
                    t = ",".join(t) if isinstance(t, list) else (t or "Unknown")
                    upsert(conn, "schemas", {"site_id": self.site.site_id, "url": res.final_url or res.url, "schema_type": t,
                                             "schema_id": it.get("@id") or f"blk{i}", "json": j(it), "source": "ld+json"},
                           ["site_id", "url", "schema_type", "schema_id"], update_cols=["json", "source"])
        upsert(conn, "pages", {
            "site_id": self.site.site_id, "url": res.url, "final_url": res.final_url, "status_code": res.status_code,
            "redirect_chain": j(res.redirect_chain), "content_type": res.content_type, "response_time_ms": res.response_time_ms,
            "title": p.title if p else None, "meta_description": p.meta_description if p else None,
            "h1": j(p.h1) if p else None, "h1_count": len(p.h1) if p else None, "h2": j(p.h2) if p else None,
            "canonical": self.norm(p.canonical) if (p and p.canonical) else None,
            "robots_meta": p.robots_meta if p else None, "x_robots_tag": res.x_robots_tag,
            "indexable": indexable, "indexability_reason": reason,
            "word_count": p.word_count if p else None, "language": p.language if p else None,
            "images": j(p.images) if p else None,
            "images_missing_alt": sum(1 for im in p.images if not im.get("alt") and not im.get("decorative")) if p else None,
            "internal_links_out": internal if p else None, "external_links_out": external if p else None,
            "schema_types": j(p.schema_types) if p else None, "structured_data": j(p.ld_json) if p else None,
            "content_hash": p.content_hash if p else None, "in_sitemap": 1 if in_sitemap else 0,
            "discovered_from": discovered_from, "depth": depth,
            "crawl_status": res.crawl_status if not res.error else "error", "crawl_error": res.error,
            "last_crawled": utcnow(), "crawl_run_id": run_id,
        }, ["site_id", "url"])
        return new_urls

    # -- run ---------------------------------------------------------------------------
    def run(self, conn: sqlite3.Connection, seeds: list[str] | None = None) -> dict:
        run_id = new_run_id("crawl")
        ensure_site(conn, self.site)
        # ensure_site's write transaction serializes this check across workers.
        # A manual CLI crawl and the scheduler must not persist the same site's
        # pages concurrently; their link snapshots would overwrite each other.
        active_since = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat(timespec="milliseconds").replace("+00:00", "Z")
        active = conn.execute("""SELECT run_id FROM crawl_runs WHERE site_id=? AND status='running'
            AND started_at>=? ORDER BY started_at DESC LIMIT 1""", (self.site.site_id, active_since)).fetchone()
        if active:
            raise RuntimeError(f"crawl already running for {self.site.site_id}: {active['run_id']}")
        conn.execute("INSERT INTO crawl_runs(run_id, site_id, started_at, max_urls, status) VALUES (?,?,?,?,?)",
                     (run_id, self.site.site_id, utcnow(), self.max_urls, "running"))
        conn.commit()
        stats = {"run_id": run_id, "scope": "targeted" if seeds is not None else "site",
                 "crawled": 0, "failed": 0, "skipped": {}, "discovered": 0, "sitemap_urls": 0}
        try:
            self.load_robots()
            sitemap = set(self.read_sitemaps())
            stats["sitemap_urls"] = len(sitemap)
            if seeds is None:
                self.record_sitemap_inventory(conn, sitemap)
                conn.commit()
            queue: deque[tuple[str, int, str | None]] = deque()
            seen: set[str] = set()
            for u in self.ordered_seeds(conn, sitemap, seeds):
                if u not in seen:
                    seen.add(u)
                    queue.append((u, 0, None))
            with ThreadPoolExecutor(max_workers=max(1, self.cfg.concurrency)) as pool:
                while queue and stats["crawled"] + stats["failed"] < self.max_urls:
                    batch = []
                    while queue and len(batch) < self.cfg.concurrency and stats["crawled"] + stats["failed"] + len(batch) < self.max_urls:
                        url, depth, src = queue.popleft()
                        ok, why = self.crawlable(url)
                        if not ok:
                            stats["skipped"][why] = stats["skipped"].get(why, 0) + 1
                            if why == "skipped_robots":
                                upsert(conn, "pages", {"site_id": self.site.site_id, "url": url, "crawl_status": why,
                                                       "discovered_from": src, "depth": depth, "in_sitemap": 1 if url in sitemap else 0,
                                                       "crawl_run_id": run_id}, ["site_id", "url"],
                                       update_cols=["crawl_status", "crawl_run_id"])
                            continue
                        batch.append((url, depth, src))
                    futures = {pool.submit(self.fetch, u, d, self.sitemap_sources.get(u)): (u, d, s)
                               for u, d, s in batch}
                    for fut in as_completed(futures):
                        u, d, s = futures[fut]
                        res = fut.result()
                        if res.error:
                            # A transport failure is not evidence that the page or
                            # its links disappeared. Keep the last valid snapshot;
                            # the failed attempt is recorded on the crawl run.
                            stats["failed"] += 1
                            log.error(f"crawl error {u}: {res.error}", extra={"url": u})
                            continue
                        new_urls = self.persist(conn, res, d, s, u in sitemap, run_id)
                        conn.commit()
                        stats["crawled"] += 1
                        log.info(f"{res.status_code} {u} ({res.response_time_ms} ms, {len(new_urls)} internal links)", extra={"url": u, "status": res.status_code})
                        for nu in new_urls:
                            if nu not in seen:
                                seen.add(nu)
                                stats["discovered"] += 1
                                queue.append((nu, d + 1, res.final_url or u))
            stats["queue_remaining"] = len(queue)
            status = ("failed" if not stats["crawled"] else
                      "completed_with_errors" if stats["failed"] else
                      "completed" if not queue else "completed_capped")
            conn.execute("UPDATE crawl_runs SET finished_at=?, urls_crawled=?, urls_failed=?, status=?, notes=? WHERE run_id=?",
                         (utcnow(), stats["crawled"], stats["failed"], status, j(stats), run_id))
            conn.commit()
            log.info(f"crawl {status}: {stats}")
            return stats
        except Exception as e:
            conn.execute("UPDATE crawl_runs SET finished_at=?, status='failed', notes=? WHERE run_id=?", (utcnow(), str(e), run_id))
            conn.commit()
            raise
        finally:
            self.http.close()
