"""Canonical goal definitions and immutable evidence."""

from __future__ import annotations

import json
import re
from datetime import UTC, date, datetime, timedelta
from typing import Annotated, Any
from uuid import uuid4

from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse, Response
from mcp.server import MCPServer

from app.config import Settings
from app.dashboard import goal_dashboard
from app.db import connect
from app.runtime import Plugin
from app.web import render

DB_FILENAME = "goals.db"
DIRECTIONS = {"above", "at_or_above", "at_or_below", "increasing_trend", "equals"}
ROLES = {"outcome", "supporting_indicator"}
NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$")
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
    """
    CREATE TABLE goals_v1_empty_guard (row_count INTEGER NOT NULL CHECK (row_count = 0));
    INSERT INTO goals_v1_empty_guard
    SELECT (SELECT COUNT(*) FROM goals) + (SELECT COUNT(*) FROM entries);
    DROP TABLE goals_v1_empty_guard;
    DROP TABLE entries;
    DROP TABLE goals;

    CREATE TABLE domains (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        display_order INTEGER NOT NULL,
        status TEXT NOT NULL
    );
    INSERT INTO domains (id, name, display_order, status) VALUES
        ('health', 'Health', 10, 'active'),
        ('career', 'Career', 20, 'active'),
        ('social', 'Social', 30, 'tbc');

    CREATE TABLE goals (
        id TEXT PRIMARY KEY,
        domain_id TEXT NOT NULL REFERENCES domains(id),
        display_order INTEGER NOT NULL DEFAULT 0,
        outcome TEXT NOT NULL,
        description TEXT,
        horizon TEXT,
        status TEXT NOT NULL DEFAULT 'active',
        target_json TEXT,
        systems_json TEXT NOT NULL DEFAULT '[]',
        dependencies_json TEXT NOT NULL DEFAULT '[]',
        evidence_sources_json TEXT NOT NULL DEFAULT '[]',
        notes_json TEXT NOT NULL DEFAULT '[]',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    CREATE INDEX goals_domain_order ON goals(domain_id, display_order, id);
    CREATE INDEX goals_status ON goals(status);

    CREATE TABLE observations (
        id TEXT PRIMARY KEY,
        goal_id TEXT NOT NULL REFERENCES goals(id),
        metric TEXT NOT NULL,
        value_json TEXT NOT NULL,
        unit TEXT,
        source TEXT NOT NULL,
        reference TEXT,
        observed_at TEXT,
        period_start TEXT,
        period_end TEXT,
        note TEXT,
        recorded_at TEXT NOT NULL,
        idempotency_key TEXT NOT NULL UNIQUE,
        CHECK (
            (observed_at IS NOT NULL AND period_start IS NULL AND period_end IS NULL)
            OR
            (observed_at IS NULL AND period_start IS NOT NULL AND period_end IS NOT NULL)
        )
    );
    CREATE INDEX observations_lookup
        ON observations(goal_id, metric, source, observed_at, period_end, recorded_at);
    CREATE TRIGGER observations_no_update BEFORE UPDATE ON observations
    BEGIN
        SELECT RAISE(ABORT, 'observations are immutable');
    END;
    CREATE TRIGGER observations_no_delete BEFORE DELETE ON observations
    BEGIN
        SELECT RAISE(ABORT, 'observations are immutable');
    END;
    """,
)
router = APIRouter(prefix="/goals")


def list_domains(settings: Settings) -> list[dict[str, Any]]:
    with connect(settings.data_dir / DB_FILENAME) as connection:
        rows = connection.execute(
            "SELECT * FROM domains ORDER BY display_order, id"
        ).fetchall()
    return [dict(row) for row in rows]


