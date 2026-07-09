# EVH Mailbox Cleanup Archive
- Archived at: 2026-07-09T02:42:38.582189Z
- Reason: live mailbox lanes were carrying stale historical notification backlog that already belongs in durable workfiles, status files, or Twilight current-facts sections.

## aj.mailbox.md
```md
# AJ MAILBOX

## Pending Items
- none## 2026-07-02T11:31:03.833997355+00:00
- FROM: ⚡ Rainbow Dash
- TO: Applejack
- SUBJECT: ⚡ It gave you the string
- BODY:
```text
you need right?


• Yeah. The string is the benchmark ask from AJ:

  Benchmark PDF chunking and embedding on demand so we can tell whether lazy
  vectorization is acceptable.

  The rest of the note spells out the measures:

  - extraction time
  - chunk count
  - chunking time
  - embedding time
  - first-search latency

  If you want, I can turn that into the exact next RD action and status update.


⚡ No the connection string for postgress


• Nope. The mailbox does not include the Postgres connection string.

  It says the chunker has a psql load path, but the live Postgres connection string is
  still needed for the actual insert/search pass.

  So the string is still missing, and that’s the blocker for the full end-to-end
  benchmark.
```

## 2026-07-03T18:39:12.543395597+00:00
- FROM: ⚡ Rainbow Dash
- TO: Applejack
- SUBJECT: - The next RD slice is th
- BODY:
```text
e PDF chunker. I need the vector DB connection information so I can store the enhanced chunks after text extraction, keyword
    annotation, and clinical summary generation.
```

## 2026-07-03T19:14:04.600351408+00:00
- FROM: ⚡ Rainbow Dash
- TO: Applejack
- SUBJECT: add:
- BODY:
```text


  - clinical_summary TEXT NOT NULL DEFAULT ''

  If you want, I can also give you the exact ALTER TABLE for the vector table and the ingest-state table.


⚡ yes


• Yep, here’s the exact SQL, dash-fast:

  ALTER TABLE instinct_pdf_chunks
    ADD COLUMN IF NOT EXISTS clinical_summary TEXT NOT NULL DEFAULT '';

  ALTER TABLE instinct_pdf_ingest_state
    ADD COLUMN IF NOT EXISTS clinical_summary TEXT NOT NULL DEFAULT '';

  If the chunk table name is different in RD’s environment, swap instinct_pdf_chunks for the real vector table name.
```
```

## fs.mailbox.md
```md
# FS MAILBOX

## Pending Items
- none
```

## pinkie.mailbox.md
```md
# PINKIE MAILBOX

## Pending Items
- none
```

## rarity.mailbox.md
```md
# RARITY MAILBOX

## Pending Items
- none
```

## rd.mailbox.md
```md
# RD MAILBOX

## Pending Items
- none## 2026-07-02T04:55:43.307541549+00:00
- FROM: 🍎 Applejack
- TO: Rainbow Dash
- SUBJECT: Dash: Benchmark PDF chunk
- BODY:
```text
ing and embedding on demand so we can tell whether lazy
  vectorization is acceptable. Measure extraction time, chunk count, chunking time,
  embedding time, and first-search latency on a representative PDF sample. Keep PDFs in
  S3 and use the benchmark to decide how much of the pipeline should be precomputed
  versus deferred.
```

## 2026-07-02T05:14:42.454008914+00:00
- FROM: 🍎 Applejack
- TO: Rainbow Dash
- SUBJECT: Dash look at pony/team
- BODY:
```text
.coordination/rd.mailbox.md AJ has set up the postgres DB and we can try to chunk one PDF and load it into the vector DB.
```

## 2026-07-03T18:39:58.883024746+00:00
- FROM: 🍎 Applejack
- TO: Rainbow Dash
- SUBJECT: Dash FROM: Applejack
- BODY:
```text

     5 +- TO: Rainbow Dash
     6 +- SUBJECT: Vector DB connection info for the PDF chunker
     7 +- BODY:
     8 +  - The next RD slice is the PDF chunker.
     9 +  - Use the managed Postgres vector DB, not MariaDB, for enhanced chunks after text extraction, keyword annotation, and clinical summary generat
        ion.
    10 +  - Endpoint: `evh-vector-pg.c6hqq6a8ukmj.us-east-1.rds.amazonaws.com:5432`
    11 +  - Secret ARN: `arn:aws:secretsmanager:us-east-1:274530612068:secret:rds!db-c16642bd-0562-45c7-8e06-6ba3f39fd7fe-2PM8Uo`
    12 +  - The vector-store target is the separate EVH RAG Postgres instance.
