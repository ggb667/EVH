# Instinct import notes (patients, alerts, reminders)

## What we are enforcing

- **Alerts:** Instinct patient create/update accepts `alertIds` as an array.
  We include one default alert ID for every patient import.
- **Reminders:** We keep a small, configured list of reminder IDs and attach
  them per patient in the import payload.

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

If you still need to look up IDs, run discovery first:

```bash
python scripts/instinct_test_account_check.py \
  --base-url "https://partner.instinctvet.com" \
  --client-id "$INSTINCT_CLIENT_ID" \
  --client-secret "$INSTINCT_CLIENT_SECRET" \
  --discover-only
```

This lists discovered account/alert/reminder IDs so you can pick the right values.

Reminder workflow status from the live tenant:

- `GET /v1/reminders` is the authoritative read path for patient-linked reminder rows.
- We verified that Ember Hetherman’s reminders are counted from that feed by `patientId`.
- We also verified that patching the patient record was not the right way to create visible reminder rows.
- The exact reminder create/update route still needs one more lookup before we can do live writes safely.

Use the smoke-test script to validate account access and IDs before creating any patient:

```bash
python scripts/instinct_test_account_check.py \
  --base-url "https://partner.instinctvet.com" \
  --client-id "$INSTINCT_CLIENT_ID" \
  --client-secret "$INSTINCT_CLIENT_SECRET" \
  --account-id "<test-account-uuid>" \
  --default-alert-id 101 \
  --default-reminder-ids 201,202 \
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
  --default-alert-id 101 \
  --default-reminder-ids 201,202 \
  --patient-name "bob TEST" \
  --patient-pms-id "FE261" \
  --create-patient
```

If the patient has never had a visit and you need one created as part of setup, add:

```bash
python scripts/instinct_test_account_check.py \
  --base-url "https://partner.instinctvet.com" \
  --client-id "$INSTINCT_CLIENT_ID" \
  --client-secret "$INSTINCT_CLIENT_SECRET" \
  --account-id "<test-account-uuid>" \
  --default-alert-id 101 \
  --default-reminder-ids 201,202 \
  --patient-name "bob TEST" \
  --patient-pms-id "FE261" \
  --create-patient \
  --create-initial-visit
```

Notes:

- Default visit endpoint path is `/v1/visits`; override with `--visit-path` if your tenant uses a different route.
- Include `--visit-type-id <ID>` when your API requires a visit type.

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
2. Calls `GET /v1/alerts` and `GET /v1/reminders` to verify the configured IDs can be discovered.
3. Builds and prints the exact patient payload from `PatientPayloadBuilder`.
4. Optionally calls `POST /v1/patients` when `--create-patient` is provided.

If you need the shortest path from auth to reminder counting, see:

- `docs/instinct-reminders-handoff.md`

## Weight + alert ETL

For the current import pass, the live ETL only brings over:

- patient `weight`
- cleanly mapped Instinct `alertIds`

It does **not** yet write reminders, vaccine history, or free-form notes.

Use:

```bash
.venv/bin/python scripts/instinct_alert_weight_etl.py \
  --xlsx /home/ggb66/dev/EVH/Active_Clients_Alerts.xlsx \
  --output-dir etl_logs/weight_alert_dry_run
```

Or live apply:

```bash
.venv/bin/python scripts/instinct_alert_weight_etl.py \
  --xlsx /home/ggb66/dev/EVH/Active_Clients_Alerts.xlsx \
  --output-dir etl_logs/weight_alert_apply \
  --apply \
  --base-url https://partner.instinctvet.com \
  --client-id "$INSTINCT_CLIENT_ID" \
  --client-secret "$INSTINCT_CLIENT_SECRET"
```

Detailed findings, doc gaps, mapping rules, and ETL behavior are documented in:

- `docs/instinct-weight-alert-etl.md`

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

If IDs are duplicated or missing, add a stable external patient ID column before bulk import.

## Applying a patch cleanly on zsh / WSL

If you ever get this error while applying a patch:

`error: patch fragment without header at line ...`

it usually means extra text was mixed into the patch body (for example, prompt/output lines) or the patch started after the `diff --git ...` header.

Use this pattern so Git reads only the raw patch text:

```bash
cat > evh_changes.patch <<'PATCH'
diff --git a/README.md b/README.md
...patch lines...
PATCH

git apply --check evh_changes.patch
git apply evh_changes.patch
```

Notes:

- Keep `PATCH` alone on its own line (no spaces before/after).
- Start at the first `diff --git` line.
- Run `git apply --check` first to validate before applying.
