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


def require_task_editor(cx, request: Request, site_id: str, item: dict) -> None:
    """An assigned task belongs to its assignee; an unassigned draft to its creator.

    Project leads may recover old unowned records without a recorded creator. A
    lead or administrator does not implicitly gain control of somebody else's
    task simply by opening the shared project board.
    """
    actor = getattr(request.state, "panel_user", None)
    if actor is None:  # Existing trusted local integrations have no panel session.
        return
    responsibility = project_responsibility(cx, request, site_id)
    if responsibility == "none":
        raise HTTPException(403, "project membership is required")
    editor_id = item["owner_id"] if item["owner_id"] is not None else item["created_by_id"]
    if editor_id is not None and editor_id != actor["id"]:
        raise HTTPException(403, "this task is read-only for other project members")
    if editor_id is None and responsibility not in ("admin", "lead"):
        raise HTTPException(403, "only a project lead may manage unowned legacy work")


def require_task_commenter(cx, request: Request, site_id: str) -> None:
    if project_responsibility(cx, request, site_id) == "none":
        raise HTTPException(403, "project membership is required to comment")
