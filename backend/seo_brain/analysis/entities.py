"""Entity extraction (BRAND / MODEL / SERVICE / LOCATION) from REAL site data — no hard-coded entity list.

Evidence sources: taxonomy (category names), titles, URLs and content text.
Rules (all recorded in `entities.evidence` so every node is explainable):

  R1 SERVICE   the dominant leading phrase of titles/categories (e.g. "امداد خودرو") is the site's service.
  R2 LOCATION  a trailing "در <X>" phrase in titles ("in <X>") marks a location X.
  R3 BRAND     each content category (not the blog/uncategorized ones) names a brand: category name minus service words.
  R4 ALIAS     a title-subject (title minus service+location words) that has no digits and appears in >=50% of a
               brand-category's post titles is an alias of that brand (e.g. "ام وی ام" ~ "MVM").
  R5 MODEL     any other title-subject that contains a digit, or is a non-alias subject inside a brand category,
               is a MODEL whose parent is that brand.
  R6 MERGE     a subject whose token set is a subset of another entity's token set (ignoring generic words) is merged.
Optional human overrides: config/entities.yaml  (aliases / type corrections) — starts empty.
"""
from __future__ import annotations

import json
import logging
import re
import sqlite3
from collections import Counter, defaultdict
from urllib.parse import unquote

import yaml

from ..common.config import PROJECT_ROOT, SiteConfig
from ..database.db import j, rows, upsert

log = logging.getLogger("analysis.entities")

# Generic vocabulary of the domain (words, not entities). Persian + English.
GENERIC = {"امداد", "خودرو", "خودروهای", "خودروها", "انواع", "ماشین", "ماشین‌های", "خدمات", "سرویس", "تعمیر", "یدک", "یدک‌کش",
           "بلاگ", "وبلاگ", "مقالات", "اخبار", "دسته‌بندی", "نشده", "دسته", "بندی", "صفحه", "از", "و", "با", "برای", "به",
           "car", "auto", "service", "services", "blog", "news", "emdad", "roadside", "assistance"}
LOCATION_MARKERS = ("در",)          # Persian "in"
_TOKEN_RE = re.compile(r"[\w‌]+", re.U)
_ZWNJ = "‌"


def toks(s: str) -> list[str]:
    s = s.replace(_ZWNJ, " ").replace("ي", "ی").replace("ك", "ک")
    return [t.lower() for t in _TOKEN_RE.findall(s)]


def slugify(s: str) -> str:
    s = s.replace(_ZWNJ, "-").replace("ي", "ی").replace("ك", "ک").strip().lower()
    return re.sub(r"[\s_/]+", "-", re.sub(r"[^\w\s‌-]", "", s, flags=re.U)).strip("-") or "entity"


def strip_site_suffix(title: str) -> str:
    # Yoast titles are "X - Site"; WP titles are plain. Remove " - <site>" and " – <site>" if present.
    return re.split(r"\s+[-–|]\s+", title)[0].strip()


def split_title(title: str) -> tuple[list[str], str | None]:
    """Return (subject tokens without generic words, location) from a title."""
    t = strip_site_suffix(title)
    location = None
    words = t.split()
    for m in LOCATION_MARKERS:
        if m in words:
            i = len(words) - 1 - words[::-1].index(m)   # last occurrence
            if i < len(words) - 1:
                location = " ".join(words[i + 1:])
                words = words[:i]
                break
    subj = toks(" ".join(words))
    # strip only the LEADING run of generic words (service phrase); keep generic words inside proper names
    while subj and subj[0] in GENERIC:
        subj.pop(0)
    while subj and subj[-1] in GENERIC and subj[-1] in {"در", "و", "با", "برای", "به", "از"}:
        subj.pop()
    return subj, location


def _load_overrides() -> dict:
    p = PROJECT_ROOT / "config" / "entities.yaml"
    if p.exists():
        return yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    return {}


