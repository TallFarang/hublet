"""The small boundary between Health freshness and Goals definitions."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime

from app.config import Settings
from app.db import connect
from app.plugins.health_schema import MAPPINGS


def update_healthkit_sources(settings: Settings, tracking_status: str) -> int:
    database = settings.data_dir / "goals.db"
    if not database.is_file():
        return 0
    changed = 0
    try:
        with connect(database) as connection:
            rows = connection.execute(
                "SELECT id, domain_id, status, evidence_sources_json FROM goals"
            ).fetchall()
            for row in rows:
                sources = json.loads(row["evidence_sources_json"])
                matched = False
                for source in sources:
                    if source.get("source") == "HealthKit" and source.get("metric") in {
                        metric for metric, _unit in MAPPINGS.values()
                    }:
                        matched = True
                        source["tracking_status"] = tracking_status
                        source.setdefault("details", {})["transport"] = (
                            "Agentbridge via Hublet Health"
                        )
                status = row["status"]
                if matched and row["domain_id"] == "health" and status == "awaiting_automated_data":
                    status = "active"
                encoded = json.dumps(sources, sort_keys=True, separators=(",", ":"))
                if encoded != row["evidence_sources_json"] or status != row["status"]:
                    connection.execute(
                        """UPDATE goals SET evidence_sources_json = ?, status = ?, updated_at = ?
                           WHERE id = ?""",
                        (encoded, status, datetime.now(UTC).isoformat(), row["id"]),
                    )
                    changed += 1
    except sqlite3.OperationalError:
        return 0
    return changed
