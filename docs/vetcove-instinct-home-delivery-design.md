# Vetcove Home Delivery <-> Instinct alignment design

## Goal

Use Vetcove Home Delivery as the client-facing online pharmacy and fulfillment channel while keeping Instinct as the EVH system of record for client, patient, prescription, and clinical-history data wherever Instinct supports that contract safely.

## What the current EVH repo already gives us

The existing EVH codebase is Instinct-centric today:

- `README.md` documents the identifier rules already relied on in EVH:
  - `account.id` = Instinct internal account UUID
  - `account.pimsCode` / `account.pimsId` = external account identifiers
  - `patient.id` = Instinct internal patient ID
  - `patient.pimsCode` = external patient identifier
- `scripts/evh_reminder_importer.py` already implements:
  - Instinct auth via `POST /v1/auth/token`
  - paginated `GET /v1/accounts`
  - paginated `GET /v1/patients`
  - `GET /v1/patients/{id}`
  - account lookup by `pimsCode`, `pimsId`, and owner name
  - patient lookup scoped to an Instinct account
- `docs/weave-instinct-account-sync-design.md` already establishes a sound policy that is reusable here:
  - Instinct should remain source of truth for identity/contact data
  - sync must use durable mapping records
  - writes must be idempotent and field-owned

This means EVH already has the beginnings of the Instinct adapter and identity model we need. What is missing is the Vetcove-side contract and the pharmacy/order synchronization layer.

## What Vetcove Home Delivery appears to require

Based on recent public integration documentation from other veterinary PIMS vendors, Vetcove Home Delivery generally works like this:

1. The practice connects its Vetcove Home Delivery account.
2. Client and patient data are synced from the PIMS into Vetcove.
3. Prescriptions are created in Vetcove against those synced patients.
4. Client medication orders and refill activity flow back into the PIMS.
5. Prescription and order events are attached to the patient record in the PIMS.

Observed behavior from public docs:

- ezyVet documents that Vetcove Home Delivery syncs client/patient data to Vetcove, syncs prescriptions to patient records, and syncs client medication orders back into the PIMS.
- ezyVet also states the initial sync can take up to four hours and ongoing sync runs nightly.
- DaySmart Vet documents that client and patient information is shared with Vetcove and that online-store orders are written back into patient history.
- Digitail documents real-time record creation/update for the launched prescription flow plus patient-record writeback for home-delivery prescriptions.

We should treat the exact cadence and trigger behavior as vendor-contract questions until Vetcove confirms the official integration pattern for Instinct specifically.

## Recommended ownership model

Keep the ownership policy simple:

- Instinct-owned:
  - account identity
  - patient identity
  - patient demographics
  - prescriber identity
  - official prescription record
  - medical-history copy of the pharmacy event
- Vetcove-owned:
  - storefront UX
  - commerce workflow
  - cart/order lifecycle
  - shipment status
  - refill request intake
  - retailer/fulfillment metadata
- Shared but policy-driven:
  - prescription status
  - refill count / refill eligibility
  - order status visible to staff
  - cancellation state

Default policy should be `instinct_wins` for all identity and clinical fields.

## Required integration objects

Create explicit mappings instead of relying on ad hoc lookups:

### 1. Account mapping

- `instinct_account_id`
- `instinct_account_pims_code`
- `instinct_account_pims_id`
- `vetcove_client_id`
- `clinic_id`
- `last_synced_at`
- `source_payload_hash`

### 2. Patient mapping

- `instinct_patient_id`
- `instinct_patient_pims_code`
- `instinct_account_id`
- `vetcove_patient_id`
- `clinic_id`
- `last_synced_at`
- `source_payload_hash`

### 3. Prescription mapping

- `instinct_prescription_id`
- `vetcove_prescription_id`
- `instinct_patient_id`
- `prescriber_id`
- `product_key`
- `status`
- `written_at`
- `expires_at`
- `last_synced_at`

### 4. Order mapping

- `vetcove_order_id`
- `vetcove_order_line_id`
- `instinct_patient_id`
- `instinct_account_id`
- `instinct_prescription_id` when applicable
- `source_event_type`
- `source_event_timestamp`
- `last_written_to_instinct_at`

## Alignment strategy

### A. Patient and client identity

Use Instinct as the master source and export account/patient data into Vetcove.

Primary match order:

1. existing mapping record
2. Instinct `patient.id` / `account.id`
3. Instinct `patient.pimsCode` / `account.pimsId`
4. Instinct `account.pimsCode`
5. conservative fallback on normalized owner name + phone

This is directly aligned with how the current EVH code already resolves Instinct records.

### B. Prescription creation and approval

The cleanest operating model is:

1. staff initiates or approves a prescription from the Instinct-side patient context
2. EVH sends the normalized patient/client context to Vetcove if missing or stale
3. EVH creates or updates the Vetcove prescription record
4. EVH stores the external prescription mapping
5. EVH writes a pharmacy-history event back into Instinct

If Instinct already has a first-class prescription object and write API, that object should be the source of truth.
If Instinct lacks a safe prescription-write surface, then EVH should still write a durable pharmacy-history artifact into Instinct so staff can see what happened.

### C. Client orders and refill activity

Orders placed by clients in Vetcove should be ingested as events, not treated as authoritative patient edits.

Expected inbound events:

- order created
- refill requested
- order approved
- order canceled
- order fulfilled
- shipment/tracking updated

For each event:

