# EVH RAG architecture handoff

Date: `2026-07-01`
Scope: EVH RAG MVP architecture, worker contracts, and rollout milestones

This note captures the current EVH RAG assignment for Spike and the live cross-track
status from the Twilight handoff on 2026-06-30.

## First milestone

The first serious milestone is a timeline for one selected client/pet that shows:

- reconstructed document summaries
- the source PDF page range behind each summary
- direct links back to the correct PDF page

That milestone proves the full chain from PDF discovery to page extraction, grouping,
summary generation, and source-linked display.

## Product shape

- Ingest large PMS PDFs or stable PDF references.
- Extract text page by page.
- Store page text, page links, document boundaries, summaries, detected terms, embeddings,
  and status/confidence fields in Handshake's Aurora MySQL/MariaDB-compatible database.
- Reconstruct sub-documents from merged legacy PDFs.
- Show a scoped client/pet timeline with source links.
- Use guided templates instead of free-form questions for MVP.

## Tooling decisions

- Database: Handshake's Aurora MySQL, MariaDB-compatible database for the current shared load target.
- Database state: use durable ingestion/load state rows in the same MariaDB-compatible store first.
- Database state: the shared dictionary seed is already loaded and verified at 3,133 `rag_dictionary_term` rows; do not route a duplicate seed/load retry for that data.
- Python package manager: `uv`.
- PDF extraction: start with PyMuPDF.
- OCR: add Tesseract or AWS Textract only for scanned or image-only pages.
- Search: combine keyword/full-text search with vector search; do not rely on vector search alone.
- AI: embeddings plus LLM summaries/classification, likely OpenAI or Bedrock.
- LangGraph: not required for MVP ingestion; use durable DB ingestion/load states first.
- Keep the RAG database separate from the operational identity store.
- Use guided templates instead of a free-form question box for the MVP.

## Worker contracts

- RD: PDFs. Obtain PMS/Instinct PDF files or stable PDF references for initial ingestion.
- AJ: DB. Keep the Handshake Aurora MySQL/MariaDB-compatible load state current and verify any newly assigned loads.
- Rarity: Meds & Treatments. The shared dictionary seed has already been delivered to AJ and loaded; only make corrections if assigned.
- FS: Vet Terms. Define document type clues, source clues, treatment context terms, and template terminology.
- Spike: Docs. Document the architecture, worker contracts, and MVP milestones.
- Twilight: Coordination.
- Pinkie: Idle for this split.

Worker boundaries that matter:

- RD should focus on source acquisition and PDF references, not schema design.
- AJ should keep the RAG storage/load path separate from the operational identity migration path.
- Rarity and FS should feed deterministic dictionaries and context rules, not summary logic; the existing shared dictionary seed should not be rebuilt or reloaded unless assigned.
- Spike should keep the architecture doc aligned with the live coordination state.

## Data model to document

- `pms_document`: client_id, pet_id, PMS IDs/attachment IDs, filename, page_count, PMS reference/access URL, import_status.
- `pdf_page`: document_id, page_number, extracted_text, extraction_method, text_quality, source page link.
- `medication_dictionary`: canonical_name, aliases, category, active/inactive.
- `treatment_dictionary`: canonical_name, aliases, category, active/inactive.
- `detected_term`: page_id, term_type, canonical_name, matched_text, confidence, location/snippet.
- `document_group`: source_pdf_id, start_page, end_page, probable_date, probable_type, probable_source, confidence.
- `document_summary`: document_group_id, client_id, pet_id, summary, key_medications, key_treatments,
  key_findings, start_page, end_page, source_link, confidence.

The operator rule is that every derived result must trace back to a source PDF and page range.

## MVP milestones

1. Page index: PMS document reference, PDF page extraction, MariaDB-compatible page storage, page links,
   and basic client/pet/name search.
2. Medication/treatment detection: load dictionaries, detect terms on pages, show mentions with citations.
3. Document grouping: infer start/end pages, classify type, detect dates, create groups.
4. Summaries: short document summaries, timeline, hyperlinks to source pages.
5. Guided template answers: canned workflows only, with citations and context categories.
6. Admin correction: fix grouping, dates, document types, summaries, and false term matches.

The first release should use durable ingestion states at each stage instead of inferring failure
from missing data.

## Context policy

- For medications, distinguish current/home medication, prescribed at visit, administered in clinic,
  historical mention, and unclear mention.
- For treatments, distinguish performed, recommended, declined, planned, historical mention, and unclear.
- Deterministic term detection answers what terms are present; model summaries answer what those
  mentions mean in context.

## Runtime and relaunch note

- New assignment/status files take effect on the next worker preflight or Codex launch.
- Visible tab titles require relaunching the pony terminal/session layout.
- Already-running agents need restart or an explicit assignment update.

If the worker layout or visible tab titles need to change, relaunch the pony session layout.
Existing agents will not pick up assignment changes just because the files changed on disk.

## Startup snapshot

- Spike owns Docs for the RAG split.
- The doc target is the first milestone: one client/pet timeline with source-linked summaries.
- The shared design anchor is the AJ load-state correction and the PDF ingestion policy.
- The work should stay on durable MariaDB-compatible ingestion/load states and guided templates.
- The shared DB state is already seeded at 3,133 `rag_dictionary_term` rows in Handshake's Aurora MySQL/MariaDB-compatible store.
- Spike should document the loaded state, not a duplicate seed path.
- The live coordination files in the root pony tree are the canonical record, but this local note is the fast startup path for the spike worktree.

## Immediate next step

Keep this handoff note current and sync any new Twilight delta into the root coordination files when the writable path is available.
