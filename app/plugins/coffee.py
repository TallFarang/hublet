"""Coffee plugin wiring and public domain API."""

from fastapi import APIRouter, Request
from fastapi.responses import Response

from app.config import Settings
from app.dashboard import coffee_dashboard
from app.dashboard_config import load_config
from app.plugins.coffee_bags import add_bag, get_bag, list_bags, set_bag_status
from app.plugins.coffee_brews import history, log_brew
from app.plugins.coffee_mcp import register_mcp
from app.plugins.coffee_schema import DB_FILENAME, DEFAULT_GRINDER, METHODS, MIGRATIONS
from app.runtime import Plugin
from app.web import dashboard_period, render

router = APIRouter(prefix="/coffee")


@router.get("")
def coffee_page(request: Request, period: str = "week") -> Response:
    settings = request.app.state.settings
    selected = dashboard_period(period)
    bags = list_bags(settings)
    brews = history(
        settings,
        limit=100,
        start_date=selected["start"],
        end_date=selected["end"],
    )
    return render(
        request,
        "coffee.html",
        title="Coffee",
        bags=bags,
        dashboard=coffee_dashboard(
            brews,
            len(bags),
            load_config(settings)["plugins"]["coffee"],
        ),
        period=selected,
    )


def launcher_summary(settings: Settings) -> str:
    count = len(list_bags(settings))
    return f"{count} open {'bag' if count == 1 else 'bags'}"


PLUGIN = Plugin(
    name="coffee",
    icon="coffee",
    db_filename=DB_FILENAME,
    migrations=MIGRATIONS,
    register_mcp=register_mcp,
    router=router,
    launcher_summary=launcher_summary,
)

__all__ = [
    "DEFAULT_GRINDER",
    "METHODS",
    "PLUGIN",
    "add_bag",
    "get_bag",
    "history",
    "list_bags",
    "log_brew",
    "set_bag_status",
]
