# Instinct reminders handoff

This note is the shortest path from auth to patient reminder count.
It captures the live flow we verified against the partner API.

## 1. Make a Bearer token

Use the partner token endpoint with client credentials:

```bash
curl -sS https://partner.instinctvet.com/v1/auth/token \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'grant_type=client_credentials' \
  --data-urlencode 'client_id=$INSTINCT_CLIENT_ID' \
  --data-urlencode 'client_secret=$INSTINCT_CLIENT_SECRET'
```

Grab the returned `access_token` and send it as:

```bash
export INSTINCT_TOKEN="<access_token>"
```

## 2. Walk the reminders collection

First page:

```bash
curl -sS "https://partner.instinctvet.com/v1/reminders" \
  -H "Authorization: Bearer $INSTINCT_TOKEN"
```

The response includes:

- `data`: reminder rows
- `metadata.after`: cursor for the next page
- `metadata.totalCount`: total reminders in the collection

Page forward:

```bash
curl -sS "https://partner.instinctvet.com/v1/reminders?limit=100&pageCursor=<after>&pageDirection=after" \
  -H "Authorization: Bearer $INSTINCT_TOKEN"
```

Important live behavior:

- `pageDirection=after` is required for paging.
- `pageCursor` must be present and non-empty when paging.
- `limit` works up to `100`.

## 3. Find a patient

The fastest lookup we verified is by patient code:

```bash
curl -sS "https://partner.instinctvet.com/v1/patients?pimsCode=<patient-code>" \
  -H "Authorization: Bearer $INSTINCT_TOKEN"
```

If you only have a name, you can walk the patient list and match `name` in the
returned `data` rows.

Useful patient fields from the live response:

- `id`
- `name`
- `pimsCode`
- `accountId`

## 4. Count reminders for a patient

Once you know the patient `id`, walk all reminder pages and count rows where
`patientId` matches that patient:

```bash
curl -sS "https://partner.instinctvet.com/v1/reminders" \
  -H "Authorization: Bearer $INSTINCT_TOKEN"
```

Then page through using `metadata.after` until it is null.

For each page:

- inspect `data`
- count rows where `patientId == <patient-id>`
- add the matches to your running total

The live run we verified returned:

- `669` total reminders in the collection
- `3` reminders for patient `Ember Hetherman` / `pimsCode 27117`

What we tried and ruled out:

- Patching the patient record was not the correct way to create visible reminder rows.
- The live tenant did not expose a `patients/{id}/reminders` subresource in the probes we ran.
- We do not yet have the final create/update route for patient reminder rows.

## 5. Repo helpers

The local smoke-test helper now supports the same flow:

```bash
.venv/bin/python scripts/instinct_test_account_check.py \
  --base-url "https://partner.instinctvet.com" \
  --client-id "$INSTINCT_CLIENT_ID" \
  --client-secret "$INSTINCT_CLIENT_SECRET" \
  --discover-only
```

It uses:

- `GET /v1/accounts`
- `GET /v1/alerts`
- `GET /v1/reminders`

and prints the discovered rows from each list.
