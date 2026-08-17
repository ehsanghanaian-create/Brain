"""Setup helper (idempotent, checks before acting).

    python scripts/setup.py --vault            # create/verify Obsidian vault structure
    python scripts/setup.py --env              # create .env from .env.example if missing
    python scripts/setup.py --db               # create SQLite schema
    python scripts/setup.py --claude-config    # register MCP server in Claude Desktop (backs up config first)
    python scripts/setup.py --all
"""
import _bootstrap  # noqa: F401
import argparse
import json
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path

ROOT = _bootstrap.ROOT
SERVER_NAME = "seo-knowledge-graph"


def do_env() -> None:
    envf = ROOT / ".env"
    if envf.exists():
        print(".env exists — leaving untouched")
    else:
        shutil.copy(ROOT / ".env.example", envf)
        print("created .env from .env.example — fill in credentials")


def do_vault() -> None:
    from seo_brain.common.config import vault_path
    from seo_brain.graph.vault import ensure_vault
    res = ensure_vault(vault_path())
    print(json.dumps(res, ensure_ascii=False, indent=2))


def do_db() -> None:
    from seo_brain.database.db import db
    from seo_brain.common.config import database_path
    with db() as conn:
        n = conn.execute("SELECT count(*) FROM sqlite_master WHERE type='table'").fetchone()[0]
    print(f"database ready: {database_path()} ({n} tables)")


def do_claude_config(dry_run: bool = False) -> None:
    cfg_path = Path(os.environ.get("APPDATA", "")) / "Claude" / "claude_desktop_config.json"
    py = ROOT / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    server_entry = {
        "command": str(py),
        "args": [str(ROOT / "backend" / "mcp_server" / "server.py")],
        "env": {"SEO_KG_ROOT": str(ROOT), "PYTHONUTF8": "1"},
    }
    if cfg_path.exists():
        raw = cfg_path.read_text(encoding="utf-8")
        cfg = json.loads(raw) if raw.strip() else {}
        backup = cfg_path.with_name(f"claude_desktop_config.backup-{datetime.now():%Y%m%d-%H%M%S}.json")
        if not dry_run:
            shutil.copy(cfg_path, backup)
            print(f"backup written: {backup}")
    else:
        cfg = {}
        cfg_path.parent.mkdir(parents=True, exist_ok=True)
    servers = cfg.setdefault("mcpServers", {})
    existing = {k: v for k, v in servers.items() if k != SERVER_NAME}
    print(f"existing MCP servers preserved: {list(existing) or 'none'}")
    servers[SERVER_NAME] = server_entry
    if dry_run:
        print(json.dumps({"mcpServers": {SERVER_NAME: server_entry}}, indent=2))
        return
    cfg_path.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"updated {cfg_path}\nRestart Claude Desktop completely (quit from tray) to load '{SERVER_NAME}'.")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--env", action="store_true")
    ap.add_argument("--vault", action="store_true")
    ap.add_argument("--db", action="store_true")
    ap.add_argument("--claude-config", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--all", action="store_true")
    a = ap.parse_args()
    if not any([a.env, a.vault, a.db, a.claude_config, a.all]):
        ap.print_help()
        return 1
    if a.env or a.all:
        do_env()
    if a.vault or a.all:
        do_vault()
    if a.db or a.all:
        do_db()
    if a.claude_config or a.all:
        do_claude_config(dry_run=a.dry_run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