1. resolve the Vetcove order and prescription mappings
2. resolve the Instinct patient/account
3. dedupe using `source_event_id` or a stable payload hash
4. write an order/prescription history note into Instinct
5. update the EVH mapping state

### D. Product alignment

This is a likely failure point and needs explicit mapping.

Do not assume Vetcove catalog items can be matched to Instinct products by display name alone.

Keep a product crosswalk with:

- `instinct_product_id` or equivalent clinical/invoice item ID
- `vetcove_product_id`
- `vendor_sku`
- `ndc` or manufacturer code when available
- package size / dispense unit
- allowed substitution policy

### E. Status alignment

Normalize both systems into a small internal status model:

- `draft`
- `pending_approval`
- `approved`
- `rejected`
- `ordered`
- `fulfilled`
- `canceled`
- `expired`

Then maintain explicit translation tables:

- `instinct_status -> canonical_status`
- `vetcove_status -> canonical_status`

## What EVH likely needs to build

### 1. A dedicated Instinct accounts/patients adapter

Factor the reusable account/patient logic out of `scripts/evh_reminder_importer.py` into a supported module, because the lookup logic there is already the basis for Vetcove identity resolution.

Suggested module:

- `scripts/instinct_accounts.py`

### 2. A Vetcove adapter boundary

Add a provider-facing adapter for:

- upserting clients/accounts
- upserting patients
- creating/updating prescriptions
- ingesting order events
- fetching order details for replay/debugging

Suggested module:

- `scripts/vetcove_home_delivery.py`

### 3. A mapping store

At minimum, persist account, patient, prescription, and order mappings plus sync timestamps and hashes. Without this, retries and nightly sync overlap will cause duplicate records or unsafe relinking.

### 4. Sync jobs

Implement separate jobs:

- `instinct_to_vetcove_identity_sync`
- `vetcove_to_instinct_order_sync`
- `vetcove_to_instinct_prescription_sync`
- optional `reconciliation_sync`

### 5. Instinct writeback contract

Confirm which Instinct API or internal EVH write path should receive:

- prescription creation/update
- pharmacy/order history entries
- refill requests
- order cancellation/fulfillment status

The current repo proves read access for accounts, patients, alerts, reminders, plus patient patching for reminder IDs. It does not yet show a prescription or order write surface.

## Proposed rollout

### Phase 0: discovery and contract validation

- Confirm Vetcove Home Delivery's official Instinct integration pattern.
- Confirm Instinct endpoints or internal APIs for prescription/order history writeback.
- Confirm the minimum patient/client fields Vetcove requires.
- Confirm the product identifier set available from both systems.

### Phase 1: read-only patient/client sync

- Export Instinct accounts and patients to a dry-run Vetcove sync payload.
- Persist mappings without enabling order or prescription writes.
- Produce mismatch reports for duplicate owners, missing phones, and missing external IDs.

### Phase 2: prescription launch

- Support patient/client sync into Vetcove.
- Launch prescription creation from EVH staff workflow.
- Record external prescription mappings.
- Write pharmacy-history artifacts back into Instinct.

### Phase 3: client order/refill ingestion

- Ingest Vetcove order/refill events.
- Reconcile them to Instinct patient/account/prescription mappings.
- Write status/history back into Instinct.
- Add replay, audit, and dead-letter handling.

### Phase 4: reconciliation and operator tooling

- nightly reconciliation for missing writebacks
- single-patient replay
- single-order replay
- duplicate/ambiguity review queue

## Highest-risk gaps to resolve first

1. Does Instinct expose a supported prescription/order API, or will EVH need an internal writeback path outside the public Partner API?
2. What exact Vetcove identifiers and callbacks/webhooks are provided for Home Delivery?
3. Is Vetcove expecting nightly bulk sync, just-in-time patient sync during prescription launch, or both?
4. Which system is authoritative for refill eligibility and prescription expiration?
5. How should cancellations and substitutions be represented in Instinct?
6. What product identifier can safely align catalog items across both systems?

## Recommended next implementation step in this repo

Build the integration in this order:

1. extract Instinct account/patient lookup code into `scripts/instinct_accounts.py`
2. define normalized mapping dataclasses for account/patient/prescription/order
3. implement a dry-run `scripts/vetcove_home_delivery_sync.py` that emits the outbound Instinct -> Vetcove payloads
4. only after contract confirmation, add the Vetcove adapter and Instinct writeback path

That sequencing minimizes rework because it uses the Instinct identity logic already validated in EVH while postponing the vendor-specific write path until the contract is confirmed.

## Sources

- Repo-local:
  - `README.md`
  - `scripts/evh_reminder_importer.py`
  - `docs/weave-instinct-account-sync-design.md`
- Public references reviewed on April 21, 2026:
  - ezyVet Vetcove Home Delivery overview: https://docs.ezyvet.com/en/see-all-integrations/product-suppliers/vetcove-home-delivery/about-the-integration-for-vetcove-home-delivery
  - ezyVet Vetcove Home Delivery workflow: https://docs.ezyvet.com/en/see-all-integrations/product-suppliers/vetcove-home-delivery/vetcove-home-delivery-and-ezyvet-basic-workflow
  - DaySmart Vet Vetcove Home Delivery integration: https://help.vettersoftware.com/en/articles/10258097-vetcove-home-delivery-integration
  - Vetcove Home Delivery on ezyVet marketplace: https://www.ezyvet.com/integration/vetcove-home-delivery
