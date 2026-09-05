"""Coffee's deliberately small MCP surface."""

from __future__ import annotations

from typing import Any

from mcp.server import MCPServer

from app.config import Settings
from app.plugins.coffee_bags import add_bag, list_bags, set_bag_status
from app.plugins.coffee_brews import history, log_brew
from app.plugins.coffee_schema import DEFAULT_GRINDER


def register_mcp(server: MCPServer, settings: Settings) -> None:
    def add_bag_tool(
        name: str,
        roaster: str,
        roast_date: str | None = None,
        roast_level: str | None = None,
        origin: str | None = None,
        process: str | None = None,
        notes: str | None = None,
    ) -> dict[str, Any]:
        """Open a distinct purchased bag of coffee."""
        return add_bag(
            settings,
            name,
            roaster,
            roast_date,
            roast_level,
            origin,
            process,
            notes,
        )

    def list_bags_tool(
        status: str | None = "open",
        name: str | None = None,
        roaster: str | None = None,
    ) -> list[dict[str, Any]]:
        """List bags, with exact case-insensitive name and roaster matching."""
        return list_bags(settings, status, name=name, roaster=roaster)

    def set_bag_status_tool(bag_id: str, status: str) -> dict[str, Any]:
        """Mark a bag open or archived."""
        return set_bag_status(settings, bag_id, status)

    def log_brew_tool(
        bag_id: str,
        method: str,
        dose_g: float,
        grind_setting: str,
        water_g: float | None = None,
        yield_g: float | None = None,
        time_s: float | None = None,
        grinder: str = DEFAULT_GRINDER,
        temperature_c: float | None = None,
        bypass_water_g: float | None = None,
        rating: int | None = None,
        taste_notes: str | None = None,
        notes: str | None = None,
    ) -> dict[str, Any]:
        """Log a complete recipe snapshot and its outcome."""
        return log_brew(
            settings,
            bag_id,
            method,
            dose_g,
            grind_setting,
            water_g=water_g,
            yield_g=yield_g,
            time_s=time_s,
            grinder=grinder,
            temperature_c=temperature_c,
            bypass_water_g=bypass_water_g,
            rating=rating,
            taste_notes=taste_notes,
            notes=notes,
        )

    def history_tool(
        bag_id: str | None = None,
        method: str | None = None,
        limit: int = 20,
        name: str | None = None,
        roaster: str | None = None,
        roast_level: str | None = None,
        origin: str | None = None,
        process: str | None = None,
    ) -> list[dict[str, Any]]:
        """Find prior recipes by bag, method, or exact bean metadata."""
        return history(
            settings,
            bag_id,
            method,
            limit,
            name=name,
            roaster=roaster,
            roast_level=roast_level,
            origin=origin,
            process=process,
        )

    server.add_tool(add_bag_tool, name="coffee.add_bag")
    server.add_tool(list_bags_tool, name="coffee.list_bags")
    server.add_tool(set_bag_status_tool, name="coffee.set_bag_status")
    server.add_tool(log_brew_tool, name="coffee.log_brew")
    server.add_tool(history_tool, name="coffee.history")
