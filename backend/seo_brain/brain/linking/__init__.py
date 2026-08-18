"""Internal Link Intelligence Engine (phase 8).

Scope-aware by design: every suggestion carries `scope` (internal now; external / backlink / competitor later) and the
engine is split into context → targets → scoring → anchors → audit/health → patterns, so future scopes only add a
context builder + candidate source. Nothing here writes to WordPress: analyze · suggest · approve · export only.
"""
from .context import LinkContext, PageInfo, build_context
from .journey import STAGES, classify_stage, journey_score
from .scoring import score_pair, confidence_of
from .anchors import suggest_anchor
from .audit import audit_pages, health_score
from .engine import LinkEngine
from .repository import LinkRepository

__all__ = ["LinkContext", "PageInfo", "build_context", "STAGES", "classify_stage", "journey_score", "score_pair", "confidence_of",
           "suggest_anchor", "audit_pages", "health_score", "LinkEngine", "LinkRepository"]
