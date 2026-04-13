# EVH

## Instinct API base

The official Instinct Partner API reference lists the fetch-account endpoint as:

- `GET https://partner.instinctvet.com/v1/accounts/{id}`

Project-local reference copy:

- `docs/instinct-partner-fetch-account.md`

## Instinct import helpers

- `scripts/instinct_import_payload_builder.py`: builds patient payloads with
  default alert and reminder assignments.
- `scripts/instinct_test_account_check.py`: smoke-test utility for validating
  test account connectivity, alert/reminder lookups, and optional patient create
  (supports explicit `--patient-name` and `--patient-pms-id`, with either
  Bearer API key auth or username/password Basic auth).
- `docs/instinct-import.md`: integration notes, endpoint checklist, and test-account commands.
- `scripts/instinct_active_patients_audit.py`: preflight checker for `Active Patients.csv` to verify unique patient identifiers and required mapping fields before bulk import.
- `tests/test_instinct_import_payload_builder.py`: unit tests for payload merge/dedupe behavior.
