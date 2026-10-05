"""Provision the first administrator locally; never prints the generated password."""
from __future__ import annotations

import _bootstrap  # noqa: F401
from pathlib import Path
import secrets

from sqlalchemy import text

from seo_brain.api.panel_auth import hash_password, utcnow
from seo_brain.db.engine import get_engine
from seo_brain.db.migrate import migrate


def main() -> None:
    eng = get_engine()
    migrate(eng)
    username = "admin"
    password = secrets.token_urlsafe(24)
    with eng.begin() as cx:
        if cx.execute(text("SELECT 1 FROM panel_users WHERE password_hash IS NOT NULL AND role='admin' LIMIT 1")).first():
            print("An administrator account already exists; no change made.")
            return
        row = cx.execute(text("SELECT id FROM panel_users WHERE username=:username"), {"username": username}).first()
        if row:
            raise RuntimeError("Username admin already exists without a usable password; resolve manually")
        at = utcnow()
        cx.execute(text("""INSERT INTO panel_users(full_name,email,username,password_hash,role,active,created_at,updated_at)
            VALUES ('Administrator','admin@local.invalid',:username,:password,'admin',1,:at,:at)"""),
            {"username": username, "password": hash_password(password), "at": at})
    path = Path("data/panel-initial-admin.txt").resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"username: {username}\npassword: {password}\nChange the password after first login.\n", encoding="utf-8")
    print(f"Initial credentials saved to {path}")


if __name__ == "__main__":
    main()