```
```

## spike.mailbox.md
```md
# SPIKE MAILBOX

## Pending Items
- Twilight RAG handoff, 2026-06-30: EVH is pivoting to a RAG system over legacy PMS PDFs.
- Spike's new assignment: document the RAG architecture, worker contracts, and MVP milestones. Do not continue treating Reminders, Weave Contacts, Weave Scheduling, Stockroom, or Vetcove as the active cross-track documentation priorities unless Twilight/user explicitly reopens those tracks.
- First serious milestone: for one selected client/pet, show a timeline of reconstructed document summaries, each linking to the correct page in the large PMS PDF.
- Overall product shape:
  - Ingest large PMS PDFs or stable PDF references.
  - Extract text page by page.
  - Store page text, page links, document boundaries, summaries, detected terms, embeddings, and status/confidence fields in Handshake's Aurora MySQL/MariaDB-compatible database.
  - Reconstruct sub-documents from merged legacy PDFs.
  - Show a scoped client/pet timeline and source links.
  - Use guided templates instead of free-form questions for MVP.
- Tooling decisions:
  - Database: Handshake's Aurora MySQL, MariaDB-compatible database for the current shared load target.
  - Python package manager: uv.
  - PDF extraction: start with PyMuPDF.
  - OCR: add Tesseract or AWS Textract only for scanned/image-only pages.
  - Search: combine keyword/full-text search with vector search; do not rely on vector search alone.
  - AI: embeddings plus LLM summaries/classification, likely OpenAI or Bedrock.
  - LangGraph: not required for MVP ingestion; use durable DB ingestion states first, and consider LangGraph later for uncertain summarization/classification/Q&A flows.
- Worker assignments for RAG:
  - RD: PDFs. Obtain PMS/Instinct PDF files or stable PDF references for initial ingestion. The user will personally work from RD's tree for now.
  - AJ: DB. Keep the Handshake Aurora MySQL/MariaDB-compatible load state current and verify any new assigned loads.
  - Rarity: Meds & Treatments. Shared dictionary seed is already delivered to AJ and loaded; do not retry it unless the user assigns a correction.
  - FS: Vet Terms. Define veterinary document type clues, source clues, treatment context terms, and template terminology.
  - Spike: Docs. Document the system architecture, worker contracts, and MVP milestones.
  - Twilight: Coordination unchanged.
  - Pinkie: Idle for this split.
- Suggested build order:
  - MVP 1 Page Index: PMS document reference, PDF page extraction, MariaDB-compatible page storage, page links, basic client/pet/name search.
  - MVP 2 Medication/Treatment Detection: load dictionaries, detect terms on pages, show mentions with citations.
  - MVP 3 Document Grouping: infer start/end pages, classify type, detect dates, create groups.
  - MVP 4 Summaries: short document summaries, timeline, hyperlinks to source pages.
  - MVP 5 Guided Template Answers: canned workflows only, with citations and context categories.
  - MVP 6 Admin Correction: fix grouping, dates, document types, summaries, and false term matches.
- Data model concepts Spike should document:
  - `pms_document`: client_id, pet_id, PMS IDs/attachment IDs, filename, page_count, PMS reference/access URL, import_status.
  - `pdf_page`: document_id, page_number, extracted_text, extraction_method, text_quality, source page link.
  - `medication_dictionary`: canonical_name, aliases, category, active/inactive.
  - `treatment_dictionary`: canonical_name, aliases, category, active/inactive.
  - `detected_term`: page_id, term_type, canonical_name, matched_text, confidence, location/snippet.
  - `document_group`: source_pdf_id, start_page, end_page, probable_date, probable_type, probable_source, confidence.
  - `document_summary`: document_group_id, client_id, pet_id, summary, key_medications, key_treatments, key_findings, start_page, end_page, source_link, confidence.
- Guided template concepts:
  - summarize history
  - list medications
  - list treatments
  - list diagnostics
  - list vaccines
  - list follow-ups
  - show source pages
- Safety/context policy to document:
  - For medications, distinguish current/home medication, prescribed at visit, administered in clinic, historical mention, and unclear mention.
  - For treatments, distinguish performed, recommended, declined, planned, historical mention, and unclear.
  - Deterministic term detection answers "what terms are present"; model summaries answer "what those mentions mean in context."
- UI/API target:
  - Client/pet picker.
  - Timeline: Date, Type, Summary, Source.
  - Source page links into the original PDF.
  - Guided template buttons instead of an open free-form question box for MVP.
- Runtime note: new assignment/status files take effect on next worker preflight/Codex launch. Visible tab titles require relaunching the pony terminal/session layout. Already-running agents need restart or explicit assignment update.
- Pinkie documentation update: Weave support case `901174` is closed and Weave will not provide an API.
- Documentation consequence: remove any wording that implies pending Weave API access or a future bootstrap extract from Weave support; document the track as manual CSV import/export reconciliation only.
- Handoff from FS for Handshake app team: we now have live Instinct appointment lifecycle evidence from three HAR captures in `/home/ggb66/dev/EVH/`.
  - Create call: `createCalendarAppointment`
    - created appointment id: `1066`
    - payload fields: `locationId=1`, `appointmentTypeId=35`, `confirmed=false`, `date=2026-05-20`, `startTime=21:00:00`, `durationInMinutes=30`, `notes=None`, `patientId=67`, `providerId=199`, `reason=Attacked by Carnivorous Plant`, `serviceId=36`, `failOnConflict=true`, `acknowledgedConflictingIds=[]`, `acknowledgedReservationIds=[]`
  - Reschedule call: `reviseCalendarAppointment`
    - same appointment id: `1066`
    - updated fields: `startTime=22:15:00`, `durationInMinutes=45`
    - retained fields: same location, provider, appointment type, patient, service, reason, notes, and confirmed flag
  - Cancel call: `setCalendarAppointmentStatus`
    - same appointment id: `1066`
    - final status: `CANCELLED`
    - the response revision history shows prior edits before cancel: `21:00:00 -> 22:00:00`, then `22:00:00 -> 22:15:00` plus `duration_in_minutes 30 -> 45`, then the status change to cancelled
  - Supporting list/fetch operations were present in the reschedule capture and are enough to build lookup-driven UI mapping:
    - `GetServiceList`
    - `appointmentTypes`
    - `listActiveUsers`
    - `listActiveProviders`
    - `listActiveStaff`
    - `getLocationsWithReminderConfigurations`
    - `getLocationByInstinctId`
    - `getPatientById`
    - `getPatientLastVisit`
    - `listRoutingClients`
    - `getCalendarAppointments`
    - `calendarEntries`
  - Important practical note: the UI can likely be built as a Handshake scheduling page that lets users click an open slot, choose doctor vs `Tech`, fill a small form, and then save only if the slot is open and the duration does not overlap another appointment.
  - Important integration caveat: the real difficulty is not the form, it is the mapping and validation layer. We still need rules for translating Weave-side data into Instinct IDs for `patientId`, `providerId`, `locationId`, `appointmentTypeId`, and `serviceId`, plus the lookup for the existing appointment when rescheduling or canceling.
  - Useful implementation assumption: `Tech` appointments are a first-class appointment type (`Technician Appointments (Tech)`).
  - Suggested product scope for Handshake app team:
    - day/week schedule view with open slots
    - click-to-create from an open slot
    - simple form with provider/type/service dropdowns
    - validation for conflict/overlap/slot length
    - submit to Instinct using the same lifecycle endpoints already proven by HAR
  - Rough effort estimate from FS:
    - MVP: 2 to 5 days
    - solid version with mapping/validation/retries: 1 to 2 weeks
    - production-hardening: 2+ weeks
  - No production implementation has been started in EVH for this scheduler yet; this is handoff/design input only.
- Twilight handoff for tomorrow morning: EVH now has a live Vetcove-format patient export path in `scripts/export_vetcove_patients.py` built on the shared Instinct pagination client in `scripts/instinct_partner_client.py`.
- Live result to preserve: `/home/ggb66/dev/EVH/vetcove_patients.csv` was generated successfully from the tenant with `19,563` living-patient rows (`27,102` total patients scanned, `7,539` non-living skipped).
- Mapping decisions now explicit:
  - `Division` is hard-coded as `Eustis Veterinary Hospital` on every row.
  - missing city/state/zip are backfilled conservatively: keep real city when present, fill missing state as `FL`, infer missing zip from the most common zip already seen for that city, and fall back to `Eustis / FL / 32726` only when city is missing too.
- Current Vetcove import-readiness gaps to document clearly:
  - `Last Visit` still missing on `19,083` rows because many patients do not have a usable past appointment in the Partner feed.
  - `Animal Weight (lb)` missing on `19,145` rows.
  - `Date of Birth` missing on `1,824` rows.
  - `Physical Address Street 1` still missing on `44` rows.
  - both email/mobile missing on `200` rows.
- New verification to record:
  - `.venv/bin/python -m pytest -q tests/test_instinct_partner_client.py tests/test_vetcove_patient_export.py`
  - result: `6 passed`
- Appointment contract reminder to document:
  - `GET /v1/appointments` works for listing.
  - `GET /v1/appointments/{id}` works for fetch.
  - `POST /v1/appointments/{appointment_id}/cancellation` is the documented cancel route.
  - `PATCH /v1/appointments/{appointment_id}` only has documented proof for `isConfirmed`; rescheduling is not yet documented or proven.
- AJ note: HAR captured the Instinct reminder write path. The browser uses `AddPatientReminder` with `patientId`, `reminderLabelId`, `notes`, `remindOn`, `locationId`, `isActive`, and `lastAdministeredOn`. Please record this interaction and note that the save request is a GraphQL mutation to `https://evh.api.instinctvet.com/`.
- AJ note: we likely have enough to draft curl requests for missing reminders, but we still need the full per-row reminder mapping and any duplicate/ordering rules before treating the batch as safe to generate automatically.
- AJ note: explicit `curl --resolve` on the Instinct auth host plus a live bearer token was enough to make the reminder API path work when the normal resolver path was flaky. Keep that in mind for future API integrations that look blocked by DNS.
- Pinkie documentation status update: Contacts work is currently blocked on Weave support case `901174` for export credentials/access.
- Please document that the isolation refactor is now complete:
  - branch namespace: `pony/pinkie/weave-contact-bootstrap`
  - Pinkie-owned entry point: `scripts/contacts/weave_contact_sync.py`
  - supporting package marker: `scripts/contacts/__init__.py`
