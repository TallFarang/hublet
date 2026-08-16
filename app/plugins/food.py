"""Food plugin wiring and stable public domain imports."""

from datetime import datetime, timedelta

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
from app.web import render

router = APIRouter(prefix="/food")


@router.get("")
def food_page(request: Request) -> Response:
    settings = request.app.state.settings
    end = datetime.now().astimezone().date()
    start = end - timedelta(days=6)
    report = summary(settings, start.isoformat(), end.isoformat(), [])
    records = query_records(
        settings, start_date=start.isoformat(), end_date=end.isoformat(), limit=500
    )
    with connect(settings.data_dir / DB_FILENAME) as connection:
        counts = dict(
            connection.execute(
                """SELECT
                   (SELECT COUNT(*) FROM records) AS records,
                   (SELECT COUNT(*) FROM nutrition) AS nutrition,
                   (SELECT COUNT(*) FROM records
                    WHERE status = 'uncertain'
                       OR (status = 'eaten' AND nutrition_id IS NULL)) AS unresolved"""
            ).fetchone()
        )
    return render(
        request,
        "food.html",
        title="Food",
        counts=counts,
        dashboard=food_dashboard(report, records),
    )


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
