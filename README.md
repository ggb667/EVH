# EVH

## Local test run

Create the repo-local virtualenv, install `pytest`, and run the test suite:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install pytest
.venv/bin/python -m pytest -q
```

## Instinct API base

The official Instinct Partner API reference lists the fetch-account endpoint as:

- `GET https://partner.instinctvet.com/v1/accounts/{id}`

Project-local reference copy:

- `docs/instinct-partner-fetch-account.md`

## Instinct token auth

The smoke-test helper supports three auth modes:

- Bearer token via `--api-key`
- Basic auth via `--username` and `--password`
- OAuth client credentials via `--client-id` and `--client-secret`

If you already have a Bearer token, pass it directly:

```bash
.venv/bin/python scripts/instinct_test_account_check.py \
  --base-url "https://api.instinctvet.com" \
  --api-key "$INSTINCT_TOKEN" \
  --discover-only
```

If you only have a client ID and client secret, the script can fetch the token for you from:

- `POST https://partner.instinctvet.com/v1/auth/token`

The partner flow that worked live in this repo was client credentials against the
partner token endpoint, then Bearer auth on the API requests.

Use:

```bash
.venv/bin/python scripts/instinct_test_account_check.py \
  --base-url "https://api.instinctvet.com" \
  --client-id "$INSTINCT_CLIENT_ID" \
  --client-secret "$INSTINCT_CLIENT_SECRET" \
  --discover-only
```

If you need to fetch the token yourself first, this request matches the script behavior:

```bash
curl -X POST "https://partner.instinctvet.com/v1/auth/token" \
  -H "Accept: application/json" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "grant_type=client_credentials" \
  --data-urlencode "client_id=$INSTINCT_CLIENT_ID" \
  --data-urlencode "client_secret=$INSTINCT_CLIENT_SECRET"
```

Then use the returned `access_token` as:

```bash
export INSTINCT_TOKEN="<access_token>"
```

## Instinct reminders workflow

For the live reminders workflow we verified:

1. Fetch a Bearer token from `POST https://partner.instinctvet.com/v1/auth/token`.
2. Walk reminders with `GET /v1/reminders`.
3. Use the returned `metadata.after` cursor with
   `GET /v1/reminders?limit=100&pageCursor=<after>&pageDirection=after`.
4. Find a patient by `GET /v1/patients?pimsCode=<patient-code>` or by walking
   the patient list and matching `name`.
5. Count that patient’s reminders by filtering the reminder list on `patientId`.

Current reminder-write status:

- patient PATCH was not the correct write path for creating visible reminder rows
- `GET /v1/reminders` is still the read/count source of truth
- the tenant exposes patient-linked reminder rows, but the exact create/update route still needs one more lookup

The full worked example is documented in:

- `docs/instinct-reminders-handoff.md`

## Instinct import helpers

- `scripts/instinct_import_payload_builder.py`: builds patient payloads with
  default alert and reminder assignments.
- `scripts/instinct_test_account_check.py`: smoke-test utility for validating
  test account connectivity, alert/reminder lookups, and optional patient create
  (supports explicit `--patient-name` and `--patient-pms-id`, with either
  Bearer API key auth, username/password Basic auth, or OAuth
  `client_id`/`client_secret` token fetch). Also supports `--discover-only`
  (ID lookup) and optional initial visit create after patient creation.
- `docs/instinct-import.md`: integration notes, endpoint checklist, and test-account commands.
- `docs/instinct-weight-alert-etl.md`: workbook structure, Instinct API findings, doc gaps, and the current weight + alert ETL rules.
- Includes a troubleshooting section for applying patches cleanly in zsh/WSL (`git apply --check` + heredoc pattern).
- `scripts/instinct_active_patients_audit.py`: preflight checker for `Active Patients.csv` to verify unique patient identifiers and required mapping fields before bulk import.
- `scripts/instinct_alert_weight_etl.py`: ETL for importing patient weights and only the cleanly mappable Instinct alert IDs, with JSONL/CSV summary logs.
- `tests/test_instinct_import_payload_builder.py`: unit tests for payload merge/dedupe behavior.
