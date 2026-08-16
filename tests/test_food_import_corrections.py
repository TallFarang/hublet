from __future__ import annotations

from pathlib import Path

import pytest

from app.config import Settings
from app.plugins.food import query_records
from app.plugins.food_import import import_csvs
from tests.food_import_fixtures import catalogue_row, ledger_row, write_csv


def test_importer_collapses_multistep_correction_to_root_id(
    settings_env: dict[str, str], tmp_path: Path
) -> None:
    settings = Settings.from_env(settings_env)
    ledger, catalogue = tmp_path / "ledger.csv", tmp_path / "catalogue.csv"
    rows = [
        ledger_row(
            "grab-order-1-1", status="uncertain", consumption_datetime="", calories="550"
        ),
        ledger_row(
            "confirm-order-1-1",
            calories="550",
            notes="Confirmed; supersedes uncertain source row",
        ),
        ledger_row(
            "correction-order-1-final",
            calories="405.9",
            calories_low="",
            calories_high="",
            protein_g="20",
            carbs_g="50",
            fat_g="12",
            notes="Published correction supersedes confirm-order-1-1",
        ),
    ]
    write_csv(ledger, rows)
    write_csv(catalogue, [catalogue_row()])

    result = import_csvs(settings, ledger, catalogue)
    records = query_records(settings)

    assert result["source_record_count"] == 3
    assert result["canonical_record_count"] == 1
    assert result["collapsed_revision_count"] == 2
    assert result["status_counts"] == {"eaten": 1}
    assert result["confirmed_daily_totals"]["2026-08-09"]["calories"] == 405.9
    assert len(records) == 1
    assert records[0]["id"] == "grab-order-1-1"
    assert records[0]["calculated_nutrition"]["calories"] == 405.9
    assert records[0]["update_reason"].startswith("Published correction")


def test_importer_applies_aggregate_exclusion_to_unclaimed_roots(
    settings_env: dict[str, str], tmp_path: Path
) -> None:
    settings = Settings.from_env(settings_env)
    ledger, catalogue = tmp_path / "ledger.csv", tmp_path / "catalogue.csv"
    rows = [
        ledger_row(
            f"grab-bulk-{position}",
            order_id="bulk",
            status="uncertain",
            notes="Superseded after clarification" if position == 2 else "",
        )
        for position in range(1, 4)
    ]
    rows.extend(
        [
            ledger_row(
                "confirm-bulk-1",
                order_id="bulk",
                notes="Confirmed; supersedes uncertain source row",
            ),
            ledger_row(
                "exclude-bulk-remainder",
                order_id="bulk",
                item="Remaining items",
                status="excluded",
                notes="Excludes remaining items; supersedes remaining uncertain source rows",
            ),
            ledger_row(
                "standalone-confirm",
                order_id="standalone",
                notes="A standalone confirmed meal",
            ),
        ]
    )
    write_csv(ledger, rows)
    write_csv(catalogue, [catalogue_row()])

    result = import_csvs(settings, ledger, catalogue)
    records = {record["id"]: record for record in query_records(settings)}

    assert result["canonical_record_count"] == 4
    assert result["status_counts"] == {"eaten": 2, "excluded": 2}
    assert records["grab-bulk-1"]["status"] == "eaten"
    assert records["grab-bulk-2"]["status"] == records["grab-bulk-3"]["status"] == "excluded"
    assert records["grab-bulk-2"]["item"] == "Rice bowl"
    assert "standalone-confirm" in records


def test_importer_refuses_ambiguous_superseding_rows(
    settings_env: dict[str, str], tmp_path: Path
) -> None:
    settings = Settings.from_env(settings_env)
    ledger, catalogue = tmp_path / "ledger.csv", tmp_path / "catalogue.csv"
    rows = [
        ledger_row("manual-1", order_id="manual", status="uncertain", item="First"),
        ledger_row("manual-2", order_id="manual", status="uncertain", item="Second"),
        ledger_row(
            "correction-manual",
            order_id="manual",
            item="Different",
            notes="This supersedes an earlier row",
        ),
    ]
    write_csv(ledger, rows)
    write_csv(catalogue, [catalogue_row()])

    with pytest.raises(ValueError, match="ambiguous superseding"):
        import_csvs(settings, ledger, catalogue, check=True)
