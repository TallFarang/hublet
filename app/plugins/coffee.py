"""Coffee records and conservative dial-in recommendations."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Request
from fastapi.responses import Response
from mcp.server import MCPServer

from app.config import Settings
from app.dashboard import coffee_dashboard
from app.db import connect
from app.runtime import Plugin
from app.web import dashboard_period, render

DB_FILENAME = "coffee.db"
MIGRATIONS = (
    """
    CREATE TABLE beans (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        roaster TEXT,
        roast_date TEXT,
        origin TEXT,
        process TEXT,
        status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'archived')),
        notes TEXT,
        created_at TEXT NOT NULL
    );
    CREATE TABLE shots (
        id TEXT PRIMARY KEY,
        bean_id TEXT NOT NULL REFERENCES beans(id),
        dose_g REAL NOT NULL CHECK (dose_g > 0),
        yield_g REAL NOT NULL CHECK (yield_g > 0),
        time_s REAL NOT NULL CHECK (time_s > 0),
        grind_setting TEXT NOT NULL,
        grinder TEXT,
        temperature_c REAL,
        rating INTEGER CHECK (rating BETWEEN 1 AND 5),
        taste_tags_json TEXT NOT NULL DEFAULT '[]',
        notes TEXT,
        created_at TEXT NOT NULL
    );
    """,
)
router = APIRouter(prefix="/coffee")


def add_bean(
    settings: Settings,
    name: str,
    roaster: str | None = None,
    roast_date: str | None = None,
    origin: str | None = None,
    process: str | None = None,
    status: str = "open",
    notes: str | None = None,
) -> dict[str, Any]:
    name = name.strip()
    _validate_bean(name, status)
    bean_id = str(uuid4())
    with connect(settings.data_dir / DB_FILENAME) as connection:
        connection.execute(
            """INSERT INTO beans
               (id, name, roaster, roast_date, origin, process, status, notes, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (bean_id, name, roaster, roast_date, origin, process, status, notes, _now()),
        )
    return get_bean(settings, bean_id)


def get_bean(settings: Settings, bean_id: str) -> dict[str, Any]:
    with connect(settings.data_dir / DB_FILENAME) as connection:
        row = connection.execute("SELECT * FROM beans WHERE id = ?", (bean_id,)).fetchone()
    if row is None:
        raise ValueError("Bean not found")
    return dict(row)


def list_beans(settings: Settings, status: str | None = "open") -> list[dict[str, Any]]:
    if status is not None and status not in {"open", "archived"}:
        raise ValueError("status must be open or archived")
    query = "SELECT * FROM beans"
    parameters: tuple[str, ...] = ()
    if status is not None:
        query += " WHERE status = ?"
        parameters = (status,)
    query += " ORDER BY created_at DESC, id DESC"
    with connect(settings.data_dir / DB_FILENAME) as connection:
        return [dict(row) for row in connection.execute(query, parameters)]


def update_bean(
    settings: Settings,
    bean_id: str,
    *,
    name: str | None = None,
    roaster: str | None = None,
    roast_date: str | None = None,
    origin: str | None = None,
    process: str | None = None,
    status: str | None = None,
    notes: str | None = None,
) -> dict[str, Any]:
    changes = {
        key: value
        for key, value in {
            "name": name.strip() if name is not None else None,
            "roaster": roaster,
            "roast_date": roast_date,
            "origin": origin,
            "process": process,
            "status": status,
            "notes": notes,
        }.items()
        if value is not None
    }
    if "name" in changes and not changes["name"]:
        raise ValueError("name is required")
    if status is not None and status not in {"open", "archived"}:
        raise ValueError("status must be open or archived")
    get_bean(settings, bean_id)
    if changes:
        assignments = ", ".join(f"{column} = ?" for column in changes)
        with connect(settings.data_dir / DB_FILENAME) as connection:
            connection.execute(
                f"UPDATE beans SET {assignments} WHERE id = ?",
                (*changes.values(), bean_id),
            )
    return get_bean(settings, bean_id)


