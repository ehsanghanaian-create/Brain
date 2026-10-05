"""Project membership is an authorization boundary for analyst mutations."""
from fastapi import HTTPException, Request
from sqlalchemy import text


def project_responsibility(cx, request: Request, site_id: str) -> str:
    actor = getattr(request.state, "panel_user", None)
    if actor is None or actor["role"] == "admin":
        return "admin"
    row = cx.execute(text("""SELECT responsibility FROM site_assignments
        WHERE site_id=:site AND user_id=:user"""),
        {"site": site_id, "user": actor["id"]}).scalar_one_or_none()
    return row or "none"


def require_lead(cx, request: Request, site_id: str) -> None:
    if project_responsibility(cx, request, site_id) not in ("admin", "lead"):
        raise HTTPException(403, "project lead access is required")


def require_assignee(cx, request: Request, site_id: str, owner_id: int | None) -> None:
    responsibility = project_responsibility(cx, request, site_id)
    actor = getattr(request.state, "panel_user", None)
    if responsibility in ("admin", "lead"):
        return
    if responsibility != "contributor" or not actor or owner_id != actor["id"]:
        raise HTTPException(403, "only the assigned project contributor may update this work")
