"""MemoryService: reads site memory into prompts and records validated successes back.

Read path  : `context_messages(site_id)` → a system message summarising business rules / tone / content
             rules so every task for that site is grounded the same way.
Write path : `record_success(...)` appends a `successful_patterns` entry — only ever called by the
             orchestrator AFTER validation, with provenance (task kind, provider, model, run_id).
"""
from __future__ import annotations

from typing import Any

from ..db.repositories.memory import SiteMemory, SiteMemoryRepository
from .types import AIMessage


class MemoryService:
    def __init__(self, repo: SiteMemoryRepository):
        self.repo = repo

    def get(self, site_id: str) -> SiteMemory:
        return self.repo.get(site_id)

    def update(self, site_id: str, **fields: Any) -> SiteMemory:
        mem = self.repo.get(site_id)
        for k, v in fields.items():
            if k in SiteMemory.EDITABLE and v is not None:
                setattr(mem, k, v)
        return self.repo.save(mem)

    def context_messages(self, site_id: str) -> list[AIMessage]:
        mem = self.repo.get(site_id)
        parts: list[str] = []
        if mem.business_rules:
            parts.append("Business rules:\n- " + "\n- ".join(mem.business_rules))
        if mem.tone:
            parts.append("Tone: " + "; ".join(f"{k}={v}" for k, v in mem.tone.items()))
        if mem.audience:
            aud = []
            if mem.audience.get("segments"):
                aud.append("segments: " + ", ".join(map(str, mem.audience["segments"])))
            if mem.audience.get("pains"):
                aud.append("pains: " + ", ".join(map(str, mem.audience["pains"])))
            if mem.audience.get("intent_notes"):
                aud.append("intent: " + str(mem.audience["intent_notes"]))
            if aud:
                parts.append("Audience: " + "; ".join(aud))
        if mem.cta_rules:
            parts.append("CTA rules:\n- " + "\n- ".join(mem.cta_rules))
        if mem.content_rules:
            parts.append("Content rules:\n- " + "\n- ".join(mem.content_rules))
        if mem.forbidden_claims:
            parts.append("NEVER claim (forbidden):\n- " + "\n- ".join(mem.forbidden_claims))
        if mem.successful_patterns:
            recent = mem.successful_patterns[-5:]
            parts.append("Patterns that worked before:\n- " + "\n- ".join(p.get("pattern", "") for p in recent))
        if not parts:
            return []
        return [AIMessage(role="system", content=f"[site memory: {site_id}]\n" + "\n\n".join(parts))]

    def record_success(self, site_id: str, pattern: str, evidence: str, source: str, run_id: str | None = None) -> SiteMemory:
        return self.repo.add_pattern(site_id, pattern, evidence, source, run_id)
