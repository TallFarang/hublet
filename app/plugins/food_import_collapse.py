"""Collapse append-only legacy correction rows into canonical records."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from app.plugins.food_import_csv import normal, required, value

REVISION_PREFIXES = ("confirm-", "correction-", "exclude-")
PROVENANCE_FIELDS = {"record_id", "order_id", "purchase_datetime"}
AGGREGATE_FIELDS = {
    "consumption_datetime", "meal_slot", "portion_consumed", "status", "notes", "updated_at",
    "apple_health_export_id", "apple_health_exported_at",
}


def collapse_corrections(
    rows: list[dict[str, str]],
) -> tuple[list[dict[str, str]], dict[str, Any]]:
    """Return final canonical rows and a deterministic collapse report."""

    by_id: dict[str, dict[str, str]] = {}
    positions: dict[str, int] = {}
    for position, row in enumerate(rows):
        record_id = required(row, "record_id")
        if record_id in by_id:
            raise ValueError(f"duplicate ledger record ID: {record_id}")
        by_id[record_id], positions[record_id] = row, position
    parents: dict[str, str] = {}
    aggregates: list[str] = []
    for record_id, row in by_id.items():
        if _is_aggregate(record_id, row):
            aggregates.append(record_id)
            continue
        if not _claims_revision(record_id, row):
            continue
        referenced = _referenced_id(row, by_id)
        if referenced is not None:
            parents[record_id] = referenced
            continue
        prefix_parent = _prefix_parent(record_id, by_id)
        if prefix_parent is not None:
            parents[record_id] = prefix_parent

    roots_by_order = _base_roots(by_id, parents, aggregates)
    for record_id, row in by_id.items():
        if record_id in parents or record_id in aggregates or not _claims_revision(record_id, row):
            continue
        candidates = roots_by_order.get(value(row, "order_id"), [])
        matches = [
            root for root in candidates if normal(required(by_id[root], "item")) == normal(required(row, "item"))
        ]
        if len(matches) == 1:
            parents[record_id] = matches[0]
        elif len(candidates) == 1:
            parents[record_id] = candidates[0]
        else:
            raise ValueError(f"ambiguous superseding ledger row: {record_id}")

    assignments: dict[str, list[str]] = defaultdict(list)
    for child in sorted(parents, key=positions.get):
        assignments[_root_id(child, parents)].append(child)
    for aggregate_id in aggregates:
        aggregate = by_id[aggregate_id]
        order_id = value(aggregate, "order_id")
        candidates = [
            root for root in roots_by_order.get(order_id, [])
            if required(by_id[root], "status").casefold() == "uncertain" and root not in assignments
        ]
        if not candidates:
            raise ValueError(f"aggregate exclusion has no unmatched uncertain rows: {aggregate_id}")
        for root in candidates:
            assignments[root].append(aggregate_id)

    dropped = set(parents) | set(aggregates)
    canonical = []
    for record_id, row in by_id.items():
        if record_id in dropped:
            continue
        merged = dict(row)
        for revision_id in assignments.get(record_id, []):
            revision = by_id[revision_id]
            fields = AGGREGATE_FIELDS if revision_id in aggregates else set(revision) - PROVENANCE_FIELDS
            for field in fields:
                if revision_id not in aggregates or revision.get(field, "").strip():
                    merged[field] = revision[field]
            merged["update_reason"] = value(revision, "notes") or "legacy correction import"
        canonical.append(merged)
    return canonical, {
        "source_record_count": len(rows),
        "canonical_record_count": len(canonical),
        "collapsed_revision_count": len(dropped),
        "collapsed_revision_ids": sorted(dropped),
    }


def _base_roots(
    rows: dict[str, dict[str, str]], parents: dict[str, str], aggregates: list[str]
) -> dict[str | None, list[str]]:
    roots: dict[str | None, list[str]] = defaultdict(list)
    dropped = set(parents) | set(aggregates)
    for record_id, row in rows.items():
        if record_id not in dropped and not _claims_revision(record_id, row):
            roots[value(row, "order_id")].append(record_id)
    return roots


def _claims_revision(record_id: str, row: dict[str, str]) -> bool:
    notes = (value(row, "notes") or "").casefold()
    return record_id.startswith("correction-") or (
        record_id.startswith(("confirm-", "exclude-")) and "supersed" in notes
    )


def _is_aggregate(record_id: str, row: dict[str, str]) -> bool:
    notes = (value(row, "notes") or "").casefold()
    return record_id.startswith("exclude-") and record_id.endswith("-remainder") and "remaining" in notes


def _referenced_id(row: dict[str, str], rows: dict[str, dict[str, str]]) -> str | None:
    notes = value(row, "notes") or ""
    matches = [record_id for record_id in rows if record_id != row["record_id"] and record_id in notes]
    if len(matches) > 1:
        raise ValueError(f"correction references multiple record IDs: {row['record_id']}")
    return matches[0] if matches else None


def _prefix_parent(record_id: str, rows: dict[str, dict[str, str]]) -> str | None:
    if record_id.startswith(("confirm-", "exclude-")):
        candidate = "grab-" + record_id.split("-", 1)[1]
        return candidate if candidate in rows else None
    return None


def _root_id(record_id: str, parents: dict[str, str]) -> str:
    seen = set()
    while record_id in parents:
        if record_id in seen:
            raise ValueError("legacy correction chain contains a cycle")
        seen.add(record_id)
        record_id = parents[record_id]
    return record_id
