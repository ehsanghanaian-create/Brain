"""Structured (JSON lines) logging with run IDs and secret masking."""
from __future__ import annotations

import json
import logging
import os
import re
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .config import env, log_dir

_SECRET_ENV_KEYS = ("WP_APP_PASSWORD", "GOOGLE_CLIENT_SECRET", "OBSIDIAN_API_KEY", "GOOGLE_CLIENT_ID")
_SECRET_PATTERNS = [
    re.compile(r"(Authorization:\s*)(Basic|Bearer)\s+\S+", re.I),
    re.compile(r"(client_secret[\"']?\s*[:=]\s*[\"']?)([^\"',\s]+)", re.I),
    re.compile(r"(refresh_token[\"']?\s*[:=]\s*[\"']?)([^\"',\s]+)", re.I),
    re.compile(r"(access_token[\"']?\s*[:=]\s*[\"']?)([^\"',\s]+)", re.I),
    re.compile(r"(api[_-]?key[\"']?\s*[:=]\s*[\"']?)([^\"',\s]+)", re.I),
]


def mask_secrets(text: str) -> str:
    if not text:
        return text
    for key in _SECRET_ENV_KEYS:
        val = os.environ.get(key)
        if val and len(val) >= 4 and val in text:
            text = text.replace(val, "***MASKED***")
    for pat in _SECRET_PATTERNS:
        text = pat.sub(lambda m: m.group(1) + ("" if m.lastindex == 1 else "") + "***MASKED***", text)
    return text


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "run_id": getattr(record, "run_id", None) or CURRENT_RUN.get("run_id"),
            "msg": mask_secrets(record.getMessage()),
        }
        for k in ("api", "endpoint", "status", "retry", "final_state", "url", "site_id", "count"):
            if hasattr(record, k):
                payload[k] = getattr(record, k)
        if record.exc_info:
            payload["exc"] = mask_secrets(self.formatException(record.exc_info))
        return json.dumps(payload, ensure_ascii=False)


class HumanFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        rid = getattr(record, "run_id", None) or CURRENT_RUN.get("run_id") or "-"
        base = f"{datetime.now().strftime('%H:%M:%S')} {record.levelname:8s} [{rid}] {record.name}: {mask_secrets(record.getMessage())}"
        if record.exc_info:
            base += "\n" + mask_secrets(self.formatException(record.exc_info))
        return base


CURRENT_RUN: dict[str, str | None] = {"run_id": None}


def new_run_id(prefix: str) -> str:
    rid = f"{prefix}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:6]}"
    CURRENT_RUN["run_id"] = rid
    return rid


def setup_logging(name: str = "seo-kg", level: str | None = None, to_file: bool = True, stream=None) -> logging.Logger:
    """Configure root logging. `stream` defaults to stderr (required for MCP stdio servers)."""
    level = (level or env("LOG_LEVEL", "INFO") or "INFO").upper()
    root = logging.getLogger()
    root.setLevel(level)
    for h in list(root.handlers):
        root.removeHandler(h)
    sh = logging.StreamHandler(stream or sys.stderr)
    sh.setFormatter(HumanFormatter())
    root.addHandler(sh)
    if to_file:
        d: Path = log_dir()
        d.mkdir(parents=True, exist_ok=True)
        fh = logging.FileHandler(d / f"{name}.jsonl", encoding="utf-8")
        fh.setFormatter(JsonFormatter())
        root.addHandler(fh)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("googleapiclient.discovery_cache").setLevel(logging.ERROR)
    return logging.getLogger(name)