class Entity:
    def __init__(self, etype: str, name: str, source: str):
        self.type, self.name, self.source = etype, name, source
        self.aliases: set[str] = set()
        self.parent: str | None = None
        self.evidence: list[dict] = []
        self.tokens = set(t for t in toks(name) if t not in GENERIC)

    @property
    def slug(self) -> str:
        return slugify(self.name)

    def all_forms(self) -> set[str]:
        return {self.name} | self.aliases


def extract_entities(conn: sqlite3.Connection, site: SiteConfig) -> dict:
    sid = site.site_id
    posts = rows(conn, "SELECT wp_id, type, url, title, content_text FROM posts WHERE site_id=?", (sid,))
    cats = rows(conn, "SELECT wp_id, name, slug, parent_wp_id, count FROM categories WHERE site_id=? AND taxonomy='category'", (sid,))
    post_cats = defaultdict(set)
    for r in rows(conn, "SELECT post_wp_id, term_wp_id FROM post_terms WHERE site_id=? AND taxonomy='category'", (sid,)):
        post_cats[r["post_wp_id"]].add(r["term_wp_id"])
    cat_by_id = {c["wp_id"]: c for c in cats}
    overrides = _load_overrides()

    # R1 service: most common leading generic phrase across titles + category names
    lead = Counter()
    for t in [p["title"] for p in posts] + [c["name"] for c in cats]:
        w = toks(strip_site_suffix(t or ""))
        if w and w[0] in GENERIC:
            lead[w[0]] += 1
            if len(w) > 1 and w[1] in GENERIC:
                lead[w[0] + " " + w[1]] += 1
    entities: dict[tuple[str, str], Entity] = {}
    service_name = None
    if lead:
        # prefer the longest phrase that still covers >= 50% of titles
        n_titles = len(posts) + len(cats)
        best = [ph for ph, c in lead.most_common() if c >= 0.5 * n_titles]
        best.sort(key=lambda s: (-len(s.split()), -lead[s]))
        service_name = best[0] if best else lead.most_common(1)[0][0]
        e = Entity("SERVICE", service_name, "titles")
        e.evidence.append({"rule": "R1", "phrase_frequency": lead[service_name], "of": n_titles})
        entities[("SERVICE", e.slug)] = e

    # R3 brands from categories (exclude generic-only names, i.e. blog / uncategorized)
    brand_by_cat: dict[int, Entity] = {}
    for c in cats:
        name = unquote(c["name"] or "")
        subj, _ = split_title(name)
        if not subj:
            continue
        # display form: original words after the leading generic run
        orig = name.replace(_ZWNJ, " ").split()
        while orig and toks(orig[0]) and toks(orig[0])[0] in GENERIC:
            orig.pop(0)
        disp = " ".join(orig) or " ".join(subj)
        e = Entity("BRAND", disp, "taxonomy")
        e.evidence.append({"rule": "R3", "category": c["slug"], "category_name": name, "category_wp_id": c["wp_id"]})
        key = ("BRAND", e.slug)
        entities.setdefault(key, e)
        brand_by_cat[c["wp_id"]] = entities[key]
    # brand hierarchy follows the category hierarchy (sub-brand -> parent brand/company)
    for cid, b in brand_by_cat.items():
        parent = cat_by_id.get(cid, {}).get("parent_wp_id")
        if parent in brand_by_cat and brand_by_cat[parent] is not b:
            b.parent = brand_by_cat[parent].slug
            b.evidence.append({"rule": "R3", "parent_category": cat_by_id[parent]["slug"]})

    def cat_depth(cid: int) -> int:
        d, cur = 0, cid
        while cur and cat_by_id.get(cur, {}).get("parent_wp_id"):
            cur = cat_by_id[cur]["parent_wp_id"]
            d += 1
        return d

    # titles -> subjects / locations
    subj_in_cat: dict[int, Counter] = defaultdict(Counter)   # cat -> subject phrase counter
    page_subjects: dict[str, tuple[list[str], str | None, str]] = {}
    for p in posts:
        subj, loc = split_title(p["title"] or "")
        raw_subject = " ".join(subj)
        page_subjects[p["url"]] = (subj, loc, raw_subject)
        # R2 location
        if loc:
            e = Entity("LOCATION", loc, "titles")
            key = ("LOCATION", e.slug)
            ent = entities.setdefault(key, e)
            ent.evidence.append({"rule": "R2", "title": p["title"], "url": p["url"]})
        if raw_subject:
            for cid in post_cats.get(p["wp_id"], ()):
                if cid in brand_by_cat:
                    subj_in_cat[cid][raw_subject] += 1
                # posts in a sub-category also count for the parent brand category
                parent = cat_by_id.get(cid, {}).get("parent_wp_id")
                if parent in brand_by_cat and parent != cid:
                    subj_in_cat[parent][raw_subject] += 1

    # R4 aliases + R5 models — most specific (deepest) brand category first
    assigned: dict[str, str] = {}   # subject -> 'alias' | 'model'
    for cid in sorted(subj_in_cat, key=cat_depth, reverse=True):
        counter = subj_in_cat[cid]
        brand = brand_by_cat[cid]
        n_posts = sum(1 for p in posts if cid in post_cats.get(p["wp_id"], ()) or
                      any(cat_by_id.get(x, {}).get("parent_wp_id") == cid for x in post_cats.get(p["wp_id"], ())))
        for subject, cnt in counter.most_common():
            stoks = set(subject.split())
            if not stoks or subject in assigned:
                continue
            btoks = set(toks(brand.name))
            if stoks <= btoks or btoks <= stoks:      # R6 same brand (token subset, e.g. "مدیران" ~ "مدیران خودرو")
                if stoks != btoks:
                    brand.aliases.add(subject)
                    brand.evidence.append({"rule": "R6", "alias": subject, "reason": "token subset", "titles": cnt})
                assigned[subject] = "alias"
                continue
            has_digit = any(ch.isdigit() for ch in subject)
            if not has_digit and n_posts and cnt / n_posts >= 0.5:
                brand.aliases.add(subject)
                brand.evidence.append({"rule": "R4", "alias": subject, "titles_in_category": cnt, "of": n_posts})
                assigned[subject] = "alias"
                continue
            e = Entity("MODEL", subject, "titles")
            e.parent = brand.slug
            e.evidence.append({"rule": "R5", "brand_category": cat_by_id[cid]["slug"], "titles_in_category": cnt, "has_digit": has_digit})
            entities[("MODEL", e.slug)] = e
            assigned[subject] = "model"

    # canonical brand name = the longest alias form (by tokens) seen in >=2 titles, else the category form
    for e in list(entities.values()):
        if e.type != "BRAND":
            continue
        forms = Counter()
        for subj, loc, raw in page_subjects.values():
            if raw in e.aliases or raw == e.name:
                forms[raw] += 1
        cands = [f for f, c in forms.items() if c >= 2 and len(f.split()) > len(e.name.split()) and set(toks(e.name)) <= set(f.split())]
        if cands:
            new = max(cands, key=lambda f: (len(f.split()), forms[f]))
            e.aliases.discard(new)
            e.aliases.add(e.name)
            e.evidence.append({"rule": "R6", "canonical_name": new, "was": e.name, "title_frequency": forms[new]})
            old_slug = e.slug
            e.name = new
            for other in entities.values():
                if other.parent == old_slug:
                    other.parent = e.slug
            entities[("BRAND", e.slug)] = entities.pop(("BRAND", old_slug))

    # overrides (human-reviewed)
    for ov in overrides.get("aliases", []) or []:
        for e in entities.values():
            if e.name == ov.get("entity") or ov.get("entity") in e.aliases:
                e.aliases.update(ov.get("aliases", []))
                e.evidence.append({"rule": "override", "aliases": ov.get("aliases")})
    for ov in overrides.get("types", []) or []:
        for key, e in list(entities.items()):
            if e.name == ov.get("entity") and ov.get("type") in ("BRAND", "MODEL", "SERVICE", "LOCATION"):
                e.type = ov["type"]
                e.evidence.append({"rule": "override", "type": ov["type"]})
                entities[(e.type, e.slug)] = entities.pop(key)

    # persist entities
    conn.execute("DELETE FROM entity_mentions WHERE site_id=?", (sid,))
    conn.execute("DELETE FROM entities WHERE site_id=?", (sid,))
    for e in entities.values():
        upsert(conn, "entities", {"site_id": sid, "entity_type": e.type, "name": e.name, "slug": e.slug,
                                  "aliases": j(sorted(e.aliases)), "parent_slug": e.parent, "source": e.source,
                                  "evidence": j(e.evidence)}, ["site_id", "entity_type", "slug"])

    # mentions: page ABOUT entity — evidence-based scoring
    pages = rows(conn, "SELECT url, title, h1 FROM pages WHERE site_id=? AND status_code=200", (sid,))
    post_by_url = {p["url"]: p for p in posts}
    cat_urls = {c["wp_id"]: r["url"] for c in cats for r in rows(conn, "SELECT url FROM categories WHERE site_id=? AND wp_id=?", (sid, c["wp_id"]))}
    n_mentions = 0
    for pg in pages:
        url = pg["url"]
        title = strip_site_suffix(pg["title"] or "")
        h1s = " ".join(json.loads(pg["h1"]) if pg["h1"] else [])
        content = (post_by_url.get(url) or {}).get("content_text") or ""
        url_dec = unquote(url).lower()
        post = post_by_url.get(url)
        page_cats = post_cats.get(post["wp_id"], set()) if post else set()
        for e in entities.values():
            forms = [f for f in e.all_forms() if f]
            in_title = any(_contains(title, f) for f in forms)
            in_h1 = any(_contains(h1s, f) for f in forms)
            in_url = any(slugify(f) in url_dec or f.lower() in url_dec for f in forms)
            mentions = sum(_count(content, f) for f in forms)
            in_tax = 0
            if e.type == "BRAND":
                in_tax = int(any(brand_by_cat.get(c) is e for c in page_cats) or any(url == cat_urls.get(c) and brand_by_cat.get(c) is e for c in cat_urls))
            score = 3.0 * in_title + 2.0 * in_h1 + 1.5 * in_tax + 1.0 * in_url + min(mentions, 10) * 0.2
            if score <= 0:
                continue
            upsert(conn, "entity_mentions", {"site_id": sid, "url": url, "entity_type": e.type, "entity_slug": e.slug,
                                             "mentions": mentions, "in_title": int(in_title), "in_h1": int(in_h1),
                                             "in_url": int(in_url), "in_taxonomy": in_tax, "score": round(score, 2)},
                   ["site_id", "url", "entity_type", "entity_slug"])
            n_mentions += 1
    conn.commit()
    summary = {t: [f"{e.name}" + (f" (aliases: {', '.join(sorted(e.aliases))})" if e.aliases else "") + (f" -> {e.parent}" if e.parent else "")
                   for e in entities.values() if e.type == t] for t in ("SERVICE", "BRAND", "MODEL", "LOCATION")}
    summary["mentions"] = n_mentions
    log.info(f"entities: {json.dumps(summary, ensure_ascii=False)}")
    return summary


def _norm(s: str) -> str:
    return " ".join(toks(s))


def _contains(hay: str, needle: str) -> bool:
    return bool(needle) and (" " + _norm(needle) + " ") in (" " + _norm(hay) + " ")


def _count(hay: str, needle: str) -> int:
    if not needle:
        return 0
    return (" " + _norm(hay) + " ").count(" " + _norm(needle) + " ")
