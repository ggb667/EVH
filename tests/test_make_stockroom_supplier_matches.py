import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.make_stockroom_supplier_matches import (
    EXPECTED_COLUMNS,
    canonicalize_suppliers,
    load_stockroom_rows,
    load_supplier_canonical_map,
    split_ids,
)


def make_row(values: list[str]) -> list[str]:
    row = [""] * EXPECTED_COLUMNS
    row[: len(values)] = values
    return row


def test_split_ids_handles_slash_and_whitespace():
    assert split_ids("6735 / 603916") == ["6735", "603916"]


def test_load_stockroom_rows_accepts_quoted_commas_and_keeps_width(tmp_path: Path):
    src = tmp_path / "stockroom.csv"
    rows = [
        make_row(
            [
                "",
                "ABC",
                'Item with "quoted, comma" inside',
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
            ]
        ),
        make_row(
            [
                "",
                "DEF",
                "Another line",
            ]
        ),
    ]
    with src.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "actions",
                "PIMS ID",
                "Product",
                "Suppliers",
                "Inventory Tags",
                "Manufacturer",
                "Buying Unit",
                "Selling Unit",
                "Buying Cost",
                "Fixed Price",
                "Non Billable",
                "Markup",
                "Selling Price",
                "Dispensing Fee",
                "Location",
                "Priority",
                "QOH Min",
                "QOH Max",
            ]
        )
        writer.writerows(rows)

    header, loaded, duplicates = load_stockroom_rows(src)

    assert len(header) == EXPECTED_COLUMNS
    assert len(loaded) == 2
    assert loaded[0]["Product"] == 'Item with "quoted, comma" inside'
    assert duplicates == {}


def test_load_stockroom_rows_rejects_duplicate_descriptions(tmp_path: Path):
    src = tmp_path / "stockroom.csv"
    with src.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "actions",
                "PIMS ID",
                "Product",
                "Suppliers",
                "Inventory Tags",
                "Manufacturer",
                "Buying Unit",
                "Selling Unit",
                "Buying Cost",
                "Fixed Price",
                "Non Billable",
                "Markup",
                "Selling Price",
                "Dispensing Fee",
                "Location",
                "Priority",
                "QOH Min",
                "QOH Max",
            ]
        )
        writer.writerow(make_row(["", "ABC", "Duplicate", "", "", "", "", "", "", "", "", "", "", "", "", "", "", ""]))
        writer.writerow(make_row(["", "DEF", "Duplicate", "", "", "", "", "", "", "", "", "", "", "", "", "", "", ""]))

    _, _, duplicates = load_stockroom_rows(src)

    assert duplicates == {"Duplicate": [2, 3]}


def test_canonicalize_suppliers_resolves_patterson_variants(tmp_path: Path):
    suppliers_csv = tmp_path / "stockroom_suppliers_ids.csv"
    with suppliers_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["id", "code", "label", "notes"])
        writer.writerow(["1", "MWI", "MWI Veterinary Supply", ""])
        writer.writerow(["2", "PATL", "Patterson Veterinary Supply", ""])
        writer.writerow(["3", "PATT", "Patterson Office Supply", ""])
        writer.writerow(["4", "WEB", "Patterson Vet Webster", ""])
        writer.writerow(["5", "PUR", "Purina Pet Care MWI", ""])
        writer.writerow(["6", "PZR", "Zoetis/Pfizer Inc", ""])

    canonical_map = load_supplier_canonical_map(suppliers_csv)
    assert canonicalize_suppliers(
        {
            "MWI Veterinary Supply",
            "Patterson Veterinary Supp",
            "Patterson Vet (Webster)",
            "Purina Pet Care/MWI",
            "Zoetis/Pfizer Inc.",
        },
        canonical_map,
    ) == [
        "MWI Veterinary Supply",
        "Patterson Vet Webster",
        "Patterson Veterinary Supply",
        "Purina Pet Care MWI",
        "Zoetis/Pfizer Inc",
    ]