def create_goal(
    settings: Settings,
    goal_id: str,
    domain: str,
    outcome: str,
    display_order: int = 0,
    description: str | None = None,
    horizon: str | None = None,
    status: str = "active",
    target: dict[str, Any] | None = None,
    systems: list[str] | None = None,
    dependencies: list[str] | None = None,
    evidence_sources: list[dict[str, Any]] | None = None,
    notes: list[str] | None = None,
) -> dict[str, Any]:
    definition = _normalise_definition(
        goal_id=goal_id,
        domain=domain,
        display_order=display_order,
        outcome=outcome,
        description=description,
        horizon=horizon,
        status=status,
        target=target,
        systems=systems,
        dependencies=dependencies,
        evidence_sources=evidence_sources,
        notes=notes,
    )
    now = _now()
    with connect(settings.data_dir / DB_FILENAME) as connection:
        _require_domain(connection, definition["domain"])
        connection.execute(
            """INSERT INTO goals
               (id, domain_id, display_order, outcome, description, horizon, status,
                target_json, systems_json, dependencies_json, evidence_sources_json,
                notes_json, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            _definition_values(definition) + (now, now),
        )
    return get_goal(settings, goal_id)


def update_goal(
    settings: Settings,
    goal_id: str,
    *,
    domain: str,
    display_order: int,
    outcome: str,
    description: str | None,
    horizon: str | None,
    status: str,
    target: dict[str, Any] | None,
    systems: list[str],
    dependencies: list[str],
    evidence_sources: list[dict[str, Any]],
    notes: list[str],
) -> dict[str, Any]:
    get_goal(settings, goal_id)
    definition = _normalise_definition(
        goal_id=goal_id,
        domain=domain,
        display_order=display_order,
        outcome=outcome,
        description=description,
        horizon=horizon,
        status=status,
        target=target,
        systems=systems,
        dependencies=dependencies,
        evidence_sources=evidence_sources,
        notes=notes,
    )
    with connect(settings.data_dir / DB_FILENAME) as connection:
        _require_domain(connection, definition["domain"])
        connection.execute(
            """UPDATE goals SET
               domain_id = ?, display_order = ?, outcome = ?, description = ?, horizon = ?,
               status = ?, target_json = ?, systems_json = ?, dependencies_json = ?,
               evidence_sources_json = ?, notes_json = ?, updated_at = ?
               WHERE id = ?""",
            _definition_values(definition)[1:] + (_now(), goal_id),
        )
    return get_goal(settings, goal_id)


def set_status(settings: Settings, goal_id: str, status: str) -> dict[str, Any]:
    get_goal(settings, goal_id)
    status = _name(status, "status")
    with connect(settings.data_dir / DB_FILENAME) as connection:
        connection.execute(
            "UPDATE goals SET status = ?, updated_at = ? WHERE id = ?",
            (status, _now(), goal_id),
        )
    return get_goal(settings, goal_id)


def list_goals(
    settings: Settings, domain: str | None = None, status: str | None = None
) -> list[dict[str, Any]]:
    clauses = []
    parameters: list[str] = []
    if domain is not None:
        clauses.append("goals.domain_id = ?")
        parameters.append(_name(domain, "domain"))
    if status is not None:
        clauses.append("goals.status = ?")
        parameters.append(_name(status, "status"))
    query = _GOAL_SELECT
    if clauses:
        query += " WHERE " + " AND ".join(clauses)
    query += " ORDER BY domains.display_order, goals.display_order, goals.id"
    with connect(settings.data_dir / DB_FILENAME) as connection:
        rows = connection.execute(query, parameters).fetchall()
    return [_goal_from_row(row) for row in rows]


def get_goal(settings: Settings, goal_id: str, history_limit: int = 100) -> dict[str, Any]:
    _limit(history_limit)
    with connect(settings.data_dir / DB_FILENAME) as connection:
        row = connection.execute(_GOAL_SELECT + " WHERE goals.id = ?", (goal_id,)).fetchone()
        latest_rows = connection.execute(
            """SELECT * FROM (
                   SELECT observations.*,
                          ROW_NUMBER() OVER (
                              PARTITION BY metric, source
                              ORDER BY COALESCE(observed_at, period_end) DESC,
                                       recorded_at DESC, id DESC
                          ) AS position
                   FROM observations WHERE goal_id = ?
               ) WHERE position = 1
               ORDER BY COALESCE(observed_at, period_end) DESC, recorded_at DESC, id DESC""",
            (goal_id,),
        ).fetchall()
    if row is None:
        raise ValueError("Goal not found")
    result = _goal_from_row(row)
    result["latest_observations"] = [_observation_from_row(row) for row in latest_rows]
    result["history"] = query_evidence(settings, goal_id=goal_id, limit=history_limit)
    return result


def get_registry(settings: Settings) -> dict[str, Any]:
    domains = list_domains(settings)
    goals_by_domain: dict[str, list[dict[str, Any]]] = {domain["id"]: [] for domain in domains}
    for goal in list_goals(settings):
        goals_by_domain[goal["domain"]].append(goal)
    return {
        "domains": [{**domain, "goals": goals_by_domain[domain["id"]]} for domain in domains]
    }


def record_evidence(
    settings: Settings,
    goal_id: str,
    metric: str,
    value: float | str | bool,
    source: str,
    idempotency_key: str,
    unit: str | None = None,
    reference: str | None = None,
    observed_at: str | None = None,
    period_start: str | None = None,
    period_end: str | None = None,
    note: str | None = None,
) -> dict[str, Any]:
    get_goal(settings, goal_id)
    if not isinstance(value, (int, float, str, bool)):
        raise TypeError("evidence value must be a number, string or boolean")
    if isinstance(value, str) and not value.strip():
        raise ValueError("evidence value cannot be empty")
    timing = _normalise_timing(observed_at, period_start, period_end)
    payload = {
        "goal_id": goal_id,
        "metric": _name(metric, "metric"),
        "value": value,
        "unit": _optional_text(unit),
        "source": _required_text(source, "source"),
        "reference": _optional_text(reference),
        **timing,
        "note": _optional_text(note),
        "idempotency_key": _required_text(idempotency_key, "idempotency_key"),
    }
    with connect(settings.data_dir / DB_FILENAME) as connection:
        observation_id = str(uuid4())
        inserted = connection.execute(
            """INSERT INTO observations
               (id, goal_id, metric, value_json, unit, source, reference, observed_at,
                period_start, period_end, note, recorded_at, idempotency_key)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(idempotency_key) DO NOTHING""",
            (
                observation_id,
                payload["goal_id"],
                payload["metric"],
                _dump(payload["value"]),
                payload["unit"],
                payload["source"],
                payload["reference"],
                payload["observed_at"],
                payload["period_start"],
                payload["period_end"],
                payload["note"],
                _now(),
                payload["idempotency_key"],
            ),
        )
        row = connection.execute(
            "SELECT * FROM observations WHERE idempotency_key = ?",
            (payload["idempotency_key"],),
        ).fetchone()
        observation = _observation_from_row(row)
        if _observation_payload(observation) != _observation_payload(payload):
            raise ValueError("idempotency key already belongs to a different observation")
    return {"created": inserted.rowcount == 1, "observation": observation}


def query_evidence(
    settings: Settings,
    goal_id: str | None = None,
    metric: str | None = None,
    source: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    limit: int = 500,
) -> list[dict[str, Any]]:
    _limit(limit)
    clauses = []
    parameters: list[Any] = []
    if goal_id is not None:
        clauses.append("goal_id = ?")
        parameters.append(goal_id)
    if metric is not None:
        clauses.append("metric = ?")
        parameters.append(_name(metric, "metric"))
    if source is not None:
        clauses.append("source = ?")
        parameters.append(_required_text(source, "source"))
    if start_date is not None:
        clauses.append("date(COALESCE(observed_at, period_end)) >= ?")
        parameters.append(_date(start_date, "start_date").isoformat())
    if end_date is not None:
        clauses.append("date(COALESCE(observed_at, period_end)) <= ?")
        parameters.append(_date(end_date, "end_date").isoformat())
    if start_date is not None and end_date is not None and start_date > end_date:
        raise ValueError("start_date must not be after end_date")
    query = "SELECT * FROM observations"
    if clauses:
        query += " WHERE " + " AND ".join(clauses)
    query += " ORDER BY COALESCE(observed_at, period_end) DESC, recorded_at DESC, id DESC LIMIT ?"
    parameters.append(limit)
    with connect(settings.data_dir / DB_FILENAME) as connection:
        rows = connection.execute(query, parameters).fetchall()
    return [_observation_from_row(row) for row in rows]


def report_snapshot(settings: Settings, start_date: str, end_date: str) -> dict[str, Any]:
    start = _date(start_date, "start_date")
    end = _date(end_date, "end_date")
    if start > end:
        raise ValueError("start_date must not be after end_date")
    registry = get_registry(settings)
    for domain in registry["domains"]:
        reported_goals = []
        for definition in domain["goals"]:
            evidence = []
            for source in definition["evidence_sources"]:
                observations = query_evidence(
                    settings,
                    goal_id=definition["id"],
                    metric=source["metric"],
                    source=source["source"],
                    start_date=start.isoformat(),
                    end_date=end.isoformat(),
                )
                prior = query_evidence(
                    settings,
                    goal_id=definition["id"],
                    metric=source["metric"],
                    source=source["source"],
                    end_date=(start - timedelta(days=1)).isoformat(),
                    limit=1,
                )
                gap = None
                if not observations:
                    gap = {
                        "connected": "no_observation_in_period",
                        "stale": "source_stale",
                    }.get(source["tracking_status"], "source_unavailable")
                evidence.append(
                    {
                        "source_definition": source,
                        "observations": observations,
                        "latest_before_period": prior[0] if prior else None,
                        "gap": gap,
                    }
                )
            reported_goals.append({"definition": definition, "evidence": evidence})
        domain["goals"] = reported_goals
    return {"start_date": start.isoformat(), "end_date": end.isoformat(), **registry}


def register_mcp(server: MCPServer, settings: Settings) -> None:
    def registry_tool() -> dict[str, Any]:
        """Return every domain and complete goal definition in display order."""
        return get_registry(settings)

    def list_tool(domain: str | None = None, status: str | None = None) -> list[dict[str, Any]]:
        """List ordered goal summaries, optionally filtered by domain or status."""
        return list_goals(settings, domain, status)

    def get_tool(goal_id: str, history_limit: int = 100) -> dict[str, Any]:
        """Return one complete goal with its latest evidence and history."""
        return get_goal(settings, goal_id, history_limit)

    def create_tool(
        goal_id: str,
        domain: str,
        outcome: str,
        display_order: int = 0,
        description: str | None = None,
        horizon: str | None = None,
        status: str = "active",
        target: dict[str, Any] | None = None,
        systems: list[str] | None = None,
        dependencies: list[str] | None = None,
        evidence_sources: list[dict[str, Any]] | None = None,
        notes: list[str] | None = None,
    ) -> dict[str, Any]:
        """Create a complete goal definition with a stable caller-supplied ID."""
        return create_goal(
            settings,
            goal_id,
            domain,
            outcome,
            display_order,
            description,
            horizon,
            status,
            target,
            systems,
            dependencies,
            evidence_sources,
            notes,
        )

    def update_tool(
        goal_id: str,
        domain: str,
        display_order: int,
        outcome: str,
        description: str | None,
        horizon: str | None,
        status: str,
        target: dict[str, Any] | None,
        systems: list[str],
        dependencies: list[str],
        evidence_sources: list[dict[str, Any]],
        notes: list[str],
    ) -> dict[str, Any]:
        """Replace one complete goal definition while preserving its stable ID."""
        return update_goal(
            settings,
            goal_id,
            domain=domain,
            display_order=display_order,
            outcome=outcome,
            description=description,
            horizon=horizon,
            status=status,
            target=target,
            systems=systems,
            dependencies=dependencies,
            evidence_sources=evidence_sources,
            notes=notes,
        )

    def status_tool(goal_id: str, status: str) -> dict[str, Any]:
        """Set a goal's status without changing the rest of its definition."""
        return set_status(settings, goal_id, status)

    def record_tool(
        goal_id: str,
        metric: str,
        value: float | str | bool,
        source: str,
        idempotency_key: str,
        unit: str | None = None,
        reference: str | None = None,
        observed_at: str | None = None,
        period_start: str | None = None,
        period_end: str | None = None,
        note: str | None = None,
    ) -> dict[str, Any]:
        """Record one absolute observation idempotently."""
        return record_evidence(
            settings,
            goal_id,
            metric,
            value,
            source,
            idempotency_key,
            unit,
            reference,
            observed_at,
            period_start,
            period_end,
            note,
        )

    def query_tool(
        goal_id: str | None = None,
        metric: str | None = None,
        source: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        limit: int = 500,
    ) -> list[dict[str, Any]]:
        """Query immutable evidence by goal, metric, source and effective date."""
        return query_evidence(settings, goal_id, metric, source, start_date, end_date, limit)

    def snapshot_tool(start_date: str, end_date: str) -> dict[str, Any]:
        """Build a factual reporting snapshot with prior values and explicit gaps."""
        return report_snapshot(settings, start_date, end_date)

    server.add_tool(registry_tool, name="goals_registry_get")
    server.add_tool(list_tool, name="goals_list")
    server.add_tool(get_tool, name="goals_get")
    server.add_tool(create_tool, name="goals_create")
    server.add_tool(update_tool, name="goals_update")
    server.add_tool(status_tool, name="goals_set_status")
    server.add_tool(record_tool, name="goals_record_evidence")
    server.add_tool(query_tool, name="goals_query_evidence")
    server.add_tool(snapshot_tool, name="goals_report_snapshot")


@router.get("")
def goals_page(request: Request) -> Response:
    registry = get_registry(request.app.state.settings)
    for domain in registry["domains"]:
        domain["goals"] = [
            _goal_for_dashboard(request.app.state.settings, definition["id"])
            for definition in domain["goals"]
        ]
        for goal in domain["goals"]:
            goal["dashboard"] = goal_dashboard(goal)
    return render(
        request,
        "goals.html",
        title="Goals",
        domains=registry["domains"],
    )


@router.post("")
def create_goal_form(
    request: Request,
    domain: Annotated[str, Form()],
    outcome: Annotated[str, Form()],
    description: Annotated[str, Form()] = "",
    horizon: Annotated[str, Form()] = "",
    target_metric: Annotated[str, Form()] = "",
    target_value: Annotated[str, Form()] = "",
    target_unit: Annotated[str, Form()] = "",
    target_direction: Annotated[str, Form()] = "equals",
) -> RedirectResponse:
    create_goal(
        request.app.state.settings,
        goal_id=str(uuid4()),
        domain=domain,
        outcome=outcome,
        description=description or None,
        horizon=horizon or None,
        target=_form_target(target_metric, target_value, target_unit, target_direction),
    )
    return RedirectResponse("/goals", status_code=303)


@router.post("/{goal_id}/edit")
def edit_goal_form(
    request: Request,
    goal_id: str,
    domain: Annotated[str, Form()],
    display_order: Annotated[int, Form()],
    outcome: Annotated[str, Form()],
    description: Annotated[str, Form()] = "",
    horizon: Annotated[str, Form()] = "",
    target_metric: Annotated[str, Form()] = "",
    target_value: Annotated[str, Form()] = "",
    target_unit: Annotated[str, Form()] = "",
    target_direction: Annotated[str, Form()] = "equals",
) -> RedirectResponse:
    current = get_goal(request.app.state.settings, goal_id)
    update_goal(
        request.app.state.settings,
        goal_id,
        domain=domain,
        display_order=display_order,
        outcome=outcome,
        description=description or None,
        horizon=horizon or None,
        status=current["status"],
        target=_form_target(
            target_metric,
            target_value,
            target_unit,
            target_direction,
            current["target"],
        ),
        systems=current["systems"],
        dependencies=current["dependencies"],
        evidence_sources=current["evidence_sources"],
        notes=current["notes"],
    )
    return RedirectResponse("/goals", status_code=303)


@router.post("/{goal_id}/status")
def status_form(
    request: Request, goal_id: str, status: Annotated[str, Form()]
) -> RedirectResponse:
    set_status(request.app.state.settings, goal_id, status)
    return RedirectResponse("/goals", status_code=303)


def launcher_summary(settings: Settings) -> str:
    count = len([goal for goal in list_goals(settings) if goal["status"] != "archived"])
    return f"{count} {'goal' if count == 1 else 'goals'}"


def _goal_for_dashboard(settings: Settings, goal_id: str) -> dict[str, Any]:
    goal = get_goal(settings, goal_id, history_limit=50)
    latest = {
        (observation["metric"], observation["source"]): observation
        for observation in goal["latest_observations"]
    }
    goal["evidence_sources"] = [
        {**source, "latest": latest.get((source["metric"], source["source"]))}
        for source in goal["evidence_sources"]
    ]
    return goal


def _form_target(
    metric: str,
    value: str,
    unit: str,
    direction: str,
    previous: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    if not metric.strip():
        return None
    parsed_value: int | float | str | None = value.strip() or None
    if isinstance(parsed_value, str):
        try:
            numeric = float(parsed_value)
            parsed_value = int(numeric) if numeric.is_integer() else numeric
        except ValueError:
            pass
    return {
        "metric": metric,
        "value": parsed_value,
        "unit": unit or None,
        "direction": direction,
        "required_duration": previous.get("required_duration") if previous else None,
        "qualifiers": previous.get("qualifiers", {}) if previous else {},
    }


def _normalise_definition(**definition: Any) -> dict[str, Any]:
    goal_id = _required_text(definition["goal_id"], "goal_id")
    if ID_PATTERN.fullmatch(goal_id) is None:
        raise ValueError("goal_id must contain only letters, numbers, dots, colons, underscores or hyphens")
    domain = _name(definition["domain"], "domain")
    outcome = _required_text(definition["outcome"], "outcome")
    status = _name(definition["status"], "status")
    display_order = definition["display_order"]
    if isinstance(display_order, bool) or not isinstance(display_order, int):
        raise TypeError("display_order must be an integer")
    target = _normalise_target(definition["target"])
    return {
        "id": goal_id,
        "domain": domain,
        "display_order": display_order,
        "outcome": outcome,
        "description": _optional_text(definition["description"]),
        "horizon": _optional_text(definition["horizon"]),
        "status": status,
        "target": target,
        "systems": _statements(definition["systems"], "systems"),
        "dependencies": _identifiers(definition["dependencies"], "dependencies"),
        "evidence_sources": _normalise_sources(definition["evidence_sources"], target),
        "notes": _statements(definition["notes"], "notes"),
    }


def _normalise_target(target: dict[str, Any] | None) -> dict[str, Any] | None:
    if target is None:
        return None
    if not isinstance(target, dict):
        raise TypeError("target must be an object")
    metric = _name(target.get("metric"), "target metric")
    value = target.get("value")
    if isinstance(value, bool) or value is not None and not isinstance(value, (int, float, str)):
        raise ValueError("target value must be a number or string")
    direction = target.get("direction") or "equals"
    if direction not in DIRECTIONS:
        raise ValueError("target direction is not supported")
    duration = target.get("required_duration")
    if duration is not None:
        if not isinstance(duration, dict):
            raise ValueError("required_duration must be an object")
        count = duration.get("count")
        if isinstance(count, bool) or not isinstance(count, int) or count < 1:
            raise ValueError("required_duration count must be a positive integer")
        duration = {
            "count": count,
            "unit": _name(duration.get("unit"), "required_duration unit"),
            "consecutive": bool(duration.get("consecutive", False)),
        }
    qualifiers = target.get("qualifiers") or {}
    _require_scalar_mapping(qualifiers, "target qualifiers")
    return {
        "metric": metric,
        "value": value,
        "unit": _optional_text(target.get("unit")),
        "direction": direction,
        "required_duration": duration,
        "qualifiers": qualifiers,
    }


def _normalise_sources(
    sources: list[dict[str, Any]] | None, target: dict[str, Any] | None
) -> list[dict[str, Any]]:
    result = []
    for source in sources or []:
        if not isinstance(source, dict):
            raise TypeError("evidence_sources must contain objects")
        metric = _name(source.get("metric"), "evidence metric")
        role = source.get("role") or (
            "outcome" if target is not None and metric == target["metric"] else "supporting_indicator"
        )
        if role not in ROLES:
            raise ValueError("evidence role must be outcome or supporting_indicator")
        details = source.get("details") or {}
        _require_scalar_mapping(details, "evidence details")
        expectation = source.get("expectation")
        if expectation is not None:
            expectation = _normalise_target({"metric": metric, **expectation})
            expectation.pop("metric")
        result.append(
            {
                "metric": metric,
                "cadence": _name(source.get("cadence"), "evidence cadence"),
                "source": _required_text(source.get("source"), "evidence source"),
                "tracking_status": _name(
                    source.get("tracking_status") or "unspecified", "tracking_status"
                ),
                "role": role,
                "access_notes": _optional_text(source.get("access_notes")),
                "collection_notes": _optional_text(source.get("collection_notes")),
                "expectation": expectation,
                "details": details,
            }
        )
    return result


def _definition_values(definition: dict[str, Any]) -> tuple[Any, ...]:
    return (
        definition["id"],
        definition["domain"],
        definition["display_order"],
        definition["outcome"],
        definition["description"],
        definition["horizon"],
        definition["status"],
        _dump(definition["target"]) if definition["target"] is not None else None,
        _dump(definition["systems"]),
        _dump(definition["dependencies"]),
        _dump(definition["evidence_sources"]),
        _dump(definition["notes"]),
    )


def _goal_from_row(row: Any) -> dict[str, Any]:
    return {
        "id": row["id"],
        "domain": row["domain_id"],
        "domain_name": row["domain_name"],
        "display_order": row["display_order"],
        "outcome": row["outcome"],
        "description": row["description"],
        "horizon": row["horizon"],
        "status": row["status"],
        "target": _load(row["target_json"]),
        "systems": _load(row["systems_json"]),
        "dependencies": _load(row["dependencies_json"]),
        "evidence_sources": _load(row["evidence_sources_json"]),
        "notes": _load(row["notes_json"]),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _require_domain(connection: Any, domain: str) -> None:
    if connection.execute("SELECT 1 FROM domains WHERE id = ?", (domain,)).fetchone() is None:
        raise ValueError("domain not found")


def _required_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} is required")
    return value.strip()


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError("text values must be strings")
    return value.strip() or None


def _name(value: Any, field: str) -> str:
    value = _required_text(value, field)
    if NAME_PATTERN.fullmatch(value) is None:
        raise ValueError(f"{field} must be lower-case words joined by underscores")
    return value


def _statements(values: list[str] | None, field: str) -> list[str]:
    if values is None:
        return []
    if not isinstance(values, list):
        raise TypeError(f"{field} must be a list")
    return [_required_text(value, field) for value in values]


def _identifiers(values: list[str] | None, field: str) -> list[str]:
    values = _statements(values, field)
    if any(ID_PATTERN.fullmatch(value) is None for value in values):
        raise ValueError(f"{field} contains an invalid goal ID")
    return values


def _require_scalar_mapping(value: Any, field: str) -> None:
    if not isinstance(value, dict) or any(
        not isinstance(key, str) or item is not None and not isinstance(item, (str, int, float, bool))
        for key, item in value.items()
    ):
        raise ValueError(f"{field} must contain scalar values")


def _normalise_timing(
    observed_at: str | None, period_start: str | None, period_end: str | None
) -> dict[str, str | None]:
    if observed_at is not None and period_start is None and period_end is None:
        try:
            parsed = datetime.fromisoformat(observed_at)
        except (AttributeError, ValueError) as error:
            raise ValueError("observed_at must be an ISO timestamp") from error
        if parsed.tzinfo is None:
            raise ValueError("observed_at must include a timezone")
        return {
            "observed_at": parsed.astimezone(UTC).isoformat(),
            "period_start": None,
            "period_end": None,
        }
    if observed_at is None and period_start is not None and period_end is not None:
        start = _date(period_start, "period_start")
        end = _date(period_end, "period_end")
        if start > end:
            raise ValueError("period_start must not be after period_end")
        return {
            "observed_at": None,
            "period_start": start.isoformat(),
            "period_end": end.isoformat(),
        }
    raise ValueError("evidence timing requires observed_at or both period_start and period_end")


def _observation_from_row(row: Any) -> dict[str, Any]:
    return {
        "id": row["id"],
        "goal_id": row["goal_id"],
        "metric": row["metric"],
        "value": _load(row["value_json"]),
        "unit": row["unit"],
        "source": row["source"],
        "reference": row["reference"],
        "observed_at": row["observed_at"],
        "period_start": row["period_start"],
        "period_end": row["period_end"],
        "note": row["note"],
        "recorded_at": row["recorded_at"],
        "idempotency_key": row["idempotency_key"],
    }


def _observation_payload(observation: dict[str, Any]) -> dict[str, Any]:
    payload = {
        key: observation[key]
        for key in (
            "goal_id",
            "metric",
            "value",
            "unit",
            "source",
            "reference",
            "observed_at",
            "period_start",
            "period_end",
            "note",
            "idempotency_key",
        )
    }
    payload["value"] = _dump(payload["value"])
    return payload


def _date(value: str, field: str) -> date:
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{field} must be an ISO date") from error


def _limit(value: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError("limit must be an integer")
    if not 1 <= value <= 500:
        raise ValueError("limit must be between 1 and 500")


def _dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _load(value: str | None) -> Any:
    return None if value is None else json.loads(value)


def _now() -> str:
    return datetime.now(UTC).isoformat()


_GOAL_SELECT = """SELECT goals.*, domains.name AS domain_name
                  FROM goals JOIN domains ON domains.id = goals.domain_id"""

PLUGIN = Plugin(
    name="goals",
    icon="goals",
    db_filename=DB_FILENAME,
    migrations=MIGRATIONS,
    register_mcp=register_mcp,
    router=router,
    launcher_summary=launcher_summary,
)
