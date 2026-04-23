# Weave <-> Instinct account/contact sync design

## Goal

Provide communications from both Weave and Instinct while keeping Instinct as the EVH system of record for client account and contact data. Weave should consume synchronized identity/contact state from Instinct and may write back Weave-originated communication activity into Instinct when EVH wants that reflected in the Instinct communication log.

## External constraints

### Instinct

- The existing EVH code already uses Instinct Partner API account lookups and `primaryContact` data in `scripts/evh_reminder_importer.py`.
- Instinct `GET /v1/accounts` supports pagination plus incremental filters that are usable for periodic sync:
  - `insertedSince`
  - `updatedSince`
  - `deletedSince`
  - `includeDeleted`
  - exact lookup by `pimsCode` and `pimsId`
  - partial lookup by `name`
- Instinct account identity rules in this repo already distinguish:
  - `account.id`: Instinct internal UUID
  - `account.pimsCode`: human-readable external code
  - `account.pimsId`: stable external integration identifier when present

### Weave

- The Weave engineering docs describe a schema-first platform where protobuf definitions generate:
  - gRPC services
  - grpc-gateway HTTP routes
  - generated clients
  - per-route auth and middleware wiring
- That architecture is a good fit for a dedicated EVH contacts sync service instead of embedding sync logic in an ad hoc script.

## Proposed architecture

Use a three-part design:

1. `evh-contact-sync` Weave service
2. EVH sync worker
3. shared contact-mapping and field-ownership store

### 1. `evh-contact-sync` Weave service

Implement a schema-owned service in Weave for contact upsert, lookup, sync-run visibility, and writeback event intake.

Suggested schema path:

- `weave/schemas/evh-contact-sync/v1`

Suggested RPCs:

- `UpsertExternalContact`
- `BatchUpsertExternalContacts`
- `GetExternalContactBySourceKey`
- `ApplyInstinctWriteback`
- `ApplyWeaveWriteback`
- `ListSyncRuns`
- `ReplaySyncRun`

Expose these via generated gRPC and grpc-gateway routes, but prefer generated gRPC clients for worker-to-service traffic. The gateway is still useful for operator tooling, diagnostics, and replay endpoints.

### 2. EVH sync worker

Run a periodic worker from EVH infrastructure that:

- authenticates to Instinct
- pages `GET /v1/accounts`
- filters incrementally by watermark timestamps
- normalizes Instinct account/contact data
- emits normalized Instinct-side contact change events
- calls the Weave generated client to upsert contacts or apply writeback
- stores sync state and run metrics

This worker can begin as a Python job in this repo because EVH already has Python-based Instinct integration code. If the sync becomes core Weave platform traffic, move the worker into the Weave service runtime later without changing the external contract.

### 2b. Appointment sync worker

Appointments need a dedicated sync path instead of being folded into contact sync, because appointment state changes have a narrower lifecycle and different conflict rules.

Use a second worker that:

- polls Instinct appointments incrementally
- resolves appointment type metadata
- maps Weave booking events to Instinct appointment records
- applies cancellation and confirmation updates in both directions
- preserves source-of-truth metadata per appointment field

Relevant Instinct endpoints:

- `GET /v1/appointments`
- `GET /v1/appointments/{id}`
- `PATCH /v1/appointments/{appointment_id}`
- `POST /v1/appointments/{appointment_id}/cancellation`
- `GET /v1/appointment-types`
- `GET /v1/appointment-types/{id}`

### 3. Shared contact-mapping and field-ownership store

Do not model this as a blind mirror. Keep a durable mapping record that answers:

- which Instinct account maps to which Weave contact
- which system last changed each synchronized field
- which fields are allowed to flow in each direction
- which source event or run produced the current value

For appointments, keep a second mapping record that answers:

- which Weave booking maps to which Instinct appointment
- which Instinct appointment type maps to which Weave service or booking template
- which side last confirmed, rescheduled, or canceled the appointment
- which values are safe for patient self-service edits

Without this layer, bidirectional communication sync will oscillate or overwrite good data.

## Data model

Create a canonical external-contact mapping record in Weave.

Required identifiers:

- `source_system`: `instinct`
- `source_account_id`: Instinct `account.id`
- `source_account_pims_code`: Instinct `account.pimsCode`
- `source_account_pims_id`: Instinct `account.pimsId`
- `clinic_id`: EVH clinic identifier
- `weave_contact_id`: Weave record ID once created
- `instinct_contact_key`: usually `account.id + primaryContact`
- `sync_profile`: field ownership policy name

Recommended normalized contact fields:

- `display_name`
- `first_name`
- `middle_name`
- `last_name`
- `mobile_phone`
- `home_phone`
- `work_phone`
- `email`
- `is_deleted`
- `source_inserted_at`
- `source_updated_at`
- `source_deleted_at`
- `source_payload_hash`
- `last_synced_at`

Recommended per-field metadata:

- `field_owner`
- `field_last_writer`
- `field_last_written_at`
- `field_last_source_version`

Keep the raw source payload as an audit blob for troubleshooting.

## Ownership model

Instinct is the source of truth for contact data.

Recommended baseline:

