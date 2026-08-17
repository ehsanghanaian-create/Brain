from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from sqlalchemy import select

from ..tables import sites
from .base import Repository, utcnow

MODES = ("manual", "assisted", "autopilot")


@dataclass
class Site:
    site_id: str
    name: str
    canonical_url: str
    wp_url: str | None = None
    language: str | None = None
    gsc_property: str | None = None
    business_type: str | None = None
    country: str | None = None
    mode: str = "manual"
    ga4_property: str | None = None
    workspace_path: str | None = None
    timezone: str | None = None
    created_at: str | None = None
    updated_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _row_to_site(r) -> Site:
    return Site(**{k: r._mapping[k] for k in Site.__dataclass_fields__ if k in r._mapping})


class SitesRepository(Repository):
    def list(self) -> list[Site]:
        with self.engine.connect() as cx:
            return [_row_to_site(r) for r in cx.execute(select(sites).order_by(sites.c.site_id))]

    def get(self, site_id: str) -> Site | None:
        with self.engine.connect() as cx:
            r = cx.execute(select(sites).where(sites.c.site_id == site_id)).first()
            return _row_to_site(r) if r else None

    def save(self, site: Site) -> Site:
        if site.mode not in MODES:
            raise ValueError(f"mode must be one of {MODES}")
        now = utcnow()
        values = {k: v for k, v in site.to_dict().items() if k not in ("created_at", "updated_at")}
        values["created_at"] = site.created_at or now
        values["updated_at"] = now
        with self.engine.begin() as cx:
            self.upsert(cx, sites, values, conflict=["site_id"],
                        update=[k for k in values if k not in ("site_id", "created_at")])
        return self.get(site.site_id)  # type: ignore[return-value]

    def set_fields(self, site_id: str, **fields) -> Site:
        """Targeted UPDATE of specific columns (safe under concurrent requests — no full-row overwrite)."""
        allowed = {k: v for k, v in fields.items() if k in Site.__dataclass_fields__ and k not in ("site_id", "created_at", "updated_at")}
        if "mode" in allowed and allowed["mode"] not in MODES:
            raise ValueError(f"mode must be one of {MODES}")
        if allowed:
            with self.engine.begin() as cx:
                cx.execute(sites.update().where(sites.c.site_id == site_id).values(**allowed, updated_at=utcnow()))
        s = self.get(site_id)
        if not s:
            raise KeyError(site_id)
        return s

    def set_mode(self, site_id: str, mode: str) -> Site:
        if mode not in MODES:
            raise ValueError(f"mode must be one of {MODES}")
        with self.engine.begin() as cx:
            cx.execute(sites.update().where(sites.c.site_id == site_id).values(mode=mode, updated_at=utcnow()))
        s = self.get(site_id)
        if not s:
            raise KeyError(site_id)
        return s
