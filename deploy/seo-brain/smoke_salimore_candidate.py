"""Smoke-test an isolated Salimore SEO Brain candidate without printing credentials."""
from __future__ import annotations

import argparse
from http.cookiejar import CookieJar
import json
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import HTTPCookieProcessor, Request, build_opener


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:3110")
    parser.add_argument("--credential-file", required=True, type=Path)
    args = parser.parse_args()
    credentials = dict(
        line.split(": ", 1) for line in args.credential_file.read_text(encoding="utf-8").splitlines()
        if ": " in line
    )
    opener = build_opener(HTTPCookieProcessor(CookieJar()))
    base = args.base_url.rstrip("/")

    def request(path: str, method: str = "GET", body: dict | None = None) -> tuple[int, bytes]:
        payload = json.dumps(body).encode() if body is not None else None
        headers = {"Content-Type": "application/json"} if body is not None else {}
        req = Request(base + path, data=payload, headers=headers, method=method)
        try:
            with opener.open(req, timeout=15) as response:
                return response.status, response.read()
        except HTTPError as exc:
            return exc.code, exc.read()

    status, _ = request("/api/backend/auth/me")
    assert status == 401, f"anonymous API access: {status}"
    print("anonymous API access: 401")

    status, content = request(
        "/api/backend/auth/login", "POST",
        {"username": credentials["username"], "password": credentials["password"]},
    )
    assert status == 200, f"login: {status} {content[:200]!r}"
    assert json.loads(content)["user"]["role"] == "admin"
    print("candidate admin login: 200")

    for path in (
        "/api/backend/auth/me",
        "/api/backend/sites",
        "/api/backend/work/team-management",
        "/api/backend/work/team-management/tasks",
        "/dashboard/team-management",
    ):
        status, content = request(path)
        assert status == 200, f"{path}: {status} {content[:200]!r}"
        print(f"{path}: 200")

    status, _ = request("/api/backend/auth/logout", "POST")
    assert status == 200, f"logout: {status}"
    status, _ = request("/api/backend/auth/me")
    assert status == 401, f"revoked session: {status}"
    print("logout and session revocation: passed")


if __name__ == "__main__":
    main()
