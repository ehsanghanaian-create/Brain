"""MemoryPack — everything the AI must know about the site, rendered through the `site.brain` prompt and stored as an
immutable snapshot (`memory_snapshots`) so every run/call records exactly what it was told. Mandatory in every agent prompt."""
from __future__ import annotations

import hashlib
from typing import Any

from sqlalchemy import Engine, and_, select, text

from ..db.repositories.base import dumps, loads, utcnow
from ..db.repositories.memory import SiteMemoryRepository
from ..db.tables import memory_snapshots
from .prompts.library import PromptLibrary, render

_TONE_FA = {"formal": "رسمی", "friendly": "صمیمی", "expert": "کارشناسی", "urgent": "فوری", "respectful": "محترمانه", "neutral": "خنثی", "casual": "خودمانی", "second-plural": "شما", "second-singular": "تو", "third": "سوم‌شخص"}


def _lines(items, empty="— (تعریف نشده)") -> str:
    items = [str(x) for x in (items or []) if str(x).strip()]
    return "\n".join(f"- {x}" for x in items) if items else empty


class MemoryPackBuilder:
    def __init__(self, engine: Engine):
        self.engine = engine
        self.memory = SiteMemoryRepository(engine)
        self.prompts = PromptLibrary(engine)

    def build(self, site_id: str) -> dict[str, Any]:
        mem = self.memory.get(site_id).to_dict()
        with self.engine.connect() as cx:
            r = cx.execute(text("SELECT name, canonical_url, language, country FROM sites WHERE site_id=:s"), {"s": site_id}).first()
            lk = cx.execute(text("SELECT value FROM site_settings WHERE site_id=:s AND key='linking'"), {"s": site_id}).first()
            accepted_link_patterns = [x[0] for x in cx.execute(text("SELECT message_fa FROM link_patterns WHERE site_id=:s AND status='accepted'"), {"s": site_id}).all()]
        tone = mem.get("tone") or {}
        aud = mem.get("audience") or {}
        pats = mem.get("successful_patterns") or []
        linking = loads(lk[0], {}) if lk else {}
        from ..brain.knowledge_pack import ContentKnowledgePackService
        knowledge = ContentKnowledgePackService(self.engine).latest(site_id, rebuild_if_missing=True)
        pack = {
            "site_name": r[0] if r else site_id, "site_url": r[1] if r else "", "language": (r[2] if r else None) or "fa-IR", "country": (r[3] if r else None) or "IR",
            "tone": {k: v for k, v in tone.items()}, "audience": aud,
            "business_rules": mem.get("business_rules") or [], "content_rules": mem.get("content_rules") or [], "cta_rules": mem.get("cta_rules") or [], "forbidden_claims": mem.get("forbidden_claims") or [],
            "successful_patterns": [p.get("pattern") if isinstance(p, dict) else str(p) for p in pats][-12:],
            "linking_rules": [f"انکرهای توصیفی و متنوع؛ حداقل {linking.get('min_internal_links', 3)} لینک داخلی؛ حرکت رو به جلو در سفر کاربر (اطلاعاتی → خدمت → تبدیل)",
                              "هرگز انکر عمومی مثل «اینجا/کلیک کنید» ننویس", *[f"الگوی پذیرفته‌شده: {p}" for p in accepted_link_patterns[:5]]],
            "knowledge_pack_id": knowledge.get("id") if knowledge else None,
            "knowledge_pack_version": knowledge.get("version") if knowledge else None,
            "knowledge_pack": knowledge.get("pack") if knowledge else {},
        }
        return pack

    def render(self, pack: dict[str, Any], site_id: str | None = None) -> str:
        v = self.prompts.active_version("site.brain", site_id) or {"template": "{{business_rules}}"}
        tone = pack.get("tone") or {}
        tone_s = "؛ ".join(f"{k}: {_TONE_FA.get(str(v), v)}" for k, v in tone.items() if v) or "— (تعریف نشده؛ رسمی و محترمانه بنویس)"
        aud = pack.get("audience") or {}
        aud_s = "؛ ".join(x for x in [("بخش‌ها: " + "، ".join(map(str, aud.get("segments", []))) if aud.get("segments") else ""), ("دردها: " + "، ".join(map(str, aud.get("pains", []))) if aud.get("pains") else ""), (f"اینتنت: {aud.get('intent_notes')}" if aud.get("intent_notes") else "")] if x) or "— (تعریف نشده)"
        base = render(v["template"], {"site_name": pack.get("site_name"), "site_url": pack.get("site_url"), "tone": tone_s, "audience": aud_s, "business_rules": _lines(pack.get("business_rules")),
                                      "content_rules": _lines(pack.get("content_rules")), "cta_rules": _lines(pack.get("cta_rules")), "forbidden_claims": _lines(pack.get("forbidden_claims"), "— (هیچ)"),
                                      "successful_patterns": _lines(pack.get("successful_patterns"), "— (هنوز الگویی ثبت نشده)"), "linking_rules": _lines(pack.get("linking_rules"))})
        from ..brain.knowledge_pack import ContentKnowledgePackService
        return base.rstrip() + "\n\n" + ContentKnowledgePackService.render(pack.get("knowledge_pack") or {})

    def snapshot(self, site_id: str) -> dict[str, Any]:
        """Build + render + persist (dedupe by hash). Returns {id, hash, pack, rendered}."""
        pack = self.build(site_id)
        rendered = self.render(pack, site_id)
        h = hashlib.sha256(rendered.encode("utf-8")).hexdigest()[:24]
        with self.engine.begin() as cx:
            r = cx.execute(select(memory_snapshots.c.id).where(and_(memory_snapshots.c.site_id == site_id, memory_snapshots.c.hash == h))).first()
            if r:
                sid = int(r[0])
            else:
                sid = int(cx.execute(memory_snapshots.insert().values(site_id=site_id, hash=h, pack=dumps(pack), rendered=rendered, created_at=utcnow())).inserted_primary_key[0])
        return {"id": sid, "hash": h, "pack": pack, "rendered": rendered}

    def get_snapshot(self, sid: int) -> dict | None:
        with self.engine.connect() as cx:
            r = cx.execute(select(memory_snapshots).where(memory_snapshots.c.id == sid)).first()
        if not r:
            return None
        d = dict(r._mapping); d["pack"] = loads(d["pack"], {}); return d