- Current operator state to capture:
  - live Instinct export already exists
  - do not import into Weave yet
  - wait for Weave extract/bootstrap reconciliation first because overlap with legacy Avimark contacts is expected
- Track the support dependency explicitly in docs/notes: Weave case `901174` submitted, awaiting response
- Pinkie documentation update: the Weave Contacts work has progressed from design/dry-run into a live initial Instinct export.
- New implementation behavior to document:
  - `scripts/weave_contact_sync.py` now emits Weave bulk-import CSV files, not JSONL
  - exports are incremental for ongoing runs via persisted payload hashes and watermark state
  - files are chunked for Weave import limits
- Live run results to capture:
  - `11,968` Instinct accounts exported
  - `2` marked inactive
  - output files:
    - `/tmp/evh-weave-contact-csv-20260422-161314/weave_contacts_001.csv`
    - `/tmp/evh-weave-contact-csv-20260422-161314/weave_contacts_002.csv`
  - state file:
    - `/tmp/evh-weave-contact-sync-state.json`
- Important limitation to document clearly: these CSVs should not be imported into Weave yet because Weave already contains legacy Avimark contacts and a bootstrap reconciliation/export from Weave is still required to avoid large duplicate overlap.
- Current operational blocker to mention: waiting on Weave application credentials/export access; user has requested credentials from `e-services@dsn.com`.
- Pinkie documentation handoff: Weave Contacts Phase 1 groundwork is now in place and should be documented.
- New implementation files to cover: `scripts/weave_contact_sync.py` and the expanded account normalization/projection logic in `scripts/instinct_accounts.py`.
- New tests to mention: `tests/test_weave_contact_sync.py` and the added normalization coverage in `tests/test_instinct_accounts.py`.
- Current behavior: periodic Instinct account polling with overlap-window watermarking, `includeDeleted` handling, projection into a Weave-shaped contact payload, Weave CSV export batches, and local file-backed sync state.
- Important limitation to document clearly: this is EVH-side Phase 1 only; production hookup is blocked on the real Weave contact contract, auth, external ID mapping, and any approved Weave-to-Instinct writeback scope.
- Rarity documentation handoff: stockroom planning docs are now in place and should be incorporated into EVH operator-facing documentation.
- Key planning direction: Instinct / Stockroom is the target inventory system of record; Inventory Ally is the transition system during cutover.
- EVH stock areas currently identified: Treatment, Pharmacy, Reception, Lab, Kennel, Room 1-5, Autoclave, X-Ray / Dental.
- Likely first-wave stockroom rollout locations: Treatment, Pharmacy, Reception, Lab, and Kennel.
- New docs to cover:
  - `docs/inventory-ally-stockroom-rollout-plan.md`
  - `docs/inventory-ally-stockroom-exec-summary.md`
  - `docs/inventory-ally-stockroom-ownership-matrix.md`
  - `docs/inventory-ally-stockroom-discovery-checklist.md`
