"""PromptLibrary — DB-versioned prompts: keys, versions, variables, activation, approval, tests/performance. Renderer with {{var}}."""
from __future__ import annotations

import re
from typing import Any

from sqlalchemy import Engine, and_, func, select

from ...db.repositories.base import Repository, dumps, loads, utcnow
from ...db.tables import prompt_tests, prompt_versions, prompts
from .defaults import DEFAULT_PROMPTS

_VAR = re.compile(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}")


class PromptError(ValueError):
    pass


def render(template: str, variables: dict[str, Any], require_memory: bool = False) -> str:
    if require_memory and "{{memory_pack}}" not in template.replace(" ", ""):
        raise PromptError("template must contain {{memory_pack}} — generic AI writing is not allowed")
    def sub(m):
        k = m.group(1)
        v = variables.get(k, "")
        if v is None:
            v = ""
        if isinstance(v, (list, dict)):
            import json
            v = json.dumps(v, ensure_ascii=False)
        return str(v)
    return _VAR.sub(sub, template)


def variables_of(template: str) -> list[str]:
    seen = []
    for m in _VAR.finditer(template):
        if m.group(1) not in seen:
            seen.append(m.group(1))
    return seen


class PromptLibrary(Repository):
    def seed(self) -> int:
        """Insert built-in prompts as v1 (active + approved) when the key does not exist yet. Idempotent."""
        n = 0
        with self.engine.begin() as cx:
            existing = {r[0] for r in cx.execute(select(prompts.c.key).where(prompts.c.site_id.is_(None))).all()}
            for d in DEFAULT_PROMPTS:
                if d["key"] in existing:
                    continue
                pid = int(cx.execute(prompts.insert().values(key=d["key"], scope=d["scope"], site_id=None, title=d["title"], description=d.get("description"), tags=dumps(d.get("tags", [])), created_at=utcnow())).inserted_primary_key[0])
                cx.execute(prompt_versions.insert().values(prompt_id=pid, version=1, template=d["template"], variables=dumps(d.get("variables", variables_of(d["template"]))), model_hints=dumps(d.get("model_hints", {})),
                                                           is_active=1, approval="approved", approved_by="seed", approved_at=utcnow(), changelog="built-in v1", created_by="seed", created_at=utcnow()))
                n += 1
        return n

    # ---- reads
    def list(self, site_id: str | None = None, scope: str | None = None) -> list[dict[str, Any]]:
        with self.engine.connect() as cx:
            rows = [dict(r._mapping) for r in cx.execute(select(prompts).order_by(prompts.c.scope, prompts.c.key)).all()]
            vers = [dict(r._mapping) for r in cx.execute(select(prompt_versions)).all()]
        by_prompt: dict[int, list[dict]] = {}
        for v in vers:
            by_prompt.setdefault(v["prompt_id"], []).append(v)
        out = []
        for p in rows:
            if scope and p["scope"] != scope:
                continue
            if p["site_id"] not in (None, site_id):
                continue
            vs = sorted(by_prompt.get(p["id"], []), key=lambda v: -v["version"])
            active = next((v for v in vs if v["is_active"]), None)
            p["tags"] = loads(p["tags"], []); p["versions"] = [{k: (loads(v[k], []) if k in ("variables", "model_hints") else v[k]) for k in v} for v in vs]
            p["active_version"] = active["version"] if active else None
            out.append(p)
        return out

    def get(self, pid: int) -> dict | None:
        for p in self.list():
            if p["id"] == pid:
                return p
        return None

    def active_version(self, key: str, site_id: str | None = None) -> dict | None:
        """Site override first, then global. Returns version row with prompt meta."""
        with self.engine.connect() as cx:
            for sid in ([site_id] if site_id else []) + [None]:
                q = select(prompts.c.id, prompts.c.key, prompts.c.scope).where(and_(prompts.c.key == key, prompts.c.site_id.is_(None) if sid is None else prompts.c.site_id == sid))
                p = cx.execute(q).first()
                if not p:
                    continue
                v = cx.execute(select(prompt_versions).where(and_(prompt_versions.c.prompt_id == p[0], prompt_versions.c.is_active == 1)).order_by(prompt_versions.c.version.desc())).first()
                if v:
                    d = dict(v._mapping); d["variables"] = loads(d["variables"], []); d["model_hints"] = loads(d["model_hints"], {}); d["key"] = key; d["scope"] = p[2]; d["ref"] = f"{key}@v{d['version']}"
                    return d
        return None

    def version(self, vid: int) -> dict | None:
        with self.engine.connect() as cx:
            v = cx.execute(select(prompt_versions).where(prompt_versions.c.id == vid)).first()
            if not v:
                return None
            p = cx.execute(select(prompts).where(prompts.c.id == v._mapping["prompt_id"])).first()
        d = dict(v._mapping); d["variables"] = loads(d["variables"], []); d["model_hints"] = loads(d["model_hints"], {}); d["key"] = p._mapping["key"]; d["scope"] = p._mapping["scope"]; d["ref"] = f"{d['key']}@v{d['version']}"
        return d

    # ---- writes
    def create_prompt(self, key: str, scope: str, title: str, template: str, site_id: str | None = None, description: str | None = None, model_hints: dict | None = None, created_by: str | None = None) -> dict:
        if scope in ("agent", "task"):
            render(template, {}, require_memory=True)
        with self.engine.begin() as cx:
            pid = int(cx.execute(prompts.insert().values(key=key, scope=scope, site_id=site_id, title=title, description=description, tags="[]", created_at=utcnow())).inserted_primary_key[0])
            cx.execute(prompt_versions.insert().values(prompt_id=pid, version=1, template=template, variables=dumps(variables_of(template)), model_hints=dumps(model_hints or {}), is_active=1, approval="draft",
                                                       changelog="v1", created_by=created_by, created_at=utcnow()))
        return self.get(pid)  # type: ignore[return-value]

    def add_version(self, pid: int, template: str, changelog: str | None = None, model_hints: dict | None = None, created_by: str | None = None, activate: bool = False) -> dict:
        p = self.get(pid)
        if not p:
            raise KeyError(pid)
        if p["scope"] in ("agent", "task"):
            render(template, {}, require_memory=True)
        with self.engine.begin() as cx:
            v = (cx.execute(select(func.max(prompt_versions.c.version)).where(prompt_versions.c.prompt_id == pid)).scalar() or 0) + 1
            if activate:
                cx.execute(prompt_versions.update().where(prompt_versions.c.prompt_id == pid).values(is_active=0))
            vid = int(cx.execute(prompt_versions.insert().values(prompt_id=pid, version=v, template=template, variables=dumps(variables_of(template)), model_hints=dumps(model_hints or {}), is_active=int(activate),
                                                                 approval="draft", changelog=changelog or f"v{v}", created_by=created_by, created_at=utcnow())).inserted_primary_key[0])
        return self.version(vid)  # type: ignore[return-value]

    def set_version(self, vid: int, activate: bool | None = None, approval: str | None = None, approved_by: str | None = None, changelog: str | None = None) -> dict | None:
        v = self.version(vid)
        if not v:
            return None
        with self.engine.begin() as cx:
            if activate is True:
                cx.execute(prompt_versions.update().where(prompt_versions.c.prompt_id == v["prompt_id"]).values(is_active=0))
                cx.execute(prompt_versions.update().where(prompt_versions.c.id == vid).values(is_active=1))
            elif activate is False:
                cx.execute(prompt_versions.update().where(prompt_versions.c.id == vid).values(is_active=0))
            vals: dict[str, Any] = {}
            if approval in ("draft", "approved", "retired"):
                vals.update(approval=approval, approved_by=approved_by if approval == "approved" else None, approved_at=utcnow() if approval == "approved" else None)
            if changelog is not None:
                vals["changelog"] = changelog
            if vals:
                cx.execute(prompt_versions.update().where(prompt_versions.c.id == vid).values(**vals))
        return self.version(vid)

    # ---- tests / performance
    def record_test(self, vid: int, **fields) -> int:
        with self.engine.begin() as cx:
            return int(cx.execute(prompt_tests.insert().values(prompt_version_id=vid, created_at=utcnow(), **{k: v for k, v in fields.items() if k in prompt_tests.c.keys()})).inserted_primary_key[0])

    def tests(self, pid: int) -> list[dict]:
        with self.engine.connect() as cx:
            vids = [r[0] for r in cx.execute(select(prompt_versions.c.id).where(prompt_versions.c.prompt_id == pid)).all()]
            rows = [dict(r._mapping) for r in cx.execute(select(prompt_tests).where(prompt_tests.c.prompt_version_id.in_(vids)).order_by(prompt_tests.c.id.desc())).all()] if vids else []
        return rows

    def performance(self, pid: int) -> list[dict]:
        """Per version: n tests, avg score, avg rating, avg cost/latency."""
        with self.engine.connect() as cx:
            rows = cx.execute(select(prompt_versions.c.id, prompt_versions.c.version, func.count(prompt_tests.c.id), func.avg(prompt_tests.c.score), func.avg(prompt_tests.c.human_rating), func.avg(prompt_tests.c.cost_usd), func.avg(prompt_tests.c.latency_ms))
                              .select_from(prompt_versions.outerjoin(prompt_tests, prompt_tests.c.prompt_version_id == prompt_versions.c.id)).where(prompt_versions.c.prompt_id == pid).group_by(prompt_versions.c.id).order_by(prompt_versions.c.version)).all()
        return [{"version_id": r[0], "version": r[1], "tests": r[2], "avg_score": round(r[3], 1) if r[3] is not None else None, "avg_rating": round(r[4], 2) if r[4] is not None else None,
                 "avg_cost_usd": round(r[5], 5) if r[5] is not None else None, "avg_latency_ms": int(r[6]) if r[6] is not None else None} for r in rows]
