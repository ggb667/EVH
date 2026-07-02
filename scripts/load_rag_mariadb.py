from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import time
from pathlib import Path
from typing import Iterable


DEFAULT_CLUSTER_ARN = os.environ.get("DB_CLUSTER_ARN", "")
DEFAULT_SECRET_ARN = os.environ.get("DB_SECRET_ARN", "")
DEFAULT_DATABASE = os.environ.get("DB_NAME", "")


def _run_aws(args: list[str], *, input_text: str | None = None) -> str:
    proc = subprocess.run(
        ["aws", *args],
        input=input_text,
        text=True,
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        raise SystemExit(proc.stderr.strip() or proc.stdout.strip() or "aws command failed")
    return proc.stdout


def _execute_statement(cluster_arn: str, secret_arn: str, database: str, sql: str) -> None:
    attempts = 0
    while True:
        attempts += 1
        proc = subprocess.run(
            [
                "aws",
                "rds-data",
                "execute-statement",
                "--resource-arn",
                cluster_arn,
                "--secret-arn",
                secret_arn,
                "--database",
                database,
                "--sql",
                sql,
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        if proc.returncode == 0:
            return
        message = (proc.stderr or proc.stdout or "").strip()
        if "DatabaseResumingException" in message and attempts < 12:
            time.sleep(min(30, attempts * 3))
            continue
        raise SystemExit(message or "aws execute-statement failed")


def _quote_sql(value: str) -> str:
    return "'" + value.replace("\\", "\\\\").replace("'", "''") + "'"


def _aliases_json(text: str) -> str:
    if not text.strip():
        return "[]"
    aliases = [alias.strip() for alias in text.split("|") if alias.strip()]
    return json.dumps(aliases, ensure_ascii=False, separators=(",", ":"))


def _dictionary_params(row: dict[str, str]) -> list[dict[str, object]]:
    category = row["category"].strip()
    category_value: dict[str, object]
    if category:
        category_value = {"stringValue": category}
    else:
        category_value = {"isNull": True}
    return [
        {"name": "term_type", "value": {"stringValue": row["term_type"]}},
        {"name": "canonical_name", "value": {"stringValue": row["canonical_name"]}},
        {"name": "aliases", "value": {"stringValue": _aliases_json(row["aliases"])}},
        {"name": "category", "value": category_value},
        {"name": "active", "value": {"booleanValue": row["active"].strip().lower() == "true"}},
        {"name": "priority_score", "value": {"longValue": int(row["priority"])}},
        {"name": "confidence_score", "value": {"doubleValue": float(row["confidence"])}},
        {"name": "metadata_json", "value": {"stringValue": row["metadata_json"]}},
    ]


def _load_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
        if reader.fieldnames is None:
            raise SystemExit(f"Missing header row in {path}")
        return reader.fieldnames, rows


def _sql_value(field: str, row: dict[str, str]) -> str:
    value = row.get(field, "")
    if value == "":
        return "NULL"
    return _quote_sql(value)


def _chunked(items: list[dict[str, str]], size: int) -> Iterable[list[dict[str, str]]]:
    for i in range(0, len(items), size):
        yield items[i : i + size]


def load_schema(cluster_arn: str, secret_arn: str, database: str, schema_path: Path) -> None:
    sql = schema_path.read_text(encoding="utf-8")
    statements = [stmt.strip() for stmt in sql.split(";") if stmt.strip()]
    for stmt in statements:
        _execute_statement(cluster_arn, secret_arn, database, stmt)


def load_dictionary(cluster_arn: str, secret_arn: str, database: str, csv_path: Path) -> int:
    _, rows = _load_csv(csv_path)
    _execute_statement(cluster_arn, secret_arn, database, "DELETE FROM rag_dictionary_term_alias")
    _execute_statement(cluster_arn, secret_arn, database, "DELETE FROM rag_dictionary_term")
    inserted = 0
    sql = (
        "INSERT INTO rag_dictionary_term "
        "(term_type, canonical_name, aliases, category, active, priority_score, confidence_score, metadata_json) "
        "VALUES (:term_type, :canonical_name, CAST(:aliases AS JSON), NULLIF(:category, ''), :active, :priority_score, :confidence_score, CAST(:metadata_json AS JSON)) "
        "ON DUPLICATE KEY UPDATE "
        "aliases=VALUES(aliases), category=VALUES(category), active=VALUES(active), "
        "priority_score=VALUES(priority_score), confidence_score=VALUES(confidence_score), metadata_json=VALUES(metadata_json)"
    )
    for batch in _chunked(rows, 100):
        parameter_sets = [_dictionary_params(row) for row in batch]
        payload = {
            "resourceArn": cluster_arn,
            "secretArn": secret_arn,
            "database": database,
            "sql": sql,
            "parameterSets": parameter_sets,
        }
        _run_aws(["rds-data", "batch-execute-statement", "--cli-input-json", json.dumps(payload)])
        inserted += len(batch)
    return inserted


def count_rows(cluster_arn: str, secret_arn: str, database: str, table: str) -> int:
    output = _run_aws(
        [
            "rds-data",
            "execute-statement",
            "--resource-arn",
            cluster_arn,
            "--secret-arn",
            secret_arn,
            "--database",
            database,
            "--sql",
            f"SELECT COUNT(*) AS count FROM {table}",
        ]
    )
    data = json.loads(output)
    records = data.get("records") or []
    if not records:
        return 0
    return int(records[0][0].get("longValue", 0))


def main() -> int:
    parser = argparse.ArgumentParser(description="Load EVH RAG seed data into MariaDB via the AWS RDS Data API.")
    parser.add_argument("--cluster-arn", default=DEFAULT_CLUSTER_ARN, required=not DEFAULT_CLUSTER_ARN)
    parser.add_argument("--secret-arn", default=DEFAULT_SECRET_ARN, required=not DEFAULT_SECRET_ARN)
    parser.add_argument("--database", default=DEFAULT_DATABASE, required=not DEFAULT_DATABASE)
    parser.add_argument(
        "--schema",
        default=Path("db/rag_dictionary_schema.sql"),
        type=Path,
    )
    parser.add_argument(
        "--dictionary-csv",
        default=Path("db/rag_dictionary_term_seed_merged.csv"),
        type=Path,
    )
    args = parser.parse_args()

    cluster_arn = args.cluster_arn
    secret_arn = args.secret_arn
    database = args.database
    schema_path = args.schema
    dictionary_csv = args.dictionary_csv

    if not schema_path.exists():
        raise SystemExit(f"Schema file not found: {schema_path}")
    if not dictionary_csv.exists():
        raise SystemExit(f"Dictionary CSV not found: {dictionary_csv}")

    load_schema(cluster_arn, secret_arn, database, schema_path)
    loaded = load_dictionary(cluster_arn, secret_arn, database, dictionary_csv)
    count = count_rows(cluster_arn, secret_arn, database, "rag_dictionary_term")
    print(f"loaded {loaded} dictionary rows")
    print(f"verified rag_dictionary_term count={count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