- Important limitation to document clearly: workflow ownership is not fully finalized yet because the missing IA / Stockroom workflow detail still has to be gathered from system evidence rather than memory.
- Suggested doc follow-up: summarize the current plan and include a short request list for IA / Instinct screenshots, exports, and workflow confirmation.
- RD documentation handoff: Vetcove Home Delivery investigation is documented in `docs/vetcove-instinct-home-delivery-design.md`.
- New implementation files to cover from the Vetcove side: `scripts/instinct_accounts.py` as the reusable Instinct identity adapter and the reminder importer refactor that now builds on it in `scripts/evh_reminder_importer.py`.
- New tests to mention: `tests/test_instinct_accounts.py`.
- Important Vetcove summary to document clearly: recommended operating model is Instinct as source of truth and Vetcove Home Delivery as the client storefront and order channel; remaining blocker is Vetcove confirmation of the Instinct-specific Rx sync, required fields and identifiers, and order or refill writeback contract.
- Additional RD documentation note: record that the Vetcove track has been normalized to the pony isolation policy. Future implementation belongs on `pony/rd/*` branches, and any new Vetcove-specific scripts must go under `scripts/vetcove/`.
- Current Vetcove status to preserve: no production integration code exists yet for Vetcove itself; the project currently has planning/design material plus reusable Instinct-side identity groundwork only.
- New RD documentation handoff: live prescription payload notes now exist in `docs/instinct-prescription-payload-notes.md`.
- Important field-level summary to preserve: `external-prescriptions` includes embedded product label/unit metadata, `quantityPerFill`, and `pharmacyNote`, while `dispensed-prescriptions` includes `accountId`, `productId`, `prescribedAt`, and `remainingFills`.
- Important caveat to document clearly: the recommendation that `external-prescriptions` is the likely Vetcove-facing export feed is an EVH inference from live payloads, not something Vetcove or Instinct explicitly documented.
- FS status update: added a shared Instinct Partner API scaffold for contact and appointment sync in the EVH worktree.
- New files to document: `scripts/instinct_partner_client.py`, `scripts/instinct_accounts.py`, `scripts/instinct_appointments.py`, `scripts/instinct_sync_runner.py`, and `scripts/__init__.py`.
- Runner behavior to capture: incremental feed pulls, persisted watermark state, structured export records with idempotency keys, and conflict flags for downstream Weave mirroring.
- Docs updated: `README.md` and `docs/instinct-import.md`.
- Verification result: focused sync/normalization tests are green with `8 passed`.
- Appointment contract notes added in `docs/instinct-appointments-contract-notes.md`.
- Document the six appointment endpoints and the one explicit writable field the Instinct docs expose: `isConfirmed` on `PATCH /v1/appointments/{appointment_id}`.
- The docs pages I checked did not show JSON examples, so the writeup should clearly say the exact payload shapes still need live API responses or an OpenAPI source if we want field-by-field schemas.
- FS latest status: Scheduling work is paused; current branch work is documentation/sample-capture only, so Spike should record it as docs work rather than active Scheduling implementation.
- Rarity documentation follow-up: update the stockroom docs to reflect the newly confirmed workflows and the pending Instinct-human response.
- Newly confirmed IA workflows to document: vendor item / PIMS mapping, UOM and pack-size setup, on-hand quantity tracking via counts and estimated quantities, cycle counts via the Counting page / weekly list, and inventory reporting via Inventory Analysis export.
- Newly confirmed Stockroom capabilities to document: room-level quantity tracking, multi-room item support, room-only tracking without sub-locations, locations managed by `Code` and `Label`, buying-unit to selling-unit conversion, and export coverage for cycle counts, inventory history, and analytics.
- New explicit EVH planning assumption to document: manual location creation in Stockroom is acceptable because the location count is small.
- Pending human-response section to document: migration path, shadow mode, stable IDs, API endpoints, PIMS mapping migration support, cycle count data behavior, approval/review workflow, location code stability, and multi-room export/API representation.
## 2026-07-02T03:19:52.793368236+00:00
- FROM: ✶ Twilight Sparkle
- TO: Spike
- SUBJECT: please read twilights mai
- BODY:
```text
lbox notes to you.  We need you to update your documentation regarding the DB and DB state and commit and push those changes.
```

