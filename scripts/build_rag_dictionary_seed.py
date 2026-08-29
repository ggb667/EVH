from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


OUT_COLUMNS = [
    "term_type",
    "canonical_name",
    "aliases",
    "category",
    "active",
    "priority",
    "confidence",
    "metadata_json",
]


def _split_aliases(value: str) -> str:
    if not value:
        return ""
    return value


def load_rarity_csv(path: Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            rows.append(
                {
                    "term_type": row["term_type"].strip(),
                    "canonical_name": row["canonical_name"].strip(),
                    "aliases": _split_aliases(row.get("aliases", "").strip()),
                    "category": row.get("category", "").strip(),
                    "active": row.get("active", "true").strip().lower(),
                    "priority": row.get("priority", "1").strip(),
                    "confidence": row.get("confidence", "1.0").strip(),
                    "metadata_json": row.get("metadata_json", "{}").strip(),
                }
            )
    return rows


def load_vet_taxonomy_md(path: Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    in_table = False
    with path.open(encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.rstrip("\n")
            if line.startswith("| term_type |"):
                in_table = True
                continue
            if not in_table:
                continue
            if not line.startswith("|"):
                break
            parts = [part.strip() for part in line.strip("|").split("|")]
            if len(parts) != 6 or parts[0] == "---":
                continue
            term_type, canonical_name, aliases, category, source_note, active = parts
            if term_type not in {"vet_term", "treatment", "medication"}:
                continue
            rows.append(
                {
                    "term_type": term_type,
                    "canonical_name": canonical_name,
                    "aliases": aliases,
                    "category": category,
                    "active": active.lower(),
                    "priority": "50",
                    "confidence": "0.95",
                    "metadata_json": json.dumps(
                        {
                            "source_system": "fluttershy-vet-taxonomy",
                            "source_file": str(path.name),
                            "source_note": source_note,
                        },
                        separators=(",", ":"),
                    ),
                }
            )
    return rows


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=OUT_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--vet-taxonomy", required=True)
    parser.add_argument("--stockroom-csv", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    vet_rows = load_vet_taxonomy_md(Path(args.vet_taxonomy))
    stock_rows = load_rarity_csv(Path(args.stockroom_csv))
    write_csv(Path(args.output), vet_rows + stock_rows)
    print(f"wrote {len(vet_rows) + len(stock_rows)} rows to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
