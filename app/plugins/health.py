"""Health plugin wiring over the current Agentbridge snapshot."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Request
from fastapi.responses import Response
from mcp.server import MCPServer
from pydantic import Field

from app.config import Settings
from app.dashboard import health_dashboard
from app.plugins.health_query import list_types, query_records, sync_status
from app.plugins.health_report import summary
from app.plugins.health_schema import DB_FILENAME, MIGRATIONS
from app.plugins.health_sync import sync_agentbridge
from app.runtime import Plugin
from app.web import render

router = APIRouter(prefix="/health")
QueryLimit = Annotated[int, Field(ge=1, le=200)]
QueryOffset = Annotated[int, Field(ge=0)]


def register_mcp(server: MCPServer, settings: Settings) -> None:
    def sync_tool(dry_run: bool = False) -> dict[str, Any]:
        """Synchronize the configured Agentbridge directory atomically."""
        return sync_agentbridge(settings, dry_run)

    def query_tool(
        type: str,
        start_date: str,
        end_date: str,
        limit: QueryLimit = 100,
        offset: QueryOffset = 0,
        include_raw: bool = False,
    ) -> dict[str, Any]:
        """Query one HealthKit type from the current snapshot. Limit is at most 200."""
        return query_records(settings, type, start_date, end_date, limit, offset, include_raw)

    def summary_tool(start_date: str, end_date: str) -> dict[str, Any]:
        """Return compact coverage, mapped metrics, and goal-ready evidence."""
        return summary(settings, start_date, end_date)

    def status_tool() -> dict[str, Any]:
        """Return sync freshness, missing dates, and the latest error."""
        return sync_status(settings)

    def types_tool() -> list[dict[str, Any]]:
        """List every discovered HealthKit type without a semantic allowlist."""
        return list_types(settings)

    server.add_tool(sync_tool, name="health_sync_agentbridge")
    server.add_tool(query_tool, name="health_query_records")
    server.add_tool(summary_tool, name="health_summary")
    server.add_tool(status_tool, name="health_sync_status")
    server.add_tool(types_tool, name="health_list_types")


@router.get("")
def health_page(request: Request) -> Response:
    settings = request.app.state.settings
    status = sync_status(settings)
    end = (
        date.fromisoformat(status["latest_export_date"])
        if status["latest_export_date"]
        else datetime.now().astimezone().date()
    )
    report = summary(settings, (end - timedelta(days=29)).isoformat(), end.isoformat())
    return render(
        request,
        "health.html",
        title="Health",
        dashboard=health_dashboard(report),
    )


def launcher_summary(settings: Settings) -> str:
    status = sync_status(settings)
    if not status["latest_export_date"]:
        return "Not synced"
    return f"{status['freshness'].capitalize()} · {status['latest_export_date']}"


PLUGIN = Plugin(
    name="health",
    icon="health",
    db_filename=DB_FILENAME,
    migrations=MIGRATIONS,
    register_mcp=register_mcp,
    router=router,
    launcher_summary=launcher_summary,
)