## 2026-07-02T03:19:52.793368236+00:00
- FROM: ✶ Twilight Sparkle
- TO: Spike
- SUBJECT: please read twilights mai
- BODY:
```text
lbox notes to you.  We need you to update your documentation regarding the DB and DB state and commit and push those changes.
```
```

## twi.mailbox.md archived tail
```md
## 2026-07-02T16:38:49.050782925+00:00
- FROM: ⚡ Rainbow Dash
- TO: Twilight Sparkle
- SUBJECT: Sparkle Twilight, here’s
- BODY:
```text
the plan to note:

  - Refactor the PDF path into a real pipeline:
      - fetch_instinct_pdf
      - extract_pdf_pages
      - load_keyword_index from the DB
      - annotate_pages_with_keywords
      - generate_client_summary
      - persist_page_chunks_and_summary
  - Keep page-first extraction, not tiny blind chunks.
  - Measure and print:
      - fetch time
      - extraction time
      - page chunking time
      - keyword matching time
      - client-summary time
      - DB/vector write time
      - total text volume and chunk counts
  - Store canonical summary and keyword mapping outside the vector store too, then attach them as metadata to the page/chunk
    records.
  - Make the whole thing LangChain-friendly so a human can inspect and edit each stage.

  I couldn’t write that into the authoritative pony/team.coordination/* files from this session because those root files aren’t
  in my writable scope, so this is the durable note request I’d want Twilight to capture.
```

## 2026-07-03T18:39:24.733122662+00:00
- FROM: ⚡ Rainbow Dash
- TO: Twilight Sparkle
- SUBJECT: Sparkle D's next slice is
- BODY:
```text
 the PDF chunker: skip PDFs with no text layer using 204 status/error text, extract terms from meds/treatments/products, generate
    a veterinary clinical summary for each full PDF, add a summary column, attach terms to chunk metadata, and store enhanced chunks in the vector DB.
    AJ needs to provide the vector DB connection information.
```
```
