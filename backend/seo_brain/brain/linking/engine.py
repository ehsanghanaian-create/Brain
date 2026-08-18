"""LinkEngine — analyze (audit → targets → pairs → suggestions → graph), status changes, patterns → Site Brain memory, export.

Nothing here touches WordPress. Analyze · suggest · approve · export only.
"""
from __future__ import annotations

import csv
import io
import uuid
from collections import Counter, defaultdict
from typing import Any

from sqlalchemy import Engine, text

from ...brain.content.drafts import DraftRepository
from ...brain.keywords.normalize import normalize_keyword
from ...db.repositories.memory import SiteMemoryRepository
from ...graph.model import GraphEdge
from ...graph.store import get_graph_store
from .anchors import suggest_anchor
from .audit import FLAG_FA, audit_pages
from .context import DEFAULT_LINKING, LinkContext, PageInfo, build_context
from .journey import STAGE_FA, is_meaningful
from .repository import CONF_FA, KIND_FA, LinkRepository
from .scoring import score_pair

_TOP_FA = {"topic": "ارتباط موضوعی", "entities": "موجودیت مشترک", "intent": "سفر کاربر", "authority": "اعتبار منبع", "anchor": "انکر آماده"}


class LinkEngine:
    def __init__(self, engine: Engine):
        self.engine = engine
        self.repo = LinkRepository(engine)
        self.settings_repo = DraftRepository(engine)          # site_settings helper lives there
        self.memory = SiteMemoryRepository(engine)

    def settings(self, site_id: str) -> dict[str, Any]:
        base = dict(DEFAULT_LINKING)
        stored = self.settings_repo.settings(site_id, "linking")
        for k, v in stored.items():
            base[k] = {**base[k], **v} if isinstance(v, dict) and isinstance(base.get(k), dict) else v
        return base

    def put_settings(self, site_id: str, patch: dict[str, Any]) -> dict[str, Any]:
        cur = self.settings(site_id)
        allowed = {k: v for k, v in patch.items() if k in DEFAULT_LINKING}
        if "weights" in allowed:
            allowed["weights"] = {**cur["weights"], **allowed["weights"]}
        self.settings_repo.put_settings(site_id, "linking", {**cur, **allowed})
        return self.settings(site_id)

    def page_count(self, site_id: str) -> int:
        with self.engine.connect() as cx:
            return int(cx.execute(text("SELECT count(*) FROM graph_nodes WHERE site_id=:s AND node_type IN ('PAGE','POST','CATEGORY')"), {"s": site_id}).scalar() or 0)

    # ------------------------------------------------------------------ analyze
    def analyze(self, site_id: str) -> dict[str, Any]:
        st = self.settings(site_id)
        mem = self.memory.get(site_id).to_dict()
        ctx = build_context(self.engine, site_id, st, mem)
        run_id = f"links-{uuid.uuid4().hex[:8]}"
        stats = audit_pages(ctx)
        self.repo.save_stats(site_id, stats)
        boosts = self._pattern_boosts(site_id)
        prs = sorted(p.pagerank for p in ctx.pages.values() if not p.is_content_item)
        low = int(st.get("low_inbound_threshold", 2)); min_score = float(st.get("min_score", 0.45))
        max_t = int(st.get("max_per_target", 5)); max_s = int(st.get("max_per_source", 3))
        # targets: pages that need/deserve links (published pages + planned content with a URL are targets; unpublished content are sources only via content_outbound)
        targets: list[PageInfo] = []
        for nid, p in ctx.pages.items():
            if p.is_content_item and not p.published:
                continue
            s = stats.get(nid)
            need = 1.0 if (s and s["inbound_body"] == 0) else (0.7 if s and s["inbound_body"] < low else 0.3)
            prio = 0.5 * need + 0.35 * p.value + (0.15 if p.striking or p.opportunities else 0)
            if prio >= 0.35 or (s and "orphan" in s["flags"]):
                p.value = max(p.value, prio); targets.append(p)
        targets.sort(key=lambda p: -p.value)
        candidates: list[dict[str, Any]] = []
        supports_edges: list[GraphEdge] = []
        for t in targets:
            pairs = []
            for sid, s in ctx.pages.items():
                if sid == t.node_id or (s.is_content_item and not s.published and t.is_content_item):
                    continue
                r = score_pair(ctx, s, t, prs, boosts.get(self._pattern_key(s.stage, t.stage), 0.0))
                if not r:
                    continue
                topical = max(r["components"]["topic"], r["components"]["entities"])      # topical similarity = topic/cluster OR shared specific entities
                if topical >= st.get("supports_min_topic", 0.6) and is_meaningful(s.stage, t.stage) and not (s.is_content_item and not s.published):
                    supports_edges.append(GraphEdge(s.node_id, t.node_id, "SUPPORTS", round(topical, 3), {"props": {"topic": r["components"]["topic"], "entities": r["components"]["entities"], "journey": r["journey"]["why"]}}, site_id))
                if r["score"] >= min_score:
                    pairs.append((s, r))
            pairs.sort(key=lambda x: -x[1]["score"])
            for s, r in pairs[:max_t]:
                anchor, alts, hint = suggest_anchor(ctx, s, t, r["matched_phrases"])
                kind = self._kind(ctx, s, t, stats)
                candidates.append(self._suggestion(site_id, s, t, r, anchor, alts, hint, kind, stats, run_id))
        # anchor_fix suggestions on existing weak links (existing link, generic/over-used anchor)
        candidates.extend(self._anchor_fixes(ctx, stats, run_id))
        # per-source cap (max 3 from the same source, keep the best)
        per_source: Counter = Counter(); final = []
        for c in sorted(candidates, key=lambda c: -c["score"]):
            if c["kind"] == "anchor_fix":
                final.append(c); continue
            if per_source[c["source_node_id"]] >= max_s:
                continue
            per_source[c["source_node_id"]] += 1; final.append(c)
        counts = self.repo.replace_run(site_id, final, run_id)
        graph = self._sync_graph(site_id, final, supports_edges)
        self.learn_patterns(site_id)
        by_conf = Counter(c["confidence"] for c in final)
        return {"run_id": run_id, "pages": len(ctx.pages), "targets": len(targets), "suggestions": len(final), "by_confidence": dict(by_conf), "supports_edges": len(supports_edges),
                **counts, "graph": graph, "stats": {"orphans": sum(1 for s in stats.values() if "orphan" in s["flags"]), "low_inbound": sum(1 for s in stats.values() if "low_inbound" in s["flags"]),
                                                     "avg_health": round(sum(s["health_score"] for s in stats.values()) / len(stats), 1) if stats else None}}

    @staticmethod
    def _kind(ctx: LinkContext, s: PageInfo, t: PageInfo, stats: dict) -> str:
        if s.is_content_item and not s.published:
            return "content_outbound"
        if stats.get(t.node_id, {}).get("inbound_total", 1) == 0:
            return "orphan_rescue"
        if s.stage == "hub" or s.node_type == "CATEGORY":
            return "hub_spoke"
        if s.stage == "informational" and t.stage in ("commercial", "service", "conversion"):
            return "supports"
        return "contextual"

    def _suggestion(self, site_id: str, s: PageInfo, t: PageInfo, r: dict, anchor: str, alts: list[str], hint: str, kind: str, stats: dict, run_id: str) -> dict[str, Any]:
        ts = stats.get(t.node_id, {})
        seo_bits = []
        if ts.get("inbound_body", 0) == 0: seo_bits.append("صفحه هدف هیچ لینک ورودی بدنه ندارد")
        elif ts.get("inbound_body", 0) < 3: seo_bits.append(f"صفحه هدف فقط {ts['inbound_body']} لینک ورودی بدنه دارد")
        if t.gsc.get("position") and 4 <= (t.gsc["position"] or 99) <= 20: seo_bits.append(f"جایگاه GSC {t.gsc['position']} ({t.gsc.get('impressions', 0)} ایمپرشن) — نزدیک صفحه اول")
        if t.opportunities: seo_bits.append("فرصت کلمه کلیدی: " + "، ".join(sorted(set(t.opportunities))[:2]))
        reason = "؛ ".join(r["reason_parts"] + seo_bits)
        top_comp = max(r["components"], key=lambda k: r["components"][k] * self.settings(site_id)["weights"][k])
        return {"kind": kind, "source_node_id": s.node_id, "source_url": s.url, "source_title": s.title, "source_stage": s.stage, "target_node_id": t.node_id, "target_url": t.url,
                "target_title": t.title, "target_stage": t.stage, "anchor": anchor, "anchor_alternatives": alts, "placement_hint": hint, "score": r["score"], "confidence": r["confidence"],
                "score_breakdown": {**r["components"], "journey": r["journey"]["score"], "pattern_boost": r["pattern_boost"], "penalties": r["penalties"], "top": top_comp},
                "reason_fa": reason, "evidence": {**r["evidence"], "target_inbound_body": ts.get("inbound_body"), "target_health": ts.get("health_score"), "target_gsc": t.gsc or None,
                                                  "target_keywords": t.keywords[:3], "journey": r["journey"]}, "run_id": run_id}

    def _anchor_fixes(self, ctx: LinkContext, stats: dict, run_id: str) -> list[dict[str, Any]]:
        out = []
        for (sid, tid), recs in ctx.links.items():
            s, t = ctx.pages.get(sid), ctx.pages.get(tid)
            if not s or not t:
                continue
            body = [r for r in recs if not r["nav"]]
            if not body:
                continue
            bad = [r for r in body if r["anchor"] and normalize_keyword(r["anchor"]) in ctx.generic_anchors]   # empty anchors = image links, not flagged
            over = "over_optimized_anchor" in stats.get(tid, {}).get("flags", [])
            if not bad and not over:
                continue
            anchor, alts, hint = suggest_anchor(ctx, s, t, [])
            if over and (not anchor or normalize_keyword(anchor) == normalize_keyword(t.primary_keyword or "")):
                anchor = (alts[0] if alts else anchor)
            why = ("انکر عمومی «" + (bad[0]["anchor"] or "خالی") + "» را با انکر توصیفی جایگزین کنید") if bad else "انکر دقیق بیش از ۶۰٪ لینک‌های ورودی را تشکیل می‌دهد — تنوع انکر"
            out.append({"kind": "anchor_fix", "source_node_id": sid, "source_url": s.url, "source_title": s.title, "source_stage": s.stage, "target_node_id": tid, "target_url": t.url, "target_title": t.title,
                        "target_stage": t.stage, "anchor": anchor, "anchor_alternatives": alts, "placement_hint": "روی لینک موجود", "score": 0.6 if bad else 0.5, "confidence": "recommended" if bad else "low",
                        "score_breakdown": {"top": "anchor"}, "reason_fa": why, "evidence": {"current_anchors": [r["anchor"] for r in body][:5], "exact_match_ratio": stats.get(tid, {}).get("exact_match_ratio")}, "run_id": run_id})
        return out

    # ------------------------------------------------------------------ graph
    def _sync_graph(self, site_id: str, suggestions: list[dict], supports: list[GraphEdge]) -> dict[str, int]:
        store = get_graph_store(self.engine)
        with self.engine.begin() as cx:
            cx.execute(text("DELETE FROM graph_edges WHERE site_id=:s AND edge_type IN ('LINK_OPPORTUNITY','SUPPORTS')"), {"s": site_id})
        edges = []
        for s in suggestions:
            if s["kind"] == "anchor_fix":
                continue
            edges.append(GraphEdge(s["source_node_id"], s["target_node_id"], "LINK_OPPORTUNITY", s["score"], {"props": {"anchor": s["anchor"], "kind": s["kind"], "confidence": s["confidence"], "reason": s["reason_fa"][:200]}}, site_id))
        # dedupe supports
        seen = set(); sup = []
        for e in supports:
            if (e.source, e.target) not in seen:
                seen.add((e.source, e.target)); sup.append(e)
        existing = {n.id for n in store.list_nodes(site_id, ["PAGE", "POST", "CATEGORY", "CONTENT"], limit=100000)}
        edges = [e for e in edges if e.source in existing and e.target in existing]; sup = [e for e in sup if e.source in existing and e.target in existing]
        return {"link_opportunity": store.upsert_edges(edges), "supports": store.upsert_edges(sup)}

    def set_status(self, site_id: str, sid: int, status: str, anchor: str | None = None) -> dict | None:
        s = self.repo.set_status(site_id, sid, status, anchor)
        if not s:
            return None
        store = get_graph_store(self.engine)
        with self.engine.begin() as cx:
            if status in ("accepted", "done"):
                cx.execute(text("DELETE FROM graph_edges WHERE site_id=:s AND edge_type='LINK_OPPORTUNITY' AND source_id=:a AND target_id=:b"), {"s": site_id, "a": s["source_node_id"], "b": s["target_node_id"]})
            elif status == "dismissed":
                cx.execute(text("DELETE FROM graph_edges WHERE site_id=:s AND edge_type IN ('LINK_OPPORTUNITY','SUGGESTED_LINK') AND source_id=:a AND target_id=:b"), {"s": site_id, "a": s["source_node_id"], "b": s["target_node_id"]})
        if status in ("accepted", "done") and s["kind"] != "anchor_fix":
            store.upsert_edges([GraphEdge(s["source_node_id"], s["target_node_id"], "SUGGESTED_LINK", s["score"], {"props": {"anchor": s["anchor"], "done": status == "done", "suggestion_id": sid}}, site_id)])
        self.learn_patterns(site_id)
        return self.repo.get(site_id, sid)

    # ------------------------------------------------------------------ patterns
    @staticmethod
    def _pattern_key(src_stage: str, tgt_stage: str) -> str:
        return f"journey:{src_stage}>{tgt_stage}"

    def learn_patterns(self, site_id: str) -> list[dict]:
        rows, _ = self.repo.list(site_id, status="accepted,dismissed,done", limit=100000)
        agg: dict[str, dict] = defaultdict(lambda: {"accepted": 0, "dismissed": 0, "done": 0, "feature": {}})
        for r in rows:
            top = (r.get("score_breakdown") or {}).get("top", "topic")
            keys = [(self._pattern_key(r["source_stage"], r["target_stage"]), {"source_stage": r["source_stage"], "target_stage": r["target_stage"]}),
                    (f"component:{top}", {"top_component": top}), (f"kind:{r['kind']}", {"kind": r["kind"]})]
            ev = r.get("evidence") or {}
            if ev.get("shared_entities"):
                keys.append(("anchor:entity", {"anchor_style": "entity"}))
            for k, f in keys:
                a = agg[k]; a["feature"] = f
                if r["status"] == "accepted": a["accepted"] += 1
                elif r["status"] == "done": a["accepted"] += 1; a["done"] += 1
                else: a["dismissed"] += 1
        out = []
        for k, a in agg.items():
            tot = a["accepted"] + a["dismissed"]
            if tot < 2:
                continue
            f = a["feature"]
            if "source_stage" in f:
                desc = f"لینک از صفحات {STAGE_FA.get(f['source_stage'], f['source_stage'])} به {STAGE_FA.get(f['target_stage'], f['target_stage'])}"
            elif "top_component" in f:
                desc = f"پیشنهادهایی که دلیل اصلی‌شان «{_TOP_FA.get(f['top_component'], f['top_component'])}» است"
            elif "kind" in f:
                desc = f"پیشنهادهای نوع «{KIND_FA.get(f['kind'], f['kind'])}»"
            else:
                desc = "انکر بر پایه نام مدل/خدمت"
            rate = a["accepted"] / tot
            msg = f"{desc}: {rate:.0%} پذیرفته شده ({a['accepted']} از {tot}؛ {a['done']} انجام‌شده)"
            self.repo.upsert_pattern(site_id, k, f, a["accepted"], a["dismissed"], a["done"], msg)
            out.append({"key": k, "rate": rate, "n": tot})
        return out

    def _pattern_boosts(self, site_id: str) -> dict[str, float]:
        """Bounded boosts (≤0.1) only from patterns the user accepted into memory; dismissed patterns reduce (never below 0)."""
        boosts: dict[str, float] = {}
        for p in self.repo.patterns(site_id):
            if p["status"] == "accepted":
                boosts[p["pattern_key"]] = min(0.1, 0.1 * p["acceptance_rate"])
            elif p["status"] == "dismissed":
                boosts[p["pattern_key"]] = 0.0
        return boosts

    def set_pattern_status(self, site_id: str, pid: int, status: str) -> dict | None:
        p = next((x for x in self.repo.patterns(site_id) if x["id"] == pid), None)
        if not p:
            return None
        ref = p.get("memory_pattern_ref")
        if status == "accepted" and not ref:
            ref = f"linkpattern:{pid}"
            self.memory.add_pattern(site_id, pattern=p["message_fa"], evidence=f"acceptance {p['acceptance_rate']:.0%} · accepted {p['accepted']} · dismissed {p['dismissed']} · done {p['done']}",
                                    source="internal_linking", run_id=ref + "|" + p["pattern_key"])
        return self.repo.set_pattern_status(site_id, pid, status, ref if status == "accepted" else None)

    # ------------------------------------------------------------------ export
    def export_csv(self, site_id: str, status: str | None = "accepted,done") -> str:
        rows, _ = self.repo.list(site_id, status=status, limit=100000)
        buf = io.StringIO(); w = csv.writer(buf)
        w.writerow(["status", "kind", "confidence", "score", "source_url", "source_title", "target_url", "target_title", "anchor", "placement_hint", "reason"])
        for r in rows:
            w.writerow([r["status"], r["kind"], r["confidence"], r["score"], r["source_url"], r["source_title"], r["target_url"], r["target_title"], r["anchor"], r["placement_hint"], r["reason_fa"]])
        return "﻿" + buf.getvalue()

    # ------------------------------------------------------------------ page detail
    def page_detail(self, site_id: str, node_id: str) -> dict | None:
        p = self.repo.page(site_id, node_id)
        if not p:
            return None
        ctx_rows = {}
        with self.engine.connect() as cx:
            r = cx.execute(text("SELECT url FROM graph_nodes WHERE site_id=:s AND node_id=:n"), {"s": site_id, "n": node_id}).first()
            url = r[0] if r else p["url"]
            try:
                inbound = [dict(x._mapping) for x in cx.execute(text("SELECT source_url, anchor_text, is_nav FROM links WHERE site_id=:s AND target_url=:u"), {"s": site_id, "u": url}).all()]
                outbound = [dict(x._mapping) for x in cx.execute(text("SELECT target_url, anchor_text, is_nav, is_internal FROM links WHERE site_id=:s AND source_url=:u"), {"s": site_id, "u": url}).all()]
            except Exception:  # noqa: BLE001
                inbound, outbound = [], []
        p["inbound"] = inbound[:50]; p["outbound"] = outbound[:50]
        p["suggestions_to"] = self.repo.list(site_id, target=node_id, limit=20)[0]
        p["suggestions_from"] = self.repo.list(site_id, source=node_id, limit=20)[0]
        p["flags_fa"] = [FLAG_FA.get(f, f) for f in p["flags"]]
        return p
