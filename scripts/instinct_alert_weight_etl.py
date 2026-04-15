"""ETL for importing Avimark patient weights and cleanly mappable alert IDs.

This script reads `Active_Clients_Alerts.xlsx`, extracts patient-level weight and
alert text fields, maps only conservative alert phrases into Instinct alert IDs,
and writes an ETL log that records the intended or applied changes.

Live apply mode updates only:
- patient `weight`
- patient `alertIds` (merged with existing alerts)

This pass intentionally does not write free-form notes, reminders, or vaccine
history. Those require separate policy decisions.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from urllib import error, parse, request
from xml.etree import ElementTree as ET
from zipfile import ZipFile


XLSX_NS = {"a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
WORKBOOK_HEADERS = {
    "account": "Account",
    "patient_name": "Name",
    "weight": "Weight",
    "alert_text": "Alert Text",
}

ALERT_CATALOG: dict[int, str] = {
    192: "Blind",
    200: "Cat Aggressive",
    209: "Caution - Go Slow",
    214: "Caution - Unpredictable",
    215: "Caution - Will Bite",
    225: "Deaf",
    226: "Diabetic",
    235: "Dog Aggressive",
    246: "FeLV +",
    251: "FIV +",
    262: "Heart Murmur",
    284: "Muzzle for Treatments",
    291: "No Jugular Sticks",
    296: "No Rectal Temps",
    313: "Painful",
}


@dataclass(frozen=True)
class AlertPattern:
    name: str
    regex: re.Pattern[str]
    alert_ids: tuple[int, ...]


ALERT_PATTERNS: tuple[AlertPattern, ...] = (
    AlertPattern("will_bite", re.compile(r"\bwill\s*bite\b|fear biter|may bite|try to bite|biter\b", re.I), (215,)),
    AlertPattern("needs_muzzle", re.compile(r"\bmuzzle\b|needs muzzle|owner muzzles|cannot muzzle", re.I), (284,)),
    AlertPattern("go_slow", re.compile(r"\bgo slow\b", re.I), (209,)),
    AlertPattern("dog_aggressive", re.compile(r"\bdog aggressive\b|animal aggressive", re.I), (235,)),
    AlertPattern("cat_aggressive", re.compile(r"\bcat aggressive\b|go after cats|doesn't like cats\b", re.I), (200,)),
    AlertPattern("blind", re.compile(r"\bblind\b", re.I), (192,)),
    AlertPattern("deaf", re.compile(r"\bdeaf\b", re.I), (225,)),
    AlertPattern("diabetic", re.compile(r"\bdiabetic\b", re.I), (226,)),
    AlertPattern("fiv", re.compile(r"\bfiv\b", re.I), (251,)),
    AlertPattern("felv", re.compile(r"\bfelv\b", re.I), (246,)),
    AlertPattern("heart_murmur", re.compile(r"heart murmur", re.I), (262,)),
    AlertPattern("no_jugular", re.compile(r"no jugular", re.I), (291,)),
    AlertPattern("no_rectal", re.compile(r"no temp|no rectal temp", re.I), (296,)),
    AlertPattern("unpredictable", re.compile(r"\bunpredictable\b", re.I), (214,)),
    AlertPattern("painful", re.compile(r"\bpainful\b", re.I), (313,)),
)


@dataclass(frozen=True)
class WorkbookRow:
    account_pims_code: str
    patient_name: str
    weight: float | None
    alert_text: str
    source_row: int


@dataclass(frozen=True)
class MappedAlertResult:
    alert_ids: tuple[int, ...]
    pattern_names: tuple[str, ...]


def _normalize_text(text: str) -> str:
    return " ".join(text.replace("_x000D_", " ").replace("\r", " ").replace("\n", " ").split())


def map_alert_text(alert_text: str) -> MappedAlertResult:
    ids: list[int] = []
    seen_ids: set[int] = set()
    names: list[str] = []

    for pattern in ALERT_PATTERNS:
        if not pattern.regex.search(alert_text):
            continue
        names.append(pattern.name)
        for alert_id in pattern.alert_ids:
            if alert_id in seen_ids:
                continue
            ids.append(alert_id)
            seen_ids.add(alert_id)

    return MappedAlertResult(alert_ids=tuple(ids), pattern_names=tuple(names))


def _parse_shared_strings(workbook: ZipFile) -> list[str]:
    root = ET.fromstring(workbook.read("xl/sharedStrings.xml"))
    values: list[str] = []
    for item in root.findall("a:si", XLSX_NS):
        values.append("".join((text.text or "") for text in item.iterfind(".//a:t", XLSX_NS)))
    return values


def _cell_value(cell: ET.Element, shared_strings: list[str]) -> str:
    value = cell.find("a:v", XLSX_NS)
    if value is None:
        return ""
    raw = value.text or ""
    if cell.attrib.get("t") == "s":
        return shared_strings[int(raw)]
    return raw


def _column_name(cell_ref: str) -> str:
    return "".join(character for character in cell_ref if character.isalpha())


def load_workbook_rows(path: Path, header_row: int = 4, data_row_start: int = 6) -> list[WorkbookRow]:
    with ZipFile(path) as workbook:
        shared_strings = _parse_shared_strings(workbook)
        sheet = ET.fromstring(workbook.read("xl/worksheets/sheet1.xml"))
        rows = sheet.find("a:sheetData", XLSX_NS)
        if rows is None:
            return []

        header_map: dict[str, str] = {}
        parsed_rows: list[WorkbookRow] = []

        for row in rows.findall("a:row", XLSX_NS):
            row_number = int(row.attrib["r"])
            row_values = {
                _column_name(cell.attrib.get("r", "")): _cell_value(cell, shared_strings)
                for cell in row.findall("a:c", XLSX_NS)
            }

            if row_number == header_row:
                for key, expected_header in WORKBOOK_HEADERS.items():
                    for column_name, value in row_values.items():
                        if value == expected_header:
                            header_map[key] = column_name
                            break
                continue

            if row_number < data_row_start:
                continue

            account_pims_code = row_values.get(header_map["account"], "").strip()
            patient_name = row_values.get(header_map["patient_name"], "").strip()
            raw_weight = row_values.get(header_map["weight"], "").strip()
            alert_text = row_values.get(header_map["alert_text"], "").strip()

            weight = float(raw_weight) if raw_weight else None
            parsed_rows.append(
                WorkbookRow(
                    account_pims_code=account_pims_code,
                    patient_name=patient_name,
                    weight=weight,
                    alert_text=alert_text,
                    source_row=row_number,
                )
            )

        return parsed_rows


@dataclass
class InstinctClient:
    base_url: str
    auth_header: str

    def _request(self, method: str, path: str, body: Mapping[str, object] | None = None) -> dict | list | None:
        headers = {"Accept": "application/json", "Authorization": self.auth_header}
        data = None
        if body is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(body).encode("utf-8")

        req = request.Request(
            url=f"{self.base_url.rstrip('/')}{path}",
            method=method,
            headers=headers,
            data=data,
        )

        with request.urlopen(req, timeout=30) as response:
            raw = response.read().decode("utf-8")
            return json.loads(raw) if raw else None

    def fetch_account_by_pims_code(self, pims_code: str) -> dict | None:
        payload = self._request("GET", f"/v1/accounts?{parse.urlencode({'pimsCode': pims_code})}")
        if not isinstance(payload, dict):
            return None
        data = payload.get("data")
        if not isinstance(data, list):
            return None
        matches = [item for item in data if isinstance(item, dict)]
        if len(matches) != 1:
            return None
        return matches[0]

    def list_patients_for_account(self, account_id: str) -> list[dict]:
        payload = self._request("GET", f"/v1/patients?{parse.urlencode({'accountId': account_id, 'limit': 100})}")
        if not isinstance(payload, dict):
            return []
        data = payload.get("data")
        if not isinstance(data, list):
            return []
        return [item for item in data if isinstance(item, dict)]

    def patch_patient(self, patient_id: int | str, payload: Mapping[str, object]) -> dict:
        response = self._request("PATCH", f"/v1/patients/{patient_id}", payload)
        if not isinstance(response, dict):
            raise RuntimeError(f"Unexpected patient PATCH response for {patient_id}: {response!r}")
        return response


def _fetch_partner_token(auth_url: str, client_id: str, client_secret: str) -> str:
    body = parse.urlencode(
        {
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
        }
    ).encode("utf-8")
    req = request.Request(
        url=auth_url,
        method="POST",
        data=body,
        headers={
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )
    with request.urlopen(req, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))
    token = payload.get("access_token")
    if not isinstance(token, str) or not token:
        raise RuntimeError(f"Token response missing access_token: {payload}")
    return token


def build_patient_patch_payload(patient: Mapping[str, object], mapped_alert_ids: Iterable[int], weight: float | None) -> dict[str, object]:
    existing_alerts = patient.get("alerts")
    merged_alert_ids: list[int] = []
    seen: set[int] = set()

    if isinstance(existing_alerts, list):
        for alert in existing_alerts:
            if not isinstance(alert, Mapping):
                continue
            alert_id = alert.get("id")
            if isinstance(alert_id, int) and alert_id not in seen:
                merged_alert_ids.append(alert_id)
                seen.add(alert_id)

    for alert_id in mapped_alert_ids:
        if alert_id not in seen:
            merged_alert_ids.append(alert_id)
            seen.add(alert_id)

    payload: dict[str, object] = {
        "accountId": patient["accountId"],
        "breedId": patient["breedId"],
        "name": patient["name"],
        "speciesId": patient["speciesId"],
        "alertIds": merged_alert_ids,
    }

    for optional_field in (
        "birthdate",
        "color",
        "deceasedDate",
        "insuranceInfo",
        "microchipInfo",
        "pimsCode",
        "sexId",
    ):
        value = patient.get(optional_field)
        if value is not None:
            payload[optional_field] = value

    if weight is not None:
        payload["weight"] = weight
    elif patient.get("weight") is not None:
        payload["weight"] = patient["weight"]

    return payload


def _log_row(
    row: WorkbookRow,
    mapped_alerts: MappedAlertResult,
    status: str,
    *,
    account_id: str | None = None,
    patient_id: int | str | None = None,
    applied_weight: float | None = None,
    error_text: str | None = None,
) -> dict[str, object]:
    return {
        "source_row": row.source_row,
        "account_pims_code": row.account_pims_code,
        "patient_name": row.patient_name,
        "weight": row.weight,
        "alert_text": row.alert_text,
        "mapped_alert_ids": list(mapped_alerts.alert_ids),
        "mapped_alert_labels": [ALERT_CATALOG[alert_id] for alert_id in mapped_alerts.alert_ids],
        "matched_patterns": list(mapped_alerts.pattern_names),
        "status": status,
        "account_id": account_id,
        "patient_id": patient_id,
        "applied_weight": applied_weight,
        "error": error_text,
    }


def _etl_paths(output_dir: Path) -> dict[str, Path]:
    return {
        "jsonl": output_dir / "instinct_weight_alert_etl.jsonl",
        "summary": output_dir / "instinct_weight_alert_etl_summary.json",
        "csv": output_dir / "instinct_weight_alert_etl.csv",
    }


def init_etl_logs(output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = _etl_paths(output_dir)
    paths["jsonl"].write_text("", encoding="utf-8")
    paths["summary"].write_text(
        json.dumps(
            {
                "total_logged_rows": 0,
                "status_counts": {},
                "jsonl_path": str(paths["jsonl"]),
                "csv_path": str(paths["csv"]),
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def append_etl_record(output_dir: Path, record: dict[str, object], records: list[dict[str, object]]) -> None:
    paths = _etl_paths(output_dir)
    with paths["jsonl"].open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=True) + "\n")

    status_counts = Counter(str(item["status"]) for item in records)
    paths["summary"].write_text(
        json.dumps(
            {
                "total_logged_rows": len(records),
                "status_counts": dict(status_counts),
                "jsonl_path": str(paths["jsonl"]),
                "csv_path": str(paths["csv"]),
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def write_etl_logs(output_dir: Path, records: list[dict[str, object]]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = _etl_paths(output_dir)["csv"]

    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        fieldnames = [
            "source_row",
            "account_pims_code",
            "patient_name",
            "weight",
            "mapped_alert_ids",
            "mapped_alert_labels",
            "status",
            "account_id",
            "patient_id",
            "error",
        ]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for record in records:
            writer.writerow(
                {
                    "source_row": record["source_row"],
                    "account_pims_code": record["account_pims_code"],
                    "patient_name": record["patient_name"],
                    "weight": record["weight"],
                    "mapped_alert_ids": ",".join(str(alert_id) for alert_id in record["mapped_alert_ids"]),
                    "mapped_alert_labels": " | ".join(record["mapped_alert_labels"]),
                    "status": record["status"],
                    "account_id": record["account_id"],
                    "patient_id": record["patient_id"],
                    "error": record["error"],
                }
            )


def _build_client(args: argparse.Namespace) -> InstinctClient:
    if args.api_key:
        return InstinctClient(base_url=args.base_url, auth_header=f"Bearer {args.api_key}")

    token = _fetch_partner_token(args.auth_url, args.client_id, args.client_secret)
    return InstinctClient(base_url=args.base_url, auth_header=f"Bearer {token}")


def run_etl(args: argparse.Namespace) -> list[dict[str, object]]:
    rows = load_workbook_rows(Path(args.xlsx))
    relevant_rows = [
        row
        for row in rows
        if row.patient_name and row.account_pims_code and (row.weight is not None or row.alert_text)
    ]

    client = _build_client(args) if args.apply else None
    account_by_pims_code: dict[str, dict | None] = {}
    patients_by_account_and_name: dict[tuple[str, str], list[dict]] = {}

    records: list[dict[str, object]] = []
    output_dir = Path(args.output_dir)
    init_etl_logs(output_dir)

    def record_result(record: dict[str, object]) -> None:
        records.append(record)
        append_etl_record(output_dir, record, records)

    for row in relevant_rows:
        mapped = map_alert_text(_normalize_text(row.alert_text))
        if row.weight is None and not mapped.alert_ids:
            continue

        if client is None:
            record_result(_log_row(row, mapped, "planned"))
            continue

        if row.account_pims_code not in account_by_pims_code:
            account_by_pims_code[row.account_pims_code] = client.fetch_account_by_pims_code(row.account_pims_code)

        account = account_by_pims_code.get(row.account_pims_code)
        if account is None:
            record_result(_log_row(row, mapped, "skipped_missing_account", error_text="No Instinct account match by pimsCode"))
            continue

        account_id = str(account["id"])
        key = (account_id, row.patient_name.casefold())
        if key not in patients_by_account_and_name:
            patient_rows = client.list_patients_for_account(account_id)
            name_map: dict[str, list[dict]] = {}
            for patient in patient_rows:
                patient_name = patient.get("name")
                if isinstance(patient_name, str):
                    name_map.setdefault(patient_name.casefold(), []).append(patient)
            patients_by_account_and_name[key] = name_map.get(row.patient_name.casefold(), [])

        matching_patients = patients_by_account_and_name[key]
        if not matching_patients:
            record_result(_log_row(row, mapped, "skipped_missing_patient", account_id=account_id, error_text="No patient match by exact name"))
            continue
        if len(matching_patients) > 1:
            record_result(_log_row(row, mapped, "skipped_ambiguous_patient", account_id=account_id, error_text="Multiple patient matches by exact name"))
            continue

        patient = matching_patients[0]
        patient_id = patient.get("id")
        if patient_id is None:
            record_result(_log_row(row, mapped, "skipped_invalid_patient", account_id=account_id, error_text="Patient row missing id"))
            continue

        payload = build_patient_patch_payload(patient, mapped.alert_ids, row.weight)
        current_weight = patient.get("weight")
        existing_alert_ids = []
        for alert in patient.get("alerts", []):
            if isinstance(alert, Mapping) and isinstance(alert.get("id"), int):
                existing_alert_ids.append(alert["id"])

        if current_weight == row.weight and all(alert_id in existing_alert_ids for alert_id in mapped.alert_ids):
            record_result(_log_row(row, mapped, "unchanged", account_id=account_id, patient_id=patient_id, applied_weight=row.weight))
            continue

        try:
            client.patch_patient(patient_id, payload)
        except error.HTTPError as exc:
            body = exc.read().decode("utf-8")
            record_result(_log_row(row, mapped, "failed_patch", account_id=account_id, patient_id=patient_id, error_text=f"HTTP {exc.code}: {body}"))
            continue

        record_result(_log_row(row, mapped, "applied", account_id=account_id, patient_id=patient_id, applied_weight=row.weight))

    return records


def main() -> int:
    parser = argparse.ArgumentParser(description="ETL Avimark weight and cleanly mappable alert IDs into Instinct")
    parser.add_argument("--xlsx", required=True, help="Path to Active_Clients_Alerts.xlsx")
    parser.add_argument("--output-dir", default="etl_logs", help="Directory for ETL log output")
    parser.add_argument("--apply", action="store_true", help="Apply live patient updates to Instinct")
    parser.add_argument("--base-url", default="https://partner.instinctvet.com", help="Instinct Partner API base URL")
    parser.add_argument("--api-key", help="Bearer token for Instinct Partner API")
    parser.add_argument("--client-id", help="OAuth client_id")
    parser.add_argument("--client-secret", help="OAuth client_secret")
    parser.add_argument(
        "--auth-url",
        default="https://partner.instinctvet.com/v1/auth/token",
        help="OAuth token endpoint",
    )
    args = parser.parse_args()

    if args.apply and not (args.api_key or (args.client_id and args.client_secret)):
        parser.error("--apply requires either --api-key or --client-id/--client-secret.")

    records = run_etl(args)
    write_etl_logs(Path(args.output_dir), records)
    print(f"Logged {len(records)} ETL records to {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
