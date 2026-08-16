from __future__ import annotations

from pathlib import Path

import pytest

from app.config import Settings
from app.plugins.food import DB_FILENAME, query_records
from app.plugins.food_import import import_csvs
from tests.food_import_fixtures import catalogue_row, ledger_row, write_csv


def test_importer_preserves_ids_totals_variants_and_sources(
    settings_env: dict[str, str], tmp_path: Path
) -> None:
    settings = Settings.from_env(settings_env)
    ledger, catalogue = tmp_path / "ledger.csv", tmp_path / "catalogue.csv"
    write_csv(
        catalogue,
        [
            catalogue_row(),
            catalogue_row(
                Item="Large platter",
                Calories="1,200",
                **{"Calories Low": "", "Calories High": "", "Portion Basis": "one platter"},
            ),
        ],
    )
    write_csv(
        ledger,
        [
            ledger_row(
                "legacy-1",
                calories="300",
                calories_low="",
                calories_high="",
                protein_g="15",
                carbs_g="37.5",
                fat_g="10",
                apple_health_export_id="export-1",
            ),
            ledger_row(
                "legacy-2",
                purchase_datetime="2026-08-10T11:00:00+07:00",
                consumption_datetime="2026-08-10T12:00:00+07:00",
                calories="650",
                calories_low="",
                calories_high="",
                protein_g="32",
                carbs_g="80",
                fat_g="21",
                quantity_ordered="0.5 bottle",
                portion_consumed="legacy larger bowl",
            ),
        ],
    )
    before = ledger.read_bytes(), catalogue.read_bytes()

    checked = import_csvs(settings, ledger, catalogue, check=True)
    result = import_csvs(settings, ledger, catalogue)
    records = query_records(settings)

    assert checked["check_only"] is True
    assert result["source_record_count"] == result["canonical_record_count"] == 2
    assert result["legacy_nutrition_count"] == 2
    assert {record["id"] for record in records} == {"legacy-1", "legacy-2"}
    assert {record["calculated_nutrition"]["calories"] for record in records} == {300, 650}
    assert next(row for row in records if row["id"] == "legacy-1")[
        "apple_health_reference"
    ] == "export-1"
    assert next(row for row in records if row["id"] == "legacy-2")["quantity"] == 0.5
    assert (ledger.read_bytes(), catalogue.read_bytes()) == before


def test_importer_refuses_nonempty_database_and_bad_headers(
    settings_env: dict[str, str], tmp_path: Path
) -> None:
    settings = Settings.from_env(settings_env)
    ledger, catalogue = tmp_path / "ledger.csv", tmp_path / "catalogue.csv"
    write_csv(ledger, [ledger_row("record-1")])
    write_csv(catalogue, [catalogue_row()])
    import_csvs(settings, ledger, catalogue)

    with pytest.raises(ValueError, match="must be empty"):
        import_csvs(settings, ledger, catalogue)

    write_csv(ledger, [{"ID": "wrong-schema"}])
    with pytest.raises(ValueError, match="unexpected ledger.csv headers"):
        import_csvs(settings, ledger, catalogue, database=tmp_path / "other.db")


def test_importer_can_target_an_explicit_empty_database(
    settings_env: dict[str, str], tmp_path: Path
) -> None:
    settings = Settings.from_env(settings_env)
    ledger, catalogue = tmp_path / "ledger.csv", tmp_path / "catalogue.csv"
    candidate = tmp_path / "candidate.db"
    write_csv(ledger, [ledger_row("record-1")])
    write_csv(catalogue, [catalogue_row()])

    import_csvs(settings, ledger, catalogue, database=candidate)

    assert candidate.exists()
    assert not (settings.data_dir / DB_FILENAME).exists()
