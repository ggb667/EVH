# EVH

## Instinct API base

The official Instinct Partner API reference lists the fetch-account endpoint as:

- `GET https://partner.instinctvet.com/v1/accounts/{id}`

Project-local reference copy:

- `docs/instinct-partner-fetch-account.md`

Primary Partner API base:

- `https://partner.instinctvet.com`

Token endpoint used by the local scripts:

- `POST https://partner.instinctvet.com/v1/auth/token`

## Environment and setup

This repo currently uses the local virtualenv at `.venv`.

Install the spreadsheet dependency before reading `.xlsx` reminder files:

```bash
.venv/bin/pip install openpyxl
```

Run tests with:

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest --basetemp=/tmp/evh-pytest tests
```

## Identifier rules

Instinct uses multiple IDs for related records. Do not treat them as interchangeable.

- `account.id`: Instinct internal UUID for the client/account record.
- `account.pimsCode`: external account/client code from the source system.
- `account.pimsId`: optional stable external account ID. It may be `null`.
- `patient.id`: Instinct internal numeric patient ID.
- `patient.pimsCode`: external patient PMS/PIMS code from the source system.

Example from the live reminder investigation:

- owner/account: `Nathan Deschenes`
- account `pimsCode`: `9758`
- patient name: `Max`
- patient internal Instinct ID: `16558`
- patient `pimsCode`: `25038`

That means `GET /v1/patients/25038` is wrong for Max. `25038` is the patient's external `pimsCode`, not the internal Instinct patient ID.

Live smoke-test results:

- `GET /v1/accounts/{id}` returns `200` with the partner token.
- `GET /v1/appointments` returns `200` with the partner token.
- `GET /v1/appointment-types` returns `200` with the partner token.
- `GET /v1/reminders` must be read with cursor paging from `metadata.after` and `pageDirection=after` in the live tenant.

## Relevant API locations

- `GET /v1/accounts/{id}`: fetch one Instinct account by internal UUID.
- `GET /v1/accounts?pimsCode=...`: resolve an external client/account code.
- `GET /v1/accounts?pimsId=...`: resolve an external stable account ID when present.
- `GET /v1/accounts?name=...`: fallback owner/account search by contact name.
- `GET /v1/patients/{id}`: fetch one patient by internal Instinct patient ID.
- `GET /v1/patients?pimsCode=...`: resolve a patient from an external patient PMS/PIMS code.
- `GET /v1/patients?accountId=...`: list patients for a resolved account.
- `GET /v1/alerts`: discover live alert IDs.
- `GET /v1/reminders`: discover live reminder rows and reminder-label IDs exposed by the tenant.
- `GET /v1/appointments`: discover live appointments for the tenant.
- `GET /v1/appointment-types`: discover live appointment type metadata.
- `POST /v1/patients`: create a patient.
- `PATCH /v1/patients/{id}`: update a patient.

## Reminder API finding

The current EVH investigation confirmed that `GET /v1/reminders` returns raw reminder rows with fields such as:

- `patientId`
- `ownerId`
- `productId`
- `reminderLabelId`
- `dueAt`
- `givenAt`
- `deactivatedAt`

However, for the tested patient/account context above, the Partner API returned no reminder rows for:

- patient `16558`
- Nathan's primary contact ID
- Nathan's account UUID

That means the reminders visible in the Instinct UI are not yet reproducible from the current Partner API call pattern alone. Treat that as an unresolved API/product behavior question, not as a parsing bug in the EVH scripts.

## Instinct import helpers

- `scripts/instinct_import_payload_builder.py`: builds patient payloads with
  default alert and reminder assignments.
- `scripts/instinct_test_account_check.py`: smoke-test utility for validating
  test account connectivity, alert/reminder lookups, and optional patient create
  (supports explicit `--patient-name` and `--patient-pms-id`, with either
  Bearer API key auth, username/password Basic auth, or OAuth
  `client_id`/`client_secret` token fetch; discovers account alert/reminder IDs
  on the fly for the import payload).
- `docs/instinct-import.md`: integration notes, endpoint checklist, and test-account commands.
- `scripts/instinct_active_patients_audit.py`: preflight checker for `Active Patients.csv` to verify unique patient identifiers and required mapping fields before bulk import.
- `scripts/evh_reminder_importer.py`: reminder spreadsheet parser plus live patient/reminder audit mode for validating owner/contact/reminder state before import execution.
- `scripts/weave_contact_sync.py`: periodic Instinct-account exporter that emits incremental Weave bulk-import CSV batches, skips unchanged accounts by stable payload hash, and persists local watermark/export state.
- `tests/test_instinct_import_payload_builder.py`: unit tests for payload merge/dedupe behavior.

## Invocation examples

Build and print a sample patient payload:

```bash
.venv/bin/python scripts/instinct_import_payload_builder.py
```

Validate test-account connectivity and discover live alert/reminder IDs:

```bash
.venv/bin/python scripts/instinct_test_account_check.py \
  --base-url "https://partner.instinctvet.com" \
  --client-id "$INSTINCT_CLIENT_ID" \
  --client-secret "$INSTINCT_CLIENT_SECRET" \
  --account-id "<account-uuid>" \
  --patient-name "bob TEST" \
  --patient-pms-id "FE261"
```

Optionally create the test patient:

```bash
.venv/bin/python scripts/instinct_test_account_check.py \
  --base-url "https://partner.instinctvet.com" \
  --client-id "$INSTINCT_CLIENT_ID" \
  --client-secret "$INSTINCT_CLIENT_SECRET" \
  --account-id "<account-uuid>" \
  --patient-name "bob TEST" \
  --patient-pms-id "FE261" \
  --create-patient
```

Audit the active-patients CSV before import:

```bash
.venv/bin/python scripts/instinct_active_patients_audit.py --csv "Active Patients.csv"
```

Dry-run the grouped reminder spreadsheet parser:

```bash
.venv/bin/python scripts/evh_reminder_importer.py "scripts/ReminderData.xlsx" --dry-run --max-patients 10
```

Audit live patients plus reminder counts exposed by the Partner API:

```bash
.venv/bin/python scripts/evh_reminder_importer.py \
  --audit-patients \
  --base-url "https://partner.instinctvet.com" \
  --username "$INSTINCT_CLIENT_ID" \
  --password "$INSTINCT_CLIENT_SECRET" \
  --max-patients 25 \
  --export-json patients.json
```

Export incremental Weave contact-import CSV files from Instinct accounts:

```bash
.venv/bin/python scripts/weave_contact_sync.py \
  --base-url "https://partner.instinctvet.com" \
  --token "$INSTINCT_TOKEN" \
  --clinic-id "evh-main" \
  --state-file /tmp/evh-weave-contact-sync-state.json \
  --export-dir /tmp/evh-weave-contact-csv \
  --chunk-size 10000
```

Note: `scripts/evh_reminder_importer.py` currently supports:

- spreadsheet parsing and source-to-Instinct mapping
- live patient audit
- patient lookup by account/client and patient identity

It does not yet implement the final reminder submission path end-to-end.
