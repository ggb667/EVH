# Instinct weight + alert ETL findings

## Scope of this pass

This pass imports only:

- patient `weight`
- patient `alertIds` when the source `Alert Text` maps cleanly to an existing Instinct alert

This pass explicitly does **not** import:

- reminder history
- vaccine history
- free-form patient notes
- account notes as a fallback for unmapped data

The implementation lives in:

- `scripts/instinct_alert_weight_etl.py`

The tests live in:

- `tests/test_instinct_alert_weight_etl.py`

## Workbook structure we verified

The source workbook is:

- `/home/ggb66/dev/EVH/Active_Clients_Alerts.xlsx`

Verified layout:

- row 4 = headers
- row 5 = blank spacer
- row 6 onward = data

Key columns:

- `B` `Account`
- `N` `Name`
- `O` `Weight`
- `Q` `Rabies`
- `U` `Notes`
- `V` `Alert Text`

Important meaning:

- account/client notes are before `Name`
- patient-level fields begin at `Name`
- `Alert Text` is the Avimark patient alert source for alert mapping

## What was wrong or misleading in the Instinct docs

These are not necessarily malicious vendor errors, but they were incomplete or misleading enough to block real ETL work until verified against the live API.

### 1. Using `api.instinctvet.com` was wrong for the Partner endpoints we needed

What worked live:

- `https://partner.instinctvet.com`

What failed from this environment:

- `https://api.instinctvet.com`

For the partner auth/account flows in this project, `partner.instinctvet.com` is the host that actually functioned.

### 2. The public reference pages we had were not enough to build the import

The available docs were enough to confirm:

- token auth endpoint
- fetch-account endpoint

They were **not** enough to reliably infer:

- how alerts are discovered in practice
- how reminder labels are discovered in practice
- whether patient notes exist on the patient object
- how account filtering works by `pimsCode`
- how pagination parameters really behave
- where vaccine history is created

### 3. The live API returned fields the quick helper output hid

The initial helper output only printed `id` and a generic `name`, which made alerts/reminders/accounts look mostly nameless.

What we learned by reading raw payloads:

- alerts use `label`, not `name`
- reminder labels use `label`, not `name`
- accounts can expose `primaryContact`, `alternateContacts`, `communicationDetails`, and `note`

### 4. The API metadata exposed pagination cursors that were not accepted back as obvious query params

Live responses included metadata like:

- `after`
- `before`
- `limit`
- `totalCount`

But these query params did **not** work:

- `after=...`
- `page[after]=...`
- `cursor=...`

That meant we could not rely on generic cursor-pagination assumptions.

### 5. The API did support direct account filtering by `pimsCode`

This turned out to be the practical fix.

What worked live:

- `GET /v1/accounts?pimsCode=10204`

What did not work:

- `pims_code`
- `accountPimsCode`

### 6. `limit` is supported, but capped

What worked:

- `limit=100`

What failed:

- `limit=200`

So the API does validate `limit`, but only up to 100.

## What we learned from the live API

### Auth

OAuth client credentials works with:

- `POST https://partner.instinctvet.com/v1/auth/token`
- body:
  - `grant_type=client_credentials`
  - `client_id`
  - `client_secret`

### Accounts

Useful live facts:

- `GET /v1/accounts?pimsCode=...` works
- account records expose:
  - `id`
  - `pimsCode`
  - `note`
  - `primaryContact`
  - `alternateContacts`

### Patients

Useful live facts:

- `GET /v1/patients?accountId=<uuid>` works
- patient records expose:
  - `id`
  - `name`
  - `pimsCode`
  - `weight`
  - `alerts`
  - `birthdate`
  - `breedId`
  - `speciesId`
  - `sexId`
  - `color`

Important constraint:

- we did **not** verify a general patient free-text notes field on the patient object

### Alerts

Useful live facts:

- `GET /v1/alerts` works
- alert records expose:
  - integer `id`
  - `label`

This is why Avimark free text cannot be copied directly into the patient payload. It has to map into existing Instinct alert IDs.

### Reminders

Useful live facts:

- `GET /v1/reminders` works
- reminder records are reminder instances, not just reusable label definitions
- `GET /v1/reminder-labels` works
- reminder-label records expose:
  - integer `id`
  - `label`
  - `productType`
  - `validFor`

This matters because reminder instances and reminder labels are not the same thing.

## Mapping policy used in this ETL

We only map alert text when the phrase is clean and conservative.

Current mapped patterns include:

- `will bite` -> `215`
- `muzzle` / `needs muzzle` -> `284`
- `go slow` -> `209`
- `dog aggressive` -> `235`
- `cat aggressive` -> `200`
- `blind` -> `192`
- `deaf` -> `225`
- `diabetic` -> `226`
- `fiv` -> `251`
- `felv` -> `246`
- `heart murmur` -> `262`
- `no jugular` -> `291`
- `no temp` / `no rectal temp` -> `296`
- `unpredictable` -> `214`
- `painful` -> `313`

We do **not** map the following in this pass:

- vaccine reaction notes
- split-vaccine notes
- premedication notes
- billing/admin notes
- owner communication notes
- general treatment instructions

## Match logic used for live apply

Each patient update is handled one row at a time.

Matching rules:

1. Match Instinct account by Avimark `Account` -> Instinct account `pimsCode`
2. Under that account, match patient by exact patient `Name`
3. Skip the row if:
   - no Instinct account matched
   - no patient matched
   - multiple patients matched the same name

Update rules:

- merge mapped alert IDs into existing patient alerts
- set patient `weight` when a workbook weight exists
- do not write account notes in this pass

## ETL log outputs

The script writes:

- JSONL log
- CSV log
- summary JSON

For each row it records:

- workbook row number
- account pims code
- patient name
- source weight
- source alert text
- mapped alert IDs
- mapped alert labels
- match/apply status
- matched account ID
- matched patient ID
- error text when skipped or failed

## Why vaccine history is still separate

We verified that the workbook `Rabies` column is mostly values like:

- `1042-23`
- `0852-25`
- `0491-26`

Those look like rabies certificate/tag-style codes, not a complete vaccine administration record.

That means the column does **not** reliably tell us:

- product
- administration date
- 1-year vs 3-year interval
- reminder label
- due date logic

So vaccine-history import needs a separate mapping pass with real live examples before we write it.

## How to run

Dry run:

```bash
.venv/bin/python scripts/instinct_alert_weight_etl.py \
  --xlsx /home/ggb66/dev/EVH/Active_Clients_Alerts.xlsx \
  --output-dir etl_logs/weight_alert_dry_run
```

Live apply:

```bash
.venv/bin/python scripts/instinct_alert_weight_etl.py \
  --xlsx /home/ggb66/dev/EVH/Active_Clients_Alerts.xlsx \
  --output-dir etl_logs/weight_alert_apply \
  --apply \
  --base-url https://partner.instinctvet.com \
  --client-id "$INSTINCT_CLIENT_ID" \
  --client-secret "$INSTINCT_CLIENT_SECRET"
```

## Current status

At this point we have:

- a tested ETL script for weights + clean alert IDs
- a dry-run log over the real workbook
- live API behavior verified for accounts, patients, alerts, reminder labels, and auth

Next steps after this pass:

1. confirm live apply counts from the ETL log
2. inspect skipped rows
3. decide whether to broaden alert mappings
4. design a separate vaccine/reminder-history import
