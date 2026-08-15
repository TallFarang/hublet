"""Apple Notes recipe references and cooking experiments."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from html import escape
from typing import Annotated, Any
from uuid import uuid4

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from mcp.server import MCPServer

from app.config import Settings
from app.db import connect
from app.runtime import Plugin

DB_FILENAME = "recipes.db"
MIGRATIONS = (
    """
    CREATE TABLE recipes (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        note_reference TEXT NOT NULL,
        tags_json TEXT NOT NULL DEFAULT '[]',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    CREATE TABLE cook_logs (
        id TEXT PRIMARY KEY,
        recipe_id TEXT NOT NULL REFERENCES recipes(id),
        rating INTEGER NOT NULL CHECK (rating BETWEEN 1 AND 5),
        changes TEXT,
        notes TEXT,
        conclusion TEXT,
        created_at TEXT NOT NULL
    );
    """,
)
router = APIRouter(prefix="/recipes")


def link_recipe(
    settings: Settings, name: str, note_reference: str, tags: list[str] | None = None
) -> dict[str, Any]:
    name = name.strip()
    note_reference = note_reference.strip()
    _validate_recipe(name, note_reference)
    recipe_id = str(uuid4())
    now = _now()
    with connect(settings.data_dir / DB_FILENAME) as connection:
        connection.execute(
            """INSERT INTO recipes
               (id, name, note_reference, tags_json, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (recipe_id, name, note_reference, _tags_json(tags), now, now),
        )
    return get_recipe(settings, recipe_id)


def search(settings: Settings, query: str = "") -> list[dict[str, Any]]:
    sql = "SELECT * FROM recipes"
    parameters: tuple[str, ...] = ()
    if query.strip():
        sql += " WHERE name LIKE ? COLLATE NOCASE OR tags_json LIKE ? COLLATE NOCASE"
        pattern = f"%{query.strip()}%"
        parameters = (pattern, pattern)
    sql += " ORDER BY updated_at DESC, id DESC"
    with connect(settings.data_dir / DB_FILENAME) as connection:
        return [_recipe(row) for row in connection.execute(sql, parameters)]


def get_recipe(settings: Settings, recipe_id: str) -> dict[str, Any]:
    with connect(settings.data_dir / DB_FILENAME) as connection:
        row = connection.execute("SELECT * FROM recipes WHERE id = ?", (recipe_id,)).fetchone()
        logs = connection.execute(
            "SELECT * FROM cook_logs WHERE recipe_id = ? ORDER BY created_at DESC, id DESC",
            (recipe_id,),
        ).fetchall()
    if row is None:
        raise ValueError("Recipe not found")
    result = _recipe(row)
    result["cook_logs"] = [dict(log) for log in logs]
    return result


def update_recipe(
    settings: Settings,
    recipe_id: str,
    *,
    name: str | None = None,
    note_reference: str | None = None,
    tags: list[str] | None = None,
) -> dict[str, Any]:
    current = get_recipe(settings, recipe_id)
    name = current["name"] if name is None else name.strip()
    note_reference = (
        current["note_reference"] if note_reference is None else note_reference.strip()
    )
    _validate_recipe(name, note_reference)
    tag_values = current["tags"] if tags is None else tags
    with connect(settings.data_dir / DB_FILENAME) as connection:
        connection.execute(
            """UPDATE recipes SET name = ?, note_reference = ?, tags_json = ?, updated_at = ?
               WHERE id = ?""",
            (name, note_reference, _tags_json(tag_values), _now(), recipe_id),
        )
    return get_recipe(settings, recipe_id)


def log_cook(
    settings: Settings,
    recipe_id: str,
    *,
    rating: int,
    changes: str | None = None,
    notes: str | None = None,
    conclusion: str | None = None,
) -> dict[str, Any]:
    get_recipe(settings, recipe_id)
    if rating not in range(1, 6):
        raise ValueError("rating must be between 1 and 5")
    log_id = str(uuid4())
    now = _now()
    with connect(settings.data_dir / DB_FILENAME) as connection:
        connection.execute(
            """INSERT INTO cook_logs
               (id, recipe_id, rating, changes, notes, conclusion, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (log_id, recipe_id, rating, changes, notes, conclusion, now),
        )
        connection.execute("UPDATE recipes SET updated_at = ? WHERE id = ?", (now, recipe_id))
        row = connection.execute("SELECT * FROM cook_logs WHERE id = ?", (log_id,)).fetchone()
    return dict(row)


def history(
    settings: Settings, recipe_id: str | None = None, limit: int = 20
) -> list[dict[str, Any]]:
    if limit < 1:
        raise ValueError("limit must be positive")
    sql = """SELECT cook_logs.*, recipes.name AS recipe_name
             FROM cook_logs JOIN recipes ON recipes.id = cook_logs.recipe_id"""
    parameters: list[Any] = []
    if recipe_id is not None:
        get_recipe(settings, recipe_id)
        sql += " WHERE cook_logs.recipe_id = ?"
        parameters.append(recipe_id)
    sql += " ORDER BY cook_logs.created_at DESC, cook_logs.id DESC LIMIT ?"
    parameters.append(min(limit, 100))
    with connect(settings.data_dir / DB_FILENAME) as connection:
        return [dict(row) for row in connection.execute(sql, parameters)]


def register_mcp(server: MCPServer, settings: Settings) -> None:
    def link_tool(
        name: str, note_reference: str, tags: list[str] | None = None
    ) -> dict[str, Any]:
        """Link a recipe to its canonical Apple Note."""
        return link_recipe(settings, name, note_reference, tags)

    def search_tool(query: str = "") -> list[dict[str, Any]]:
        """Search linked recipes by name or tag."""
        return search(settings, query)

    def get_tool(recipe_id: str) -> dict[str, Any]:
        """Get a recipe reference and its cooking experiments."""
        return get_recipe(settings, recipe_id)

    def log_tool(
        recipe_id: str,
        rating: int,
        changes: str | None = None,
        notes: str | None = None,
        conclusion: str | None = None,
    ) -> dict[str, Any]:
        """Log what changed, how it scored and what was learned."""
        return log_cook(
            settings,
            recipe_id,
            rating=rating,
            changes=changes,
            notes=notes,
            conclusion=conclusion,
        )

    def history_tool(
        recipe_id: str | None = None, limit: int = 20
    ) -> list[dict[str, Any]]:
        """Return recent cooking experiments."""
        return history(settings, recipe_id, limit)

    server.add_tool(link_tool, name="recipes.link")
    server.add_tool(search_tool, name="recipes.search")
    server.add_tool(get_tool, name="recipes.get")
    server.add_tool(log_tool, name="recipes.log_cook")
    server.add_tool(history_tool, name="recipes.history")


@router.get("", response_class=HTMLResponse)
def recipes_page(request: Request) -> str:
    settings = request.app.state.settings
    records = [get_recipe(settings, recipe["id"]) for recipe in search(settings)]
    rows = "".join(_recipe_html(recipe) for recipe in records)
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
    <title>Recipes · Hublet</title></head><body><main><a href="/">Hublet</a><h1>Recipes</h1>
    <p>Recipe content stays in Apple Notes. Hublet remembers experiments.</p>
    <ul>{rows or '<li>No linked recipes.</li>'}</ul>
    <form method="post" action="/recipes"><h2>Link a recipe</h2>
    <label>Name <input name="name" required></label>
    <label>Note reference <input name="note_reference" required></label>
    <label>Tags <input name="tags"></label><button>Link</button></form>
    </main></body></html>"""


@router.post("")
def link_form(
    request: Request,
    name: Annotated[str, Form()],
    note_reference: Annotated[str, Form()],
    tags: Annotated[str, Form()] = "",
) -> RedirectResponse:
    link_recipe(request.app.state.settings, name, note_reference, tags.split(","))
    return RedirectResponse("/recipes", status_code=303)


@router.post("/{recipe_id}/edit")
def edit_form(
    request: Request,
    recipe_id: str,
    name: Annotated[str, Form()],
    note_reference: Annotated[str, Form()],
    tags: Annotated[str, Form()] = "",
) -> RedirectResponse:
    update_recipe(
        request.app.state.settings,
        recipe_id,
        name=name,
        note_reference=note_reference,
        tags=tags.split(","),
    )
    return RedirectResponse("/recipes", status_code=303)


@router.post("/{recipe_id}/cooks")
def cook_form(
    request: Request,
    recipe_id: str,
    rating: Annotated[int, Form()],
    changes: Annotated[str, Form()] = "",
    notes: Annotated[str, Form()] = "",
    conclusion: Annotated[str, Form()] = "",
) -> RedirectResponse:
    log_cook(
        request.app.state.settings,
        recipe_id,
        rating=rating,
        changes=changes or None,
        notes=notes or None,
        conclusion=conclusion or None,
    )
    return RedirectResponse("/recipes", status_code=303)


def launcher_summary(settings: Settings) -> str:
    with connect(settings.data_dir / DB_FILENAME) as connection:
        count = connection.execute("SELECT COUNT(*) FROM cook_logs").fetchone()[0]
    return f"{count} {'cook' if count == 1 else 'cooks'}"


def _recipe_html(recipe: dict[str, Any]) -> str:
    cook_rows = "".join(
        f"""<li><strong>{log['rating']}/5</strong>
        <div>Changes: {escape(log['changes'] or '—')}</div>
        <div>Notes: {escape(log['notes'] or '—')}</div>
        <div>Conclusion: {escape(log['conclusion'] or '—')}</div></li>"""
        for log in recipe["cook_logs"]
    )
    return f"""<li><details><summary><strong>{escape(recipe['name'])}</strong> —
    {escape(', '.join(recipe['tags']))}</summary>
    <p><code>{escape(recipe['note_reference'])}</code></p>
    <form method="post" action="/recipes/{recipe['id']}/edit">
    <label>Name <input name="name" value="{_value(recipe, 'name')}" required></label>
    <label>Note reference <input name="note_reference"
    value="{_value(recipe, 'note_reference')}" required></label>
    <label>Tags <input name="tags" value="{escape(', '.join(recipe['tags']), quote=True)}">
    </label><button>Save</button></form>
    <form method="post" action="/recipes/{recipe['id']}/cooks">
    <label>Rating <input name="rating" type="number" min="1" max="5" required></label>
    <label>Changes <textarea name="changes"></textarea></label>
    <label>Notes <textarea name="notes"></textarea></label>
    <label>Conclusion <textarea name="conclusion"></textarea></label>
    <button>Log cook</button></form>
    <h3>Cook history</h3><ul>{cook_rows or '<li>Nothing cooked yet.</li>'}</ul>
    </details></li>"""


def _validate_recipe(name: str, note_reference: str) -> None:
    if not name:
        raise ValueError("name is required")
    if not note_reference:
        raise ValueError("note_reference is required")


def _tags_json(tags: list[str] | None) -> str:
    clean = [tag.strip() for tag in (tags or []) if tag.strip()]
    return json.dumps(clean, separators=(",", ":"))


def _recipe(row: Any) -> dict[str, Any]:
    result = dict(row)
    result["tags"] = json.loads(result.pop("tags_json"))
    return result


def _value(record: dict[str, Any], key: str) -> str:
    return escape(record[key] or "", quote=True)


def _now() -> str:
    return datetime.now(UTC).isoformat()


PLUGIN = Plugin(
    name="recipes",
    icon="◇",
    db_filename=DB_FILENAME,
    migrations=MIGRATIONS,
    register_mcp=register_mcp,
    router=router,
    launcher_summary=launcher_summary,
)
