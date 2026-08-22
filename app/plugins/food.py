"""Food plugin wiring and stable public domain imports."""

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import Response

from app.config import Settings
from app.dashboard import food_dashboard
from app.db import connect
from app.plugins.food_corrections import correct_record
from app.plugins.food_mcp import register_mcp
from app.plugins.food_nutrition import find_nutrition, get_nutrition, upsert_nutrition
from app.plugins.food_receipts import ingest_receipt
from app.plugins.food_records import query_records, record_consumption
from app.plugins.food_reporting import find_gaps, summary
from app.plugins.food_schema import DB_FILENAME, MIGRATIONS
from app.runtime import Plugin
from app.web import dashboard_period, render

router = APIRouter(prefix="/food")


@router.get("")
def food_page(
    request: Request,
    period: str = "week",
    q: str = "",
    restaurant: str = "Grain",
    sort: str = "name",
    include_estimates: bool = False,
) -> Response:
    settings = request.app.state.settings
    selected = dashboard_period(period, datetime.now().astimezone().date())
    report = summary(settings, selected["start"], selected["end"], [])
    records = query_records(
        settings,
        start_date=selected["start"],
        end_date=selected["end"],
        limit=500,
    )
    return render(
        request,
        "food.html",
        title="Food",
        dashboard=food_dashboard(report, records),
        catalogue=_catalogue(settings, q, restaurant, sort, include_estimates),
        period=selected,
    )


def _catalogue(
    settings: Settings,
    query: str,
    restaurant: str,
    sort: str,
    include_estimates: bool,
) -> dict[str, Any]:
    query = query.strip()[:100]
    restaurant = restaurant.strip()[:100]
    orders = {
        "name": "restaurant, item, portion_basis, id",
        "calories_asc": "calories, protein_g DESC, restaurant, item, id",
        "calories_desc": "calories DESC, protein_g DESC, restaurant, item, id",
        "protein_desc": "protein_g DESC, calories, restaurant, item, id",
        "protein_asc": "protein_g, calories, restaurant, item, id",
    }
    selected_sort = sort if sort in orders else "name"
    clauses, parameters = [], []
    if not include_estimates:
        clauses.append("evidence_class = 'fact'")
    if query:
        clauses.append("(item LIKE ? COLLATE NOCASE OR category LIKE ? COLLATE NOCASE)")
        parameters.extend([f"%{query}%", f"%{query}%"])
    if restaurant:
        clauses.append("restaurant = ? COLLATE NOCASE")
        parameters.append(restaurant)
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    with connect(settings.data_dir / DB_FILENAME) as connection:
        restaurants = [
            row[0]
            for row in connection.execute(
                "SELECT DISTINCT restaurant FROM nutrition ORDER BY restaurant COLLATE NOCASE"
            )
        ]
        rows = connection.execute(
            f"""SELECT restaurant, item, portion_basis, calories, protein_g
                FROM nutrition{where} ORDER BY {orders[selected_sort]} LIMIT 10""",
            parameters,
        ).fetchall()
    return {
        "items": [dict(row) for row in rows],
        "query": query,
        "restaurant": restaurant,
        "restaurants": restaurants,
        "sort": selected_sort,
        "include_estimates": include_estimates,
    }


def launcher_summary(settings: Settings) -> str:
    with connect(settings.data_dir / DB_FILENAME) as connection:
        count = connection.execute("SELECT COUNT(*) FROM records").fetchone()[0]
    return f"{count} food {'record' if count == 1 else 'records'}"


PLUGIN = Plugin(
    name="food",
    icon="food",
    db_filename=DB_FILENAME,
    migrations=MIGRATIONS,
    register_mcp=register_mcp,
    router=router,
    launcher_summary=launcher_summary,
)

__all__ = [
    "DB_FILENAME",
    "MIGRATIONS",
    "PLUGIN",
    "correct_record",
    "find_gaps",
    "find_nutrition",
    "get_nutrition",
    "ingest_receipt",
    "query_records",
    "record_consumption",
    "summary",
    "upsert_nutrition",
]
