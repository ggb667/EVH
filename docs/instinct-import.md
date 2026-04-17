# Instinct import notes (patients, alerts, reminders)

## What we are enforcing

- **Alerts:** Instinct patient create/update accepts `alertIds` as an array.
  We discover the live account's alert IDs and apply the first one for the test flow.
- **Reminders:** We discover the live account's reminder IDs and attach the discovered set
  per patient in the import payload.

## Relevant Instinct endpoints

- `GET /v1/accounts/{id}` (validate target account)
- `GET /v1/alerts` (resolve alert names to IDs)
- `GET /v1/reminders` (resolve reminder names to IDs)
- `POST /v1/patients` (create with `alertIds`)
- `PATCH /v1/patients/{patient_id}` (update with `alertIds`)

## Local payload helper usage

```bash
python scripts/instinct_import_payload_builder.py
```

This prints a sample payload containing:

- core patient fields
- merged `alertIds` (source + required default)
- merged `reminderIds` (source + configured default reminders)

## Test-account smoke test

Use the smoke-test script to validate account access and IDs before creating any patient:

```bash
python scripts/instinct_test_account_check.py \
  --base-url "https://partner.instinctvet.com" \
  --client-id "$INSTINCT_CLIENT_ID" \
  --client-secret "$INSTINCT_CLIENT_SECRET" \
  --account-id "<test-account-uuid>" \
  --patient-name "bob TEST" \
  --patient-pms-id "FE261"
```

Then create a real test patient by adding `--create-patient`:

```bash
python scripts/instinct_test_account_check.py \
  --base-url "https://partner.instinctvet.com" \
  --client-id "$INSTINCT_CLIENT_ID" \
  --client-secret "$INSTINCT_CLIENT_SECRET" \
  --account-id "<test-account-uuid>" \
  --patient-name "bob TEST" \
  --patient-pms-id "FE261" \
  --create-patient
```

For the owner/account context you provided:

- Owner display: `INSTINCT TEST / Greg Test`
- Owner phone: `(321) 123-4567`
- Owner email: `Greg.Bishop.srsweng@gmail.com`
- Patient to create: `bob TEST`
- PMS ID (`pimsCode`): `FE261`

Use the **owner's Instinct account UUID** as `--account-id` (the script validates it with `GET /v1/accounts/{id}`).
Authentication is required; provide either:

- `--client-id` + `--client-secret` (fetches Bearer token via `POST https://partner.instinctvet.com/v1/auth/token`), or
- `--username` + `--password` (Basic auth), or
- `--api-key` (Bearer auth).

The script:

1. Calls `GET /v1/accounts/{id}` to verify the test account exists.
2. Calls `GET /v1/alerts` and `GET /v1/reminders` to discover account-specific IDs.
3. Builds and prints the exact patient payload from `PatientPayloadBuilder`.
4. Optionally calls `POST /v1/patients` when `--create-patient` is provided.

Official reference source:

- `docs/instinct-partner-fetch-account.md`

## Active Patients CSV preflight (run only after test-account success)

After you successfully run the test-account flow above (including optional `--create-patient`),
audit your bulk file before importing:

```bash
python scripts/instinct_active_patients_audit.py --csv "Active Patients.csv"
```

What this checks:

- Detects whether a PMS/patient ID column exists and is unique per row.
- Reports rows missing ID values.
- Reports duplicate ID values.
- Reports missing core mapping fields (`patient`, owner contact, species, breed, sex).

Reminder import audit:

- `python scripts/evh_reminder_importer.py --audit-patients ...` fetches patient detail from `GET /v1/patients/{id}` so owner name and phone come from the embedded account record.
- It pages the global `GET /v1/reminders` feed and derives patient reminder counts only when the reminder payload exposes a patient reference.
- If the reminder payload does not identify the owning patient, the script emits `null` for `reminder_count` instead of a misleading `0`.

If IDs are duplicated or missing, add a stable external patient ID column before bulk import.
