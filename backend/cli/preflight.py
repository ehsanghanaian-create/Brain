"""Pre-flight checks. Prints PASS/WARNING/FAIL per component with reason and fix.

    python scripts/preflight.py [--site emdadmodiran] [--json]
Runs with the system python or the venv python (venv is checked as a component).
"""
import _bootstrap  # noqa: F401
import argparse
import json
import os
import platform
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = _bootstrap.ROOT
RESULTS: list[dict] = []


def add(component: str, status: str, reason: str, fix: str = "") -> None:
    RESULTS.append({"component": component, "status": status, "reason": reason, "fix": fix})


def which(cmd: str) -> str | None:
    return shutil.which(cmd)


def run(cmd: list[str], timeout: int = 20) -> tuple[int, str]:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return p.returncode, (p.stdout or p.stderr).strip()
    except Exception as e:  # noqa: BLE001
        return 1, str(e)


def http_get(url: str, timeout: float = 15.0):
    import httpx
    return httpx.get(url, timeout=timeout, follow_redirects=True, headers={"User-Agent": "SEO-KG-Preflight/0.1"})


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--site", default=None)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--offline", action="store_true", help="skip network checks")
    a = ap.parse_args()

    # OS / CPU
    add("OS", "PASS", f"{platform.system()} {platform.release()} ({platform.version()})")
    add("CPU architecture", "PASS", platform.machine())

    # Python
    v = sys.version_info
    if (3, 11) <= (v.major, v.minor) < (3, 14):
        add("Python", "PASS", f"{platform.python_version()} at {sys.executable}")
    else:
        add("Python", "FAIL" if v < (3, 11) else "WARNING", f"{platform.python_version()} (need >=3.11,<3.14)", "Install Python 3.13 and recreate .venv")
    in_venv = sys.prefix != getattr(sys, "base_prefix", sys.prefix)
    venv_py = ROOT / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if venv_py.exists():
        add("Python venv", "PASS", f"{venv_py} (active={in_venv})")
    else:
        add("Python venv", "FAIL", ".venv missing", "python -m venv .venv && .venv\\Scripts\\pip install -e .[dev]")

    # Python deps
    missing = []
    for mod in ("httpx", "bs4", "lxml", "protego", "networkx", "pydantic", "dotenv", "yaml", "mcp", "googleapiclient", "google_auth_oauthlib", "fastapi", "uvicorn", "rapidfuzz"):
        try:
            __import__(mod)
        except Exception:  # noqa: BLE001
            missing.append(mod)
    if missing:
        add("Python dependencies", "FAIL", f"missing: {', '.join(missing)}", ".venv\\Scripts\\pip install -e .[dev]")
    else:
        add("Python dependencies", "PASS", "all importable")

    # SQLite
    conn = sqlite3.connect(":memory:")
    try:
        conn.execute("CREATE VIRTUAL TABLE t USING fts5(x)")
        add("SQLite", "PASS", f"{sqlite3.sqlite_version} with FTS5")
    except sqlite3.OperationalError:
        add("SQLite", "FAIL", f"{sqlite3.sqlite_version} without FTS5", "Use python.org CPython build (FTS5 included)")

    # Node (informational only)
    node = which("node")
    add("Node.js", "PASS" if node else "WARNING", f"{node or 'not installed'}", "" if node else "Not required by this architecture (Python-only). Install only if adding a Node component.")
    npm = which("npm")
    add("npm", "PASS" if npm else "WARNING", f"{npm or 'not installed'}", "" if npm else "Not required.")

    # Git
    git = which("git")
    if git:
        add("Git", "PASS", run([git, "--version"])[1])
    else:
        add("Git", "FAIL", "git not found", "winget install Git.Git")
    if (ROOT / ".git").exists():
        add("Git repository", "PASS", str(ROOT))
    else:
        add("Git repository", "WARNING", "project not a git repo yet", "git init")

    # Obsidian
    obs_paths = [Path(os.environ.get("LOCALAPPDATA", "")) / "Obsidian" / "Obsidian.exe",
                 Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Obsidian" / "Obsidian.exe"]
    obs = next((p for p in obs_paths if p.exists()), None) or which("obsidian")
    if obs:
        add("Obsidian", "PASS", str(obs))
    else:
        add("Obsidian", "WARNING", "Obsidian not installed", "winget install --id Obsidian.Obsidian -e")
    from seo_brain.common.config import vault_path
    vp = vault_path()
    if vp.exists() and any(vp.iterdir()):
        add("Obsidian vault", "PASS", str(vp))
    else:
        add("Obsidian vault", "WARNING", f"vault folder missing/empty: {vp}", "python scripts/setup.py --vault")
    obs_cfg = Path(os.environ.get("APPDATA", "")) / "obsidian" / "obsidian.json"
    if obs_cfg.exists():
        try:
            data = json.loads(obs_cfg.read_text(encoding="utf-8"))
            registered = any(Path(v.get("path", "")).resolve() == vp.resolve() for v in data.get("vaults", {}).values())
            add("Vault registered in Obsidian", "PASS" if registered else "WARNING", "yes" if registered else "vault not opened in Obsidian yet", "" if registered else "Obsidian -> Open folder as vault -> select the vault path")
        except Exception as e:  # noqa: BLE001
            add("Vault registered in Obsidian", "WARNING", f"cannot read obsidian.json: {e}")
    plugin_dir = vp / ".obsidian" / "plugins"
    for pid, req in (("dataview", "recommended"), ("obsidian-local-rest-api", "optional")):
        if (plugin_dir / pid).exists():
            add(f"Obsidian plugin {pid}", "PASS", "installed in vault")
        else:
            add(f"Obsidian plugin {pid}", "WARNING", f"not installed ({req})", f"Obsidian -> Settings -> Community plugins -> Browse -> {pid}")

    # Claude Desktop
    cd_cfg = Path(os.environ.get("APPDATA", "")) / "Claude" / "claude_desktop_config.json"
    if cd_cfg.exists():
        try:
            cfg = json.loads(cd_cfg.read_text(encoding="utf-8"))
            servers = cfg.get("mcpServers", {})
            if "seo-knowledge-graph" in servers:
                add("Claude Desktop MCP config", "PASS", f"seo-knowledge-graph registered in {cd_cfg}")
            else:
                add("Claude Desktop MCP config", "WARNING", f"config exists, server not registered ({len(servers)} other servers)", "python scripts/setup.py --claude-config")
        except Exception as e:  # noqa: BLE001
            add("Claude Desktop MCP config", "FAIL", f"invalid JSON: {e}", "fix the file syntax")
    else:
        add("Claude Desktop MCP config", "WARNING", f"{cd_cfg} missing", "Install Claude Desktop / run setup.py --claude-config")

    # .env
    envf = ROOT / ".env"
    if envf.exists():
        from seo_brain.common.config import env
        add(".env", "PASS", "present")
        add("WordPress credentials", "PASS" if env("WP_APP_PASSWORD") else "WARNING", "app password set" if env("WP_APP_PASSWORD") else "not set (public read endpoints only)", "add WP_USERNAME/WP_APP_PASSWORD to .env for menus/authors")
        gsc_ok = bool(env("GOOGLE_CLIENT_ID") and env("GOOGLE_CLIENT_SECRET"))
        add("GSC prerequisites", "PASS" if gsc_ok else "FAIL", "OAuth client configured" if gsc_ok else "GOOGLE_CLIENT_ID/SECRET missing", "Create OAuth Desktop client in Google Cloud, enable Search Console API, fill .env")
        from seo_brain.common.config import resolve_path
        tok = resolve_path(env("GSC_TOKEN_PATH", "tokens/gsc_token.json"))
        add("GSC token", "PASS" if tok.exists() else "WARNING", "cached" if tok.exists() else "no token yet (first sync opens browser consent)", "python scripts/sync-gsc.py --auth-only")
    else:
        add(".env", "FAIL", ".env missing", "copy .env.example to .env and fill values")

    # network
    if not a.offline:
        from seo_brain.common.config import get_site
        try:
            site = get_site(a.site)
            add("Site config", "PASS", f"{site.site_id} -> {site.canonical_url}")
        except Exception as e:  # noqa: BLE001
            add("Site config", "FAIL", str(e), "copy config/site.example.yaml to config/site.yaml")
            site = None
        try:
            r = http_get("https://api.github.com/")
            add("GitHub connectivity", "PASS" if r.status_code < 500 else "WARNING", f"api.github.com {r.status_code}")
        except Exception as e:  # noqa: BLE001
            add("GitHub connectivity", "WARNING", str(e))
        if site:
            try:
                r = http_get(site.wp_url.rstrip("/") + "/wp-json/")
                ok = r.status_code == 200 and "wp/v2" in r.text.replace("\\/", "/")
                add("WordPress REST API", "PASS" if ok else "FAIL", f"{site.wp_url}/wp-json/ -> {r.status_code}", "" if ok else "check WP_URL / REST API not disabled")
            except Exception as e:  # noqa: BLE001
                add("WordPress REST API", "FAIL", str(e), "check network / WP_URL")
            try:
                r = http_get(site.canonical_url.rstrip("/") + "/robots.txt")
                add("robots.txt", "PASS" if r.status_code == 200 else "WARNING", f"{r.status_code}")
            except Exception as e:  # noqa: BLE001
                add("robots.txt", "WARNING", str(e))
        try:
            r = http_get("https://www.googleapis.com/discovery/v1/apis/searchconsole/v1/rest")
            add("Google APIs reachable", "PASS" if r.status_code == 200 else "WARNING", f"{r.status_code}")
        except Exception as e:  # noqa: BLE001
            add("Google APIs reachable", "WARNING", str(e))
        try:
            from seo_brain.common.config import env
            url = env("OBSIDIAN_API_URL", "https://127.0.0.1:27124")
            import httpx
            r = httpx.get(url + "/", verify=False, timeout=3)
            add("Obsidian Local REST API", "PASS", f"{url} -> {r.status_code} (optional)")
        except Exception:  # noqa: BLE001
            add("Obsidian Local REST API", "WARNING", "not reachable (optional; only needed for live-Obsidian features)", "enable plugin in Obsidian if wanted")

    # graph engine + mcp deps
    try:
        import networkx  # noqa: F401
        add("Graph engine (networkx)", "PASS", networkx.__version__)
    except Exception as e:  # noqa: BLE001
        add("Graph engine (networkx)", "FAIL", str(e), "pip install networkx")
    try:
        import mcp  # noqa: F401
        from importlib.metadata import version
        add("MCP SDK", "PASS", version("mcp"))
    except Exception as e:  # noqa: BLE001
        add("MCP SDK", "FAIL", str(e), "pip install mcp")

    # database
    from seo_brain.common.config import database_path
    dbp = database_path()
    add("Database", "PASS" if dbp.exists() else "WARNING", str(dbp) if dbp.exists() else f"{dbp} not created yet", "" if dbp.exists() else "run sync-wordpress / crawl")

    if a.json:
        print(json.dumps(RESULTS, ensure_ascii=False, indent=2))
    else:
        w = max(len(r["component"]) for r in RESULTS)
        for r in RESULTS:
            line = f"{r['status']:8s} {r['component']:{w}s}  {r['reason']}"
            if r["fix"] and r["status"] != "PASS":
                line += f"\n{'':8s} {'':{w}s}  fix: {r['fix']}"
            print(line)
        n = {s: sum(1 for r in RESULTS if r["status"] == s) for s in ("PASS", "WARNING", "FAIL")}
        print(f"\nSUMMARY: {n['PASS']} PASS, {n['WARNING']} WARNING, {n['FAIL']} FAIL")
    return 1 if any(r["status"] == "FAIL" for r in RESULTS) else 0


if __name__ == "__main__":
    raise SystemExit(main())
