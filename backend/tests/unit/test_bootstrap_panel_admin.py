"""The first administrator must be able to use the manager's command center."""
from __future__ import annotations

import os
from pathlib import Path
import sqlite3
import subprocess
import sys


def test_bootstrap_grants_superadmin_to_first_administrator(tmp_path):
    root = Path(__file__).resolve().parents[3]
    database = tmp_path / "seo.db"
    env = {**os.environ, "SEO_KG_ROOT": str(root), "DATABASE_PATH": str(database)}
    result = subprocess.run(
        [sys.executable, str(root / "backend" / "cli" / "bootstrap_panel_admin.py")],
        cwd=tmp_path, env=env, capture_output=True, text=True, check=True,
    )
    assert "Initial credentials saved" in result.stdout
    with sqlite3.connect(database) as connection:
        assert connection.execute(
            "SELECT username, role, is_superadmin FROM panel_users"
        ).fetchall() == [("admin", "admin", 1)]
    assert (tmp_path / "data" / "panel-initial-admin.txt").is_file()
