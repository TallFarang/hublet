"""Durable goals with absolute progress measurements."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any
from uuid import uuid4

from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse, Response
from mcp.server import MCPServer

from app.config import Settings
from app.db import connect
from app.runtime import Plugin
from app.web import render

DB_FILENAME = "goals.db"
MIGRATIONS = (
    """
    CREATE TABLE goals (
        id TEXT PRIMARY KEY,
        title TEXT NOT NULL,
        description TEXT,
        status TEXT NOT NULL DEFAULT 'active'
            CHECK (status IN ('active', 'completed', 'archived')),
        target_value REAL,
        unit TEXT,
        target_date TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    CREATE TABLE entries (
        id TEXT PRIMARY KEY,
        goal_id TEXT NOT NULL REFERENCES goals(id),
        value REAL NOT NULL,
        note TEXT,
        created_at TEXT NOT NULL
    );
    """,
)
router = APIRouter(prefix="/goals")


def create_goal(
    settings: Settings,
    title: str,
    description: str | None = None,
    target_value: float | None = None,
    unit: str | None = None,
    target_date: str | None = None,
) -> dict[str, Any]:
    title = title.strip()
    if not title:
        raise ValueError("title is required")
    goal_id = str(uuid4())
    now = _now()
    with connect(settings.data_dir / DB_FILENAME) as connection:
        connection.execute(
            """INSERT INTO goals
               (id, title, description, status, target_value, unit, target_date,
                created_at, updated_at)
               VALUES (?, ?, ?, 'active', ?, ?, ?, ?, ?)""",
            (goal_id, title, description, target_value, unit, target_date, now, now),
        )
    return get_goal(settings, goal_id)


def list_goals(
    settings: Settings, status: str | None = "active"
) -> list[dict[str, Any]]:
    _validate_status(status)
    query = """SELECT goals.*,
               (SELECT value FROM entries WHERE goal_id = goals.id
                ORDER BY created_at DESC, id DESC LIMIT 1) AS current_value,
               (SELECT created_at FROM entries WHERE goal_id = goals.id
                ORDER BY created_at DESC, id DESC LIMIT 1) AS current_entry_at
               FROM goals"""
    parameters: tuple[str, ...] = ()
    if status is not None:
        query += " WHERE status = ?"
        parameters = (status,)
    query += " ORDER BY updated_at DESC, id DESC"
    with connect(settings.data_dir / DB_FILENAME) as connection:
        return [dict(row) for row in connection.execute(query, parameters)]


def get_goal(settings: Settings, goal_id: str) -> dict[str, Any]:
    with connect(settings.data_dir / DB_FILENAME) as connection:
        row = connection.execute(
            """SELECT goals.*,
               (SELECT value FROM entries WHERE goal_id = goals.id
                ORDER BY created_at DESC, id DESC LIMIT 1) AS current_value,
               (SELECT created_at FROM entries WHERE goal_id = goals.id
                ORDER BY created_at DESC, id DESC LIMIT 1) AS current_entry_at
               FROM goals WHERE id = ?""",
            (goal_id,),
        ).fetchone()
        entries = connection.execute(
            "SELECT * FROM entries WHERE goal_id = ? ORDER BY created_at DESC, id DESC",
            (goal_id,),
        ).fetchall()
    if row is None:
        raise ValueError("Goal not found")
    result = dict(row)
    result["entries"] = [dict(entry) for entry in entries]
    return result


def log_progress(
    settings: Settings, goal_id: str, value: float, note: str | None = None
) -> dict[str, Any]:
    get_goal(settings, goal_id)
    entry_id = str(uuid4())
    now = _now()
    with connect(settings.data_dir / DB_FILENAME) as connection:
        connection.execute(
            "INSERT INTO entries (id, goal_id, value, note, created_at) VALUES (?, ?, ?, ?, ?)",
            (entry_id, goal_id, value, note, now),
        )
        connection.execute("UPDATE goals SET updated_at = ? WHERE id = ?", (now, goal_id))
        row = connection.execute("SELECT * FROM entries WHERE id = ?", (entry_id,)).fetchone()
    return dict(row)


def update_goal(
    settings: Settings,
    goal_id: str,
    *,
    title: str | None = None,
    description: str | None = None,
    target_value: float | None = None,
    unit: str | None = None,
    target_date: str | None = None,
    clear_target: bool = False,
) -> dict[str, Any]:
    changes = {
        key: value
        for key, value in {
            "title": title.strip() if title is not None else None,
            "description": description,
            "target_value": target_value,
            "unit": unit,
            "target_date": target_date,
        }.items()
        if value is not None
    }
    if clear_target:
        changes["target_value"] = None
    if "title" in changes and not changes["title"]:
        raise ValueError("title is required")
    get_goal(settings, goal_id)
    if changes:
        changes["updated_at"] = _now()
        assignments = ", ".join(f"{column} = ?" for column in changes)
        with connect(settings.data_dir / DB_FILENAME) as connection:
            connection.execute(
                f"UPDATE goals SET {assignments} WHERE id = ?",
                (*changes.values(), goal_id),
            )
    return get_goal(settings, goal_id)


def set_status(settings: Settings, goal_id: str, status: str) -> dict[str, Any]:
    _validate_status(status, allow_none=False)
    get_goal(settings, goal_id)
    with connect(settings.data_dir / DB_FILENAME) as connection:
        connection.execute(
            "UPDATE goals SET status = ?, updated_at = ? WHERE id = ?",
            (status, _now(), goal_id),
        )
    return get_goal(settings, goal_id)


def register_mcp(server: MCPServer, settings: Settings) -> None:
    def create_tool(
        title: str,
        description: str | None = None,
        target_value: float | None = None,
        unit: str | None = None,
        target_date: str | None = None,
        clear_target: bool = False,
    ) -> dict[str, Any]:
        """Create a durable goal."""
        return create_goal(settings, title, description, target_value, unit, target_date)

    def list_tool(status: str | None = "active") -> list[dict[str, Any]]:
        """List goals with their newest absolute measurements."""
        return list_goals(settings, status)

    def get_tool(goal_id: str) -> dict[str, Any]:
        """Get one goal and its progress history."""
        return get_goal(settings, goal_id)

    def progress_tool(goal_id: str, value: float, note: str | None = None) -> dict[str, Any]:
        """Log an absolute progress measurement, never a delta."""
        return log_progress(settings, goal_id, value, note)

    def update_tool(
        goal_id: str,
        title: str | None = None,
        description: str | None = None,
        target_value: float | None = None,
        unit: str | None = None,
        target_date: str | None = None,
        clear_target: bool = False,
    ) -> dict[str, Any]:
        """Edit a goal's target or description."""
        return update_goal(
            settings,
            goal_id,
            title=title,
            description=description,
            target_value=target_value,
            unit=unit,
            target_date=target_date,
            clear_target=clear_target,
        )

    def status_tool(goal_id: str, status: str) -> dict[str, Any]:
        """Complete, archive or reactivate a goal."""
        return set_status(settings, goal_id, status)

    server.add_tool(create_tool, name="goals.create")
    server.add_tool(list_tool, name="goals.list")
    server.add_tool(get_tool, name="goals.get")
    server.add_tool(progress_tool, name="goals.log_progress")
    server.add_tool(update_tool, name="goals.update")
    server.add_tool(status_tool, name="goals.status")


@router.get("")
def goals_page(request: Request) -> Response:
    records = list_goals(request.app.state.settings)
    return render(request, "goals.html", title="Goals", goals=records)


@router.post("")
def create_goal_form(
    request: Request,
    title: Annotated[str, Form()],
    description: Annotated[str, Form()] = "",
    target_value: Annotated[float | None, Form()] = None,
    unit: Annotated[str, Form()] = "",
    target_date: Annotated[str, Form()] = "",
) -> RedirectResponse:
    create_goal(
        request.app.state.settings,
        title,
        description or None,
        target_value,
        unit or None,
        target_date or None,
    )
    return RedirectResponse("/goals", status_code=303)


@router.post("/{goal_id}/edit")
def edit_goal_form(
    request: Request,
    goal_id: str,
    title: Annotated[str, Form()],
    description: Annotated[str, Form()] = "",
    target_value: Annotated[float | None, Form()] = None,
    unit: Annotated[str, Form()] = "",
    target_date: Annotated[str, Form()] = "",
) -> RedirectResponse:
    update_goal(
        request.app.state.settings,
        goal_id,
        title=title,
        description=description,
        target_value=target_value,
        unit=unit,
        target_date=target_date,
        clear_target=target_value is None,
    )
    return RedirectResponse("/goals", status_code=303)


@router.post("/{goal_id}/progress")
def progress_form(
    request: Request,
    goal_id: str,
    value: Annotated[float, Form()],
    note: Annotated[str, Form()] = "",
) -> RedirectResponse:
    log_progress(request.app.state.settings, goal_id, value, note or None)
    return RedirectResponse("/goals", status_code=303)


@router.post("/{goal_id}/status")
def status_form(
    request: Request, goal_id: str, status: Annotated[str, Form()]
) -> RedirectResponse:
    set_status(request.app.state.settings, goal_id, status)
    return RedirectResponse("/goals", status_code=303)


def launcher_summary(settings: Settings) -> str:
    count = len(list_goals(settings))
    return f"{count} active {'goal' if count == 1 else 'goals'}"


def _validate_status(status: str | None, allow_none: bool = True) -> None:
    if status is None and allow_none:
        return
    if status not in {"active", "completed", "archived"}:
        raise ValueError("status must be active, completed or archived")


def _now() -> str:
    return datetime.now(UTC).isoformat()


PLUGIN = Plugin(
    name="goals",
    icon="goals",
    db_filename=DB_FILENAME,
    migrations=MIGRATIONS,
    register_mcp=register_mcp,
    router=router,
    launcher_summary=launcher_summary,
)
