# Vetcove Home Delivery <-> Instinct alignment design

## Current reality

As of April 1, 2026, Vetcove Home Delivery told EVH that they do **not** integrate with Instinct.

That means EVH is not building a native Instinct-to-Vetcove API integration. The workable path is a custom EVH-controlled export/import workflow:

1. client and patient remain authoritative in Instinct
2. prescriptions remain authoritative in Instinct
3. EVH exports the needed identity and prescription data from Instinct
4. EVH transforms that data into Vetcove's onboarding/import format
5. staff loads that data into Vetcove Home Delivery
6. the client orders through Vetcove Home Delivery

## Goal

Use Vetcove Home Delivery as the client-facing order channel while keeping Instinct as the EVH system of record for:

- client identity
- patient identity
- prescription details
- internal prescription history

## What EVH already has

The current EVH repo already has useful Instinct-side groundwork:

- `scripts/instinct_accounts.py`
  - reusable account and patient identity lookups
  - account iteration
  - patient iteration
  - account resolution by `pimsCode`, `pimsId`, owner name, and phone
- `docs/instinct-prescription-payload-notes.md`
  - live payload notes for:
    - `GET /v1/external-prescriptions`
    - `GET /v1/external-prescriptions/{id}`
    - `GET /v1/dispensed-prescriptions`
    - `GET /v1/dispensed-prescriptions/{id}`

## Recommended operating model

Keep ownership simple:

- Instinct-owned:
  - client identity
  - patient identity
  - prescriber identity
  - prescription instructions
  - fill count and expiration context
- Vetcove-owned:
  - storefront UX
  - ordering flow
  - checkout and fulfillment
  - shipping/tracking

This is not bidirectional sync. It is an EVH-run export pipeline into a non-integrated external platform.

## Which Instinct feed looks most useful

This is an inference from live payloads, not a vendor-confirmed contract.

### External prescriptions

Likely best candidate for Vetcove-facing export because the sampled payload includes:

- embedded `product.label`
- product unit metadata
- `instructions`
- `quantityPerFill`
- `status`
- `totalFills`
- `pharmacyNote`

### Dispensed prescriptions

Likely best candidate for reconciliation/history because the sampled payload includes:

- `accountId`
- `productId`
- `prescribedAt`
- `quantity`
- `remainingFills`

Recommended default:

- use `external-prescriptions` as the primary export feed
- use `dispensed-prescriptions` only if EVH needs additional reconciliation context

## Required export objects

### 1. Client export row

- `instinct_account_id`
- `instinct_account_pims_code`
- owner name
- owner phone
- owner email if present

### 2. Patient export row

- `instinct_patient_id`
- `instinct_patient_pims_code`
- linked account ID
- patient name
- species
- breed if available

### 3. Prescription export row

- `instinct_prescription_id`
- linked patient ID
- prescriber ID
- product label
- instructions
- quantity per fill
- total fills
- remaining fills when available
- status
- prescribed/written timestamp
- expiration timestamp

## What EVH should build

Build only owned RD implementation under:

- branch namespace: `pony/rd/*`
- scripts directory: `scripts/vetcove/`

Suggested components:

1. `scripts/vetcove/export_instinct_clients.py`
2. `scripts/vetcove/export_instinct_patients.py`
3. `scripts/vetcove/export_instinct_prescriptions.py`
4. `scripts/vetcove/build_vetcove_import.py`

The exact file set can change, but the output should support:

- full export
- delta export
- dry-run preview
- CSV/template output compatible with Vetcove onboarding

## Near-term implementation plan

### Phase 1

- compare Instinct fields to Vetcove's client/patient template
- identify required versus optional columns
- build dry-run export for clients and patients

### Phase 2

- build prescription export from `external-prescriptions`
- join prescriptions to patients/accounts
- emit Vetcove-ready rows or companion import artifacts

### Phase 3

- add dedupe/change detection
- add replayable export manifests
- optionally add reconciliation using `dispensed-prescriptions`

## Main unknowns

- exact Vetcove onboarding template columns now in use by EVH
- whether Vetcove wants prescription data in the same import path or a separate onboarding workflow
- whether EVH wants bulk preload only, or ongoing incremental exports
- whether product mapping requires additional Instinct product lookups beyond the sampled prescription payloads

## Sources

- Vetcove implementation email to EVH, dated April 1, 2026:
  - Vetcove stated they do not integrate with Instinct
- Repo-local:
  - `scripts/instinct_accounts.py`
  - `docs/instinct-prescription-payload-notes.md`