- Instinct-owned:
  - account identity
  - `account.id`
  - `pimsCode`
  - `pimsId`
  - contact names
  - phone numbers
  - email addresses
  - account deletion or inactive state
- Weave-owned:
  - communication preferences that exist only in Weave
  - channel enablement flags that exist only in Weave
  - messaging consent artifacts collected in Weave
  - communication activity metadata
  - outbound and inbound communication events generated inside Weave
- Writeback-eligible from Weave to Instinct only by explicit allowlist:
  - communication log entries
  - consent state or consent timestamps if Instinct supports them safely

Default policy for overlapping contact fields is `instinct_wins`. Do not use `latest_timestamp_wins` as a default for names, phones, or email.

### Appointment ownership

Appointments should be field-owned separately from contact data.

Recommended baseline:

- Instinct owns:
  - appointment identity
  - appointment type identity
  - operational status transitions that happen in the practice system
  - provider/resource assignment
  - clinic-side schedule constraints
- Weave owns:
  - patient-facing booking UI state
  - self-service booking intent
  - inbound booking request metadata
  - user-entered notes that are explicitly part of the booking flow
- Shared but policy-driven:
  - appointment time
  - confirmation state
  - cancellation state
  - patient-facing reminder metadata

For patient self-booking, Instinct remains the booking authority for the initial create, then mirror the resulting appointment into Weave using the stable external mapping record. Do not allow both systems to independently create a different appointment for the same patient and time slot without a conflict queue.

## Matching and idempotency

Primary match key order:

1. existing mapping on Instinct `account.id`
2. Instinct `pimsId`
3. Instinct `pimsCode`
4. conservative fallback on normalized name + normalized phone

Rules:

- never merge two existing Weave contacts automatically when multiple candidates are found
- send ambiguous matches to a review queue
- every upsert must be idempotent on `source_system + source_account_id`
- compare a stable payload hash before writing to Weave to suppress no-op updates
- attach a source version or source event timestamp to every write so replay is safe

## Sync flows

### A. Instinct -> Weave periodic sync

Run every 5 to 15 minutes.

Algorithm:

1. Load the last successful high-water mark for EVH clinic `X`.
2. Call `GET /v1/accounts` with:
   - `updatedSince=<watermark-minus-safety-window>`
   - `includeDeleted=true`
   - `limit=100`
3. Follow pagination with `pageCursor` and `pageDirection=after`.
4. For each account:
   - extract `primaryContact`
   - normalize phones and email
   - build canonical external-contact payload
   - resolve or create mapping in Weave
   - upsert Instinct-owned fields into Weave
   - preserve Weave-only communication metadata
5. Advance the watermark only after the full run commits.

Use a 5 to 10 minute safety overlap on the next run to avoid missing records near clock boundaries. Deduping by source key and payload hash handles replay safely.

### B. Instinct deletions

Use `includeDeleted=true` plus `deletedSince`.

Behavior:

- do not hard-delete Weave contacts
- mark the external mapping and the Weave contact linkage as inactive, archived, or suppressed
- preserve communication history

Weave-side deletion is not a required synchronization behavior.

### C. Weave -> Instinct writeback

Treat writeback as a secondary flow, bounded by explicit allowlist and EVH approval.

Primary writeback target is the Instinct communication log, not Instinct contact demographics.

Candidate writeback payloads:

- communication log entries for SMS sent from Weave
- communication log entries for calls placed or completed in Weave
- communication log entries for campaign or reminder delivery attempts from Weave
- communication consent timestamp if Instinct supports safe append or patch semantics

Avoid writing back:

- names
- account identity
- account merges
- arbitrary phone replacements
- arbitrary email replacements
- direct ownership of the primary contact record from Weave

Writeback pattern:

1. Weave emits a domain event for a communication action or approved communication-field change.
2. A writeback worker consumes the event.
3. The worker loads the contact mapping and ownership profile.
4. The worker drops fields not on the Weave-to-Instinct allowlist.
5. The worker fetches the latest Instinct account mapping.
6. The worker appends a communication-log entry to Instinct when supported, or applies a tightly scoped patch only for an explicitly approved field.
7. The worker records request and response bodies for audit.

If Instinct does not support a communication-log append endpoint or safe partial update path for the specific field, keep the Weave event local and do not attempt synthetic contact updates.

### D. Instinct-triggered communication updates back into Weave

If Instinct changes a contact field such as phone or email:

1. the periodic Instinct poller detects the changed account
2. the worker normalizes the changed values
3. the ownership policy is evaluated field by field
4. Weave is updated for Instinct-owned fields
5. conflicting fields are queued for review instead of overwritten silently

### E. Appointment sync

Run appointment sync on a shorter interval than contact sync if self-booking is customer-visible.

Algorithm:

1. Load the last successful appointment watermark for the clinic.
2. Call `GET /v1/appointments` with:
   - `updatedSince=<watermark-minus-safety-window>`
   - `startsAfter=<watermark-minus-safety-window>` when the sync also needs upcoming schedule visibility
   - pagination via `pageCursor` and `pageDirection=after`
