"""Configuration loading: .env (secrets) + config/site.yaml (per-site settings).

Secrets never leave this module unmasked except through explicit accessor calls
made by connectors. Nothing here writes to disk.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

PROJECT_ROOT = Path(os.environ.get("SEO_KG_ROOT") or Path(__file__).resolve().parents[3])

_ENV_LOADED = False


def load_env() -> None:
    global _ENV_LOADED
    if not _ENV_LOADED:
        load_dotenv(PROJECT_ROOT / ".env", override=False)
        _ENV_LOADED = True


def env(name: str, default: str | None = None) -> str | None:
    load_env()
    v = os.environ.get(name)
    return v if v not in (None, "") else default


def resolve_path(p: str | Path) -> Path:
    p = Path(p)
    return p if p.is_absolute() else (PROJECT_ROOT / p)


@dataclass
class CrawlerConfig:
    max_urls: int = 20
    concurrency: int = 2
    delay_seconds: float = 1.0
    timeout_seconds: float = 20.0
    max_retries: int = 3
    user_agent: str = "SEO-KG-Crawler/0.1 (+local; read-only)"
    respect_robots: bool = True
    allowed_hosts: list[str] = field(default_factory=list)
    exclude_patterns: list[str] = field(default_factory=list)


@dataclass
class GscConfig:
    lookback_days: int = 1
    dimensions: list[str] = field(default_factory=lambda: ["date", "query", "page", "country", "device"])
    row_limit: int = 25000


@dataclass
class GraphConfig:
    important_query_min_impressions: int = 50
    important_query_min_clicks: int = 5
    max_query_nodes: int = 200


@dataclass
class SiteConfig:
    site_id: str
    name: str
    canonical_url: str
    wp_url: str
    language: str = "en"
    gsc_property: str = ""
    crawler: CrawlerConfig = field(default_factory=CrawlerConfig)
    gsc: GscConfig = field(default_factory=GscConfig)
    graph: GraphConfig = field(default_factory=GraphConfig)

    @property
    def host(self) -> str:
        from urllib.parse import urlparse
        return urlparse(self.canonical_url).hostname or ""


def _dc(cls, d: dict[str, Any] | None):
    d = d or {}
    allowed = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
    return cls(**{k: v for k, v in d.items() if k in allowed})


def load_sites(path: str | Path | None = None) -> list[SiteConfig]:
    path = resolve_path(path or "config/site.yaml")
    if not path.exists():
        raise FileNotFoundError(f"site config not found: {path} (copy config/site.example.yaml)")
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    sites = []
    for s in raw.get("sites", []):
        sites.append(
            SiteConfig(
                site_id=s["site_id"],
                name=s.get("name", s["site_id"]),
                canonical_url=s["canonical_url"],
                wp_url=s.get("wp_url", s["canonical_url"].rstrip("/")),
                language=s.get("language", "en"),
                gsc_property=s.get("gsc_property", ""),
                crawler=_dc(CrawlerConfig, s.get("crawler")),
                gsc=_dc(GscConfig, s.get("gsc")),
                graph=_dc(GraphConfig, s.get("graph")),
            )
        )
    if not sites:
        raise ValueError("no sites defined in config")
    return sites


def get_site(site_id: str | None = None) -> SiteConfig:
    sites = load_sites()
    if site_id is None:
        return sites[0]
    for s in sites:
        if s.site_id == site_id:
            return s
    raise KeyError(f"unknown site_id: {site_id}")


def database_path() -> Path:
    return resolve_path(env("DATABASE_PATH", "data/seo.db"))


def raw_data_dir() -> Path:
    return resolve_path(env("RAW_DATA_DIR", "data/raw"))


def vault_path() -> Path:
    return resolve_path(env("OBSIDIAN_VAULT_PATH", "obsidian/SEO-Knowledge-Graph"))


def log_dir() -> Path:
    return resolve_path(env("LOG_DIR", "data/logs"))
