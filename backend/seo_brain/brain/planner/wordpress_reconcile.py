"""Reconcile content plans with already-published WordPress posts, without a WP write.

Published content is imported as an unreviewed, versioned HTML snapshot. Plans with
no live post receive a brief and a content item, never a fabricated article draft.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from urllib.parse import urlparse

from sqlalchemy import Engine, text

from ..content.drafts import parse_draft


def _json(raw: str | None, fallback):
    try:
        return json.loads(raw or "")
    except (TypeError, ValueError):
        return fallback


def _slug(url: str | None, host: str) -> str | None:
    parsed = urlparse(url or "")
    if (parsed.hostname or "").lower() != host.lower():
        return None
    return parsed.path.rstrip("/").split("/")[-1] or None


def plan_actions(engine: Engine, site_id: str, live_posts: list[dict], live_body) -> list[dict]:
    """Build a fully validated read-only plan; `live_body(id)` fetches stale/missing snapshots."""
    with engine.connect() as cx:
        site = cx.execute(text("SELECT canonical_url FROM sites WHERE site_id=:s"), {"s": site_id}).first()
        plans = [dict(r) for r in cx.execute(text("SELECT * FROM content_plans WHERE site_id=:s ORDER BY id"), {"s": site_id}).mappings()]
        cached = {r["slug"]: dict(r) for r in cx.execute(text("SELECT wp_id,slug,status,content_html,excerpt,title,modified_gmt,word_count FROM posts WHERE site_id=:s AND type='post'"), {"s": site_id}).mappings()}
    if not site:
        raise ValueError("site not found")
    host = urlparse(site[0]).hostname or ""
    by_slug = {p["slug"]: p for p in live_posts if p.get("slug") and p.get("status") == "publish"}
    if len(by_slug) != len([p for p in live_posts if p.get("slug") and p.get("status") == "publish"]):
        raise ValueError("duplicate WordPress slugs")
    actions = []
    seen = set()
    for plan in plans:
        slug = _slug(plan["url"], host)
        if not slug or slug in seen:
            raise ValueError(f"plan {plan['id']} has a missing, foreign, or duplicate target URL")
        seen.add(slug)
        post = by_slug.get(slug)
        if not post:
            if plan["status"] == "published":
                raise ValueError(f"plan {plan['id']} claims published but has no live WordPress post")
            actions.append({"kind": "existing_link", "plan": plan, "post": None} if plan["content_item_id"]
                           else {"kind": "brief", "plan": plan, "slug": slug})
            continue
        if plan["content_item_id"] and plan["status"] == "published":
            actions.append({"kind": "existing_link", "plan": plan, "post": post})
            continue
        local = cached.get(slug)
        if local and local["wp_id"] == post["id"] and (local["modified_gmt"] or "")[:19] == (post.get("modified_gmt") or "")[:19]:
            body = local["content_html"] or ""
            title = local["title"] or plan["title"]
            excerpt = local["excerpt"] or ""
        else:
            fresh = live_body(post["id"])
            if fresh.get("id") != post["id"] or fresh.get("slug") != slug or fresh.get("status") != "publish":
                raise ValueError(f"WordPress post {post['id']} changed during reconciliation")
            content = fresh.get("content") or {}
            body = content.get("raw") or content.get("rendered") or ""
            title = (fresh.get("title") or {}).get("raw") or (fresh.get("title") or {}).get("rendered") or plan["title"]
            excerpt = (fresh.get("excerpt") or {}).get("raw") or ""
        structure, plain = parse_draft(body, "html")
        if len(body) < 300 or structure.word_count < 300:
            raise ValueError(f"WordPress post {post['id']} has no substantial article body")
        actions.append({"kind": "linked_published" if plan["content_item_id"] else "published",
                        "plan": plan, "post": post, "slug": slug,
                        "body": body, "body_text": plain, "structure": structure.to_dict(),
                        "title": title, "excerpt": excerpt})
    return actions


def action_counts(actions: list[dict]) -> dict[str, int]:
    return {kind: sum(a["kind"] == kind for a in actions)
            for kind in ("published", "brief", "linked_published", "existing_link")}


def apply_actions(engine: Engine, site_id: str, actions: list[dict], *, expected: dict[str, int] | None = None) -> dict[str, int]:
    """One transaction: all links, imported snapshots, and status corrections or none."""
    counts = action_counts(actions)
    if expected and any(counts.get(k) != v for k, v in expected.items()):
        raise ValueError(f"unexpected reconciliation counts: {counts}")
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with engine.begin() as cx:
        for action in actions:
            plan = action["plan"]
            pid = plan["id"]
            current = cx.execute(text("SELECT content_item_id,status FROM content_plans WHERE site_id=:s AND id=:p"), {"s": site_id, "p": pid}).first()
            if not current or current[0] != plan["content_item_id"] or current[1] != plan["status"]:
                raise ValueError(f"plan {pid} changed since preview")
            if action["kind"] == "existing_link":
                continue
            published = action["kind"] in ("published", "linked_published")
            post = action.get("post") or {}
            status = "published" if published else "brief_ready"
            meta = {"plan_id": pid, "source": "wordpress_reconciliation" if published else "content_plan",
                    "target_url": plan["url"]}
            if published:
                meta["wordpress_publication"] = {"wp_post_id": post["id"], "status": "publish", "url": plan["url"],
                                                 "wordpress_permalink": post.get("link"), "imported_at": now}
            previous_status = None
            if action["kind"] == "linked_published":
                cid = int(plan["content_item_id"])
                item = cx.execute(text("""SELECT status,wp_post_id,current_draft_id,metadata FROM content_items
                    WHERE site_id=:s AND id=:c"""), {"s": site_id, "c": cid}).first()
                draft_count = cx.execute(text("SELECT COUNT(*) FROM content_drafts WHERE site_id=:s AND content_id=:c"),
                                         {"s": site_id, "c": cid}).scalar()
                if not item or item[0] != "brief_ready" or item[1] or item[2] or draft_count:
                    raise ValueError(f"linked content {cid} changed or has a draft; manual review required")
                previous_status = item[0]
                meta = {**_json(item[3], {}), **meta}
                cx.execute(text("""UPDATE content_items SET status='published',url=:url,wp_post_id=:wp_id,
                    metadata=:meta,review_status='none',updated_at=:now WHERE site_id=:s AND id=:c"""),
                    {"url": plan["url"], "wp_id": post["id"], "meta": json.dumps(meta, ensure_ascii=False),
                     "now": now, "s": site_id, "c": cid})
            else:
                result = cx.execute(text("""INSERT INTO content_items
                    (site_id,title,slug,target_keyword_id,target_keyword,topic,cluster_id,intent,status,priority,
                     publish_date,publish_time,url,wp_post_id,metadata,created_at,updated_at,review_status)
                    VALUES (:s,:title,:slug,:kw_id,:kw,:topic,:cluster,:intent,:status,:priority,
                            :date,:time,:url,:wp_id,:meta,:now,:now,'none')"""),
                    {"s": site_id, "title": plan["title"], "slug": action["slug"], "kw_id": plan["primary_keyword_id"],
                     "kw": plan["primary_keyword"], "topic": plan["topic_id"], "cluster": plan["cluster_id"],
                     "intent": plan["intent"], "status": status, "priority": plan["priority"],
                     "date": plan["publish_date"], "time": plan["publish_time"],
                     "url": plan["url"] if published else None, "wp_id": post.get("id"),
                     "meta": json.dumps(meta, ensure_ascii=False), "now": now})
                cid = int(result.lastrowid)
            if published:
                structure = action["structure"]
                draft = cx.execute(text("""INSERT INTO content_drafts
                    (site_id,content_id,version,title,meta_description,format,body,body_text,word_count,
                     structure,source,author,change_summary,provenance,review_status,created_at)
                    VALUES (:s,:c,1,:title,:excerpt,'html',:body,:body_text,:words,:structure,
                            'wordpress:import','system:reconcile','Live WordPress snapshot',:provenance,'none',:now)"""),
                    {"s": site_id, "c": cid, "title": action["title"], "excerpt": action["excerpt"],
                     "body": action["body"], "body_text": action["body_text"], "words": structure["word_count"],
                     "structure": json.dumps(structure, ensure_ascii=False),
                     "provenance": json.dumps({"wp_post_id": post["id"], "modified_gmt": post.get("modified_gmt"),
                                                "source": "verified_live_post"}, ensure_ascii=False), "now": now})
                cx.execute(text("UPDATE content_items SET current_draft_id=:d WHERE id=:c AND site_id=:s"),
                           {"d": int(draft.lastrowid), "c": cid, "s": site_id})
                publishing = _json(plan["publishing"], {})
                publishing.update({"wp_post_id": post["id"], "wp_status": "publish", "link": plan["url"],
                                   "wordpress_permalink": post.get("link"), "reconciled_at": now})
                pub = json.dumps(publishing, ensure_ascii=False)
            else:
                outline = _json(plan["heading_structure"], [])
                targets = _json(plan["link_targets"], [])
                markdown = "# " + plan["title"] + "\n\n" + "\n".join("#" * min(max(h.get("level", 2), 2), 5) + " " + h.get("text", "") for h in outline)
                brief = cx.execute(text("""INSERT INTO content_briefs
                    (site_id,content_id,version,h1,seo_title,meta_description,intent,outline,internal_links,
                     sources,markdown,provenance,created_at)
                    VALUES (:s,:c,1,:title,:seo,:meta,:intent,:outline,:links,:sources,:markdown,:provenance,:now)"""),
                    {"s": site_id, "c": cid, "title": plan["title"], "seo": plan["seo_title"],
                     "meta": plan["meta_description"], "intent": plan["intent"],
                     "outline": json.dumps(outline, ensure_ascii=False), "links": json.dumps(targets, ensure_ascii=False),
                     "sources": json.dumps({"plan_id": pid}, ensure_ascii=False), "markdown": markdown,
                     "provenance": json.dumps({"source": "content_plan_reconciliation"}), "now": now})
                cx.execute(text("UPDATE content_items SET brief_id=:b WHERE id=:c AND site_id=:s"),
                           {"b": int(brief.lastrowid), "c": cid, "s": site_id})
                pub = plan["publishing"] or "{}"
            cx.execute(text("UPDATE content_plans SET content_item_id=:c,status=:status,publishing=:pub,updated_at=:now WHERE site_id=:s AND id=:p"),
                       {"c": cid, "status": status, "pub": pub, "now": now, "s": site_id, "p": pid})
            cx.execute(text("INSERT INTO content_events(site_id,content_id,from_status,to_status,actor,note,created_at) VALUES(:s,:c,:from_status,:status,'system:reconcile',:note,:now)"),
                       {"s": site_id, "c": cid, "from_status": previous_status, "status": status,
                        "note": "Linked to existing WordPress post" if published else "Brief linked from content plan", "now": now})
            cx.execute(text("INSERT INTO content_plan_events(site_id,content_plan_id,event,actor,from_value,to_value,payload,created_at) VALUES(:s,:p,:event,'system:reconcile',:from_status,:status,:payload,:now)"),
                       {"s": site_id, "p": pid, "event": "wordpress_reconciled" if published else "brief_linked",
                        "from_status": plan["status"], "status": status,
                        "payload": json.dumps({"content_id": cid, "wp_post_id": post.get("id")}, ensure_ascii=False), "now": now})
    return counts