3. For each appointment:
   - fetch full details when the list payload is not sufficient
   - fetch appointment type metadata when needed
   - resolve the appointment mapping record
   - apply field ownership and conflict rules
   - upsert the appointment into the other system only when the canonical value changed
4. When the appointment is canceled in Weave, propagate the cancellation request to Instinct. When Instinct changes the appointment state, mirror the resulting state into Weave.
5. Advance the watermark only after the full appointment run commits.

For patient-created appointments:

- create in Instinct as the system of record
- record the returned appointment ID immediately
- mirror the booking into Weave using the mapping record
- never treat a pre-confirmed patient booking as final until the practice-side confirmation state is synchronized

For cancellations:

- use the dedicated cancel endpoint when the source system emits a true cancellation
- do not model cancellation as a generic patch when the target API exposes a specific cancellation action
- preserve the original appointment record for audit and conflict resolution

## Conflict handling

Conflicts are expected, not exceptional.

A conflict exists when:

- both systems changed the same shared field since the last synchronization point
- the current ownership policy does not clearly choose a winner
- or the winning system lacks a reliable timestamp/version proving recency

Conflict actions:

- auto-resolve in favor of Instinct unless the field is explicitly Weave-owned
- queue for manual review when the policy is `manual_review_required`
- never bounce the same field value back and forth across systems

To prevent ping-pong:

- stamp every propagated write with integration metadata
- ignore self-originated echoes for a bounded time window
- persist the last applied source version per field

## Failure handling

Per-run tracking:

- run ID
- clinic ID
- started/finished timestamps
- source watermark in/out
- accounts scanned
- accounts created
- accounts updated
- accounts unchanged
- accounts deleted
- ambiguous matches
- field-level conflicts
- permanent failures
- retryable failures

Retry rules:

- retry 429 and 5xx responses with exponential backoff
- stop advancing watermark on partial-run failure
- dead-letter records that repeatedly fail normalization or mapping

## Security and auth

- Keep Instinct credentials in a secret manager.
- Use service-to-service auth for worker calls into Weave.
- Restrict operator replay endpoints behind authenticated internal routes.
- Log identifiers and sync status, but avoid logging full PII payloads by default.

## Observability

Emit:

- sync duration
- records per run
- API latency for Instinct and Weave
- conflict count
- manual review queue depth
- duplicate suppression count
- watermark lag

Provide operator views for:

- last successful sync per clinic
- failed records needing review
- replay of a single Instinct account by source ID

## Suggested implementation in this repo

Near-term EVH work:

- factor Instinct account iteration into a dedicated adapter module instead of leaving it inside the reminder importer
- add a new script or package for account normalization, Instinct-to-Weave projection, and batch export
- add fixtures/tests for:
  - pagination
  - updatedSince overlap windows
  - deleted account handling
  - ambiguous contact matches
  - idempotent upsert behavior
  - echo suppression for bidirectional updates
  - appointment type lookup and mapping
  - appointment cancellation propagation
  - appointment confirmation state drift
  - self-booked appointment mirroring

Suggested local modules:

- `scripts/instinct_accounts.py`
- `scripts/contacts/weave_contact_sync.py`
- `scripts/instinct_appointments.py`
- `scripts/weave_appointment_sync.py`
- `tests/test_instinct_accounts.py`
- `tests/test_weave_contact_sync.py`
- `tests/test_instinct_appointments.py`
- `tests/test_weave_appointment_sync.py`

## Rollout plan

### Phase 0

- build read-only dry run
- fetch changed Instinct accounts
- normalize payloads
- produce would-create and would-update reports without writing to Weave

### Phase 1

- enable Instinct -> Weave upsert for new accounts only
- require exact source-key idempotency
- no Weave -> Instinct writeback yet

### Phase 2

- enable updates for existing mapped contacts
- introduce deleted/inactive handling
- add ambiguity review queue
- add explicit Weave-owned communication event types and any approved writeback payloads

### Phase 3

- enable allowlisted Weave -> Instinct communication-log writeback
- add conflict queue and echo suppression
- gate by feature flag and full audit logging

## Open decisions

- What is the stable EVH clinic identifier used on the Weave side?
- Which Weave contact API or schema already exists for contact creation and update?
- Does Instinct expose a communication-log append endpoint or other supported API path for recording Weave-originated communications?
- Which phone and email fields from Instinct are authoritative when multiple communication channels exist?
- Should one Instinct account map to exactly one Weave contact, or can EVH require multiple communicators per household?
- Which communication capabilities must originate in Instinct versus Weave on day one?
- Which system is authoritative for initial appointment creation, confirmation, and cancellation?
- Does Weave already expose a booking API or schema for patient self-service appointment creation?
- Which appointment fields are editable by patients versus practice staff?

## Reference sources

- Weave engineering docs:
  - https://engineering.getweave.com/post/api-gateway-and-grpc-generation-1/
  - https://engineering.getweave.com/post/api-gateway-and-grpc-generation-2/
- Instinct account list reference:
  - https://docs.instinctvet.com/reference/instinct-partner-list-accounts
- Repo-local context:
  - `scripts/evh_reminder_importer.py`
  - `docs/instinct-import.md`
  - `README.md`
