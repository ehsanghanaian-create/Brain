from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from sqlalchemy import select

from ..tables import site_memory
from .base import Repository, dumps, loads, utcnow


@dataclass
class SiteMemory:
    """Per-site brain memory. Everything is explicit, human-editable JSON."""
    site_id: str
    business_rules: list[str] = field(default_factory=list)
    tone: dict[str, Any] = field(default_factory=dict)          # {voice, formality, audience, language_notes}
    content_rules: list[str] = field(default_factory=list)
    successful_patterns: list[dict[str, Any]] = field(default_factory=list)  # {pattern, evidence, source, run_id, created_at}
    audience: dict[str, Any] = field(default_factory=dict)      # {segments[], pains[], intent_notes}
    cta_rules: list[str] = field(default_factory=list)
    forbidden_claims: list[str] = field(default_factory=list)
    updated_at: str | None = None

    EDITABLE = ("business_rules", "tone", "audience", "cta_rules", "content_rules", "forbidden_claims", "successful_patterns")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class SiteMemoryRepository(Repository):
    def get(self, site_id: str) -> SiteMemory:
        with self.engine.connect() as cx:
            r = cx.execute(select(site_memory).where(site_memory.c.site_id == site_id)).first()
        if not r:
            return SiteMemory(site_id=site_id)
        m = r._mapping
        return SiteMemory(site_id=site_id, business_rules=loads(m["business_rules"], []), tone=loads(m["tone"], {}),
                          content_rules=loads(m["content_rules"], []), successful_patterns=loads(m["successful_patterns"], []),
                          audience=loads(m["audience"], {}), cta_rules=loads(m["cta_rules"], []),
                          forbidden_claims=loads(m["forbidden_claims"], []), updated_at=m["updated_at"])

    def save(self, mem: SiteMemory) -> SiteMemory:
        values = {"site_id": mem.site_id, "business_rules": dumps(mem.business_rules), "tone": dumps(mem.tone),
                  "content_rules": dumps(mem.content_rules), "successful_patterns": dumps(mem.successful_patterns),
                  "audience": dumps(mem.audience), "cta_rules": dumps(mem.cta_rules), "forbidden_claims": dumps(mem.forbidden_claims),
                  "updated_at": utcnow()}
        with self.engine.begin() as cx:
            self.upsert(cx, site_memory, values, conflict=["site_id"])
        return self.get(mem.site_id)

    def add_pattern(self, site_id: str, pattern: str, evidence: str, source: str, run_id: str | None = None) -> SiteMemory:
        mem = self.get(site_id)
        mem.successful_patterns.append({"pattern": pattern, "evidence": evidence, "source": source, "run_id": run_id, "created_at": utcnow()})
        return self.save(mem)