def log_shot(
    settings: Settings,
    bean_id: str,
    *,
    dose_g: float,
    yield_g: float,
    time_s: float,
    grind_setting: str,
    grinder: str | None = None,
    temperature_c: float | None = None,
    rating: int | None = None,
    taste_tags: list[str] | None = None,
    notes: str | None = None,
) -> dict[str, Any]:
    get_bean(settings, bean_id)
    if min(dose_g, yield_g, time_s) <= 0:
        raise ValueError("dose, yield and time must be positive")
    if not grind_setting.strip():
        raise ValueError("grind_setting is required")
    if rating is not None and rating not in range(1, 6):
        raise ValueError("rating must be between 1 and 5")

    shot_id = str(uuid4())
    tags = [tag.strip() for tag in (taste_tags or []) if tag.strip()]
    with connect(settings.data_dir / DB_FILENAME) as connection:
        connection.execute(
            """INSERT INTO shots
               (id, bean_id, dose_g, yield_g, time_s, grind_setting, grinder,
                temperature_c, rating, taste_tags_json, notes, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                shot_id,
                bean_id,
                dose_g,
                yield_g,
                time_s,
                grind_setting.strip(),
                grinder,
                temperature_c,
                rating,
                json.dumps(tags, separators=(",", ":")),
                notes,
                _now(),
            ),
        )
        row = connection.execute(
            """SELECT shots.*, beans.name AS bean_name
               FROM shots JOIN beans ON beans.id = shots.bean_id
               WHERE shots.id = ?""",
            (shot_id,),
        ).fetchone()
    return _shot(row)


def history(
    settings: Settings,
    bean_id: str | None = None,
    limit: int = 20,
    *,
    start_date: str | None = None,
    end_date: str | None = None,
) -> list[dict[str, Any]]:
    if limit < 1:
        raise ValueError("limit must be positive")
    query = """SELECT shots.*, beans.name AS bean_name
               FROM shots JOIN beans ON beans.id = shots.bean_id"""
    clauses = []
    parameters: list[Any] = []
    if bean_id is not None:
        get_bean(settings, bean_id)
        clauses.append("shots.bean_id = ?")
        parameters.append(bean_id)
    if start_date is not None:
        clauses.append("date(shots.created_at) >= ?")
        parameters.append(start_date)
    if end_date is not None:
        clauses.append("date(shots.created_at) <= ?")
        parameters.append(end_date)
    if clauses:
        query += " WHERE " + " AND ".join(clauses)
    query += " ORDER BY shots.created_at DESC, shots.id DESC LIMIT ?"
    parameters.append(min(limit, 100))
    with connect(settings.data_dir / DB_FILENAME) as connection:
        return [_shot(row) for row in connection.execute(query, parameters)]


def recommend_next(settings: Settings, bean_id: str) -> dict[str, Any]:
    shots = history(settings, bean_id=bean_id, limit=100)
    if not shots:
        return {
            "recommendation": "Log a shot before changing variables.",
            "change": None,
            "target": None,
            "evidence": [],
        }

    rated = [shot for shot in shots if shot["rating"] is not None]
    best = max(rated, key=lambda shot: (shot["rating"], shot["created_at"]), default=None)
    if best is not None and best["rating"] >= 4:
        return {
            "recommendation": "Repeat the best-rated shot.",
            "change": None,
            "target": {
                key: best[key]
                for key in (
                    "dose_g",
                    "yield_g",
                    "time_s",
                    "grind_setting",
                    "temperature_c",
                )
            },
            "evidence": [{"shot_id": best["id"], "rating": best["rating"]}],
        }

    latest = shots[0]
    tags = {tag.casefold() for tag in latest["taste_tags"]}
    direction = None
    if "sour" in tags or latest["time_s"] < 25:
        direction = "finer"
    elif "bitter" in tags or latest["time_s"] > 35:
        direction = "coarser"
    recommendation = (
        f"Grind {direction}; keep every other setting unchanged."
        if direction
        else "Repeat once before changing a variable."
    )
    return {
        "recommendation": recommendation,
        "change": {"grind_setting": direction} if direction else None,
        "target": None,
        "evidence": [
            {
                "shot_id": latest["id"],
                "time_s": latest["time_s"],
                "taste_tags": latest["taste_tags"],
            }
        ],
    }


def register_mcp(server: MCPServer, settings: Settings) -> None:
    def add_bean_tool(
        name: str,
        roaster: str | None = None,
        roast_date: str | None = None,
        origin: str | None = None,
        process: str | None = None,
        notes: str | None = None,
    ) -> dict[str, Any]:
        """Remember a bag of coffee beans."""
        return add_bean(settings, name, roaster, roast_date, origin, process, notes=notes)

    def list_beans_tool(status: str | None = "open") -> list[dict[str, Any]]:
        """List coffee beans, normally only open bags."""
        return list_beans(settings, status)

    def log_shot_tool(
        bean_id: str,
        dose_g: float,
        yield_g: float,
        time_s: float,
        grind_setting: str,
        grinder: str | None = None,
        temperature_c: float | None = None,
        rating: int | None = None,
        taste_tags: list[str] | None = None,
        notes: str | None = None,
    ) -> dict[str, Any]:
        """Log an espresso shot and its outcome."""
        return log_shot(
            settings,
            bean_id,
            dose_g=dose_g,
            yield_g=yield_g,
            time_s=time_s,
            grind_setting=grind_setting,
            grinder=grinder,
            temperature_c=temperature_c,
            rating=rating,
            taste_tags=taste_tags,
            notes=notes,
        )

    def history_tool(bean_id: str | None = None, limit: int = 20) -> list[dict[str, Any]]:
        """Return recent espresso shots."""
        return history(settings, bean_id, limit)

    def recommend_next_tool(bean_id: str) -> dict[str, Any]:
        """Recommend one conservative next adjustment from personal history."""
        return recommend_next(settings, bean_id)

    server.add_tool(add_bean_tool, name="coffee.add_bean")
    server.add_tool(list_beans_tool, name="coffee.list_beans")
    server.add_tool(log_shot_tool, name="coffee.log_shot")
    server.add_tool(history_tool, name="coffee.history")
    server.add_tool(recommend_next_tool, name="coffee.recommend_next")


@router.get("")
def coffee_page(request: Request, period: str = "week") -> Response:
    settings = request.app.state.settings
    selected = dashboard_period(period)
    beans = list_beans(settings)
    shots = history(
        settings,
        limit=100,
        start_date=selected["start"],
        end_date=selected["end"],
    )
    return render(
        request,
        "coffee.html",
        title="Coffee",
        beans=beans,
        shots=shots,
        dashboard=coffee_dashboard(shots, len(beans)),
        period=selected,
    )


def launcher_summary(settings: Settings) -> str:
    count = len(list_beans(settings))
    return f"{count} open {'bean' if count == 1 else 'beans'}"


def _validate_bean(name: str, status: str) -> None:
    if not name:
        raise ValueError("name is required")
    if status not in {"open", "archived"}:
        raise ValueError("status must be open or archived")


def _shot(row: Any) -> dict[str, Any]:
    result = dict(row)
    result["taste_tags"] = json.loads(result.pop("taste_tags_json"))
    return result


def _now() -> str:
    return datetime.now(UTC).isoformat()


PLUGIN = Plugin(
    name="coffee",
    icon="coffee",
    db_filename=DB_FILENAME,
    migrations=MIGRATIONS,
    register_mcp=register_mcp,
    router=router,
    launcher_summary=launcher_summary,
)
