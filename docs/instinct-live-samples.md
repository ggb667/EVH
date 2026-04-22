# Instinct live sample capture

This repo now has a smoke-test helper that can write live Instinct Partner API sample JSON to:

- `docs/instinct-live-samples.json`

Capture command:

```bash
.venv/bin/python scripts/instinct_test_account_check.py \
  --base-url "https://partner.instinctvet.com" \
  --client-id "$INSTINCT_CLIENT_ID" \
  --client-secret "$INSTINCT_CLIENT_SECRET" \
  --account-id "<account-uuid>" \
  --patient-name "bob TEST" \
  --patient-pms-id "FE261" \
  --capture-samples
```

The captured JSON currently includes:

- `account`
- `appointments`
- `appointment_types`
- `reminders`

Use the generated JSON file as the source of truth for local docs when the tenant shape changes.
