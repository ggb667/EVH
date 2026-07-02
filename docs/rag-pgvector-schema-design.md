# EVH RAG schema and storage design

## Goal

Store large PMS PDFs in a way that supports:

- page-by-page extraction
- source-linked timeline reconstruction
- medication and treatment term detection
- document grouping and summarization
- keyword plus vector search in Postgres
- durable ingestion status tracking

This is an MVP design for the EVH RAG track. It assumes a separate PostgreSQL database with `pgvector` and Postgres full-text search for the vector data.

The EVH RAG vector database is separate from any operational identity store. Keep the client/patient tables out of the vector database and load them through a separate migration path.

## Design principles

1. Keep the original PDF as the source of truth.
2. Store page text separately from derived search artifacts.
3. Make every derived row trace back to a document, page, and source run.
4. Use explicit statuses instead of implicit failure inference.
5. Preserve raw source evidence for audit and reprocessing.
6. Keep dictionary terms stable and independent from page extraction.

## Storage layers

### 1. Source object layer

Store the original PDF outside the database, then track it in a document table.

Recommended fields:

- `source_uri` or object storage key
- `source_checksum`
- `filename`
- `mime_type`
- `page_count`
- `clinic_id`
- `client_id`
- `pet_id`
- `source_system`
- `source_reference_id`
- `ingest_status`
- `ingest_error_code`
- `ingest_error_detail`

The source row should point to the canonical PDF location and act as the parent for page, term, grouping, and summary records.

Recommended database location:

- PostgreSQL vector store
- `pgvector` for embeddings
- Postgres full-text search for page and chunk text

### 2. Page layer

Store one row per PDF page with the extracted text and page-level metadata.

Recommended fields:

- `document_id`
- `page_number`
- `page_label`
- `extracted_text`
- `text_search` as `tsvector`
- `extraction_method` (`pymupdf`, `ocr`, `hybrid`)
- `text_quality_score`
- `has_ocr`
- `source_page_link`
- `page_status`
- `page_error_code`
- `page_error_detail`

If a page is too large for a single embedding chunk, split it into page chunks rather than forcing a truncated page row.

### 3. Chunk and embedding layer

Use a chunk table for vector search rather than attaching a single embedding directly to the page row.

Recommended fields:

- `page_id`
- `chunk_index`
- `chunk_text`
- `chunk_search` as `tsvector`
- `embedding_model`
- `embedding`
- `char_start`
- `char_end`
- `chunk_status`

This keeps vector search stable even when a page contains multiple clinically relevant sections.

### 4. Term dictionary layer

Keep the catalog in one shared dictionary table so medications, treatments, vet terms, and stockroom products all search the same way.

Recommended unified structure:

- `term_type` (`medication`, `treatment`, `vet_term`, `product`)
- `canonical_name`
- `aliases`
- `category`
- `active`
- `priority_score`
- `source_note`

The shared table keeps TRI search simple. Use aliases only when the canonical target is unambiguous.

### 5. Detected term layer

Store each detected mention with its source snippet and interpretation metadata.

Recommended fields:

- `chunk_id` or `page_id`
- `dictionary_term_id`
- `matched_text`
- `normalized_text`
- `confidence`
- `location_json`
- `snippet`
- `context_classification`
- `detection_status`

Context classification should distinguish:

- current/home medication
- prescribed at visit
- administered in clinic
- historical mention
- declined / not performed
- planned / follow-up
- unclear

### 6. Document grouping layer

Group pages into reconstructed sub-documents before summarization.

Recommended fields:

- `source_document_id`
- `start_page`
- `end_page`
- `probable_date`
- `probable_type`
- `probable_source`
- `confidence`
- `group_status`
- `group_error_code`
- `group_error_detail`

This is the layer that turns merged legacy PDFs into usable clinical episodes.

### 7. Summary layer

Store one summary per grouped document, plus the source citation needed for the UI.

Recommended fields:

- `document_group_id`
- `client_id`
- `pet_id`
- `summary_text`
- `key_medications`
- `key_treatments`
- `key_findings`
- `source_link`
- `summary_model`
- `summary_status`
- `summary_confidence`
- `review_state`
- `reviewed_at`

The first MVP timeline should read from this table, not directly from raw pages.

## Proposed tables

### `pms_source_document`

One row per PDF or logical PDF source.

Suggested columns:

- `id` uuid primary key
- `source_system` text not null
- `source_reference_id` text not null
- `clinic_id` text not null
- `client_id` text null
- `pet_id` text null
- `filename` text not null
- `source_uri` text not null
- `source_checksum` text not null
- `mime_type` text not null
- `page_count` integer not null
- `ingest_status` text not null
- `ingest_error_code` text null
- `ingest_error_detail` text null
- `created_at`, `updated_at`

Unique constraint recommendation:

- `unique(source_system, source_reference_id)`

### `pms_document_page`

One row per page.

Suggested columns:

- `id` uuid primary key
- `document_id` uuid not null
- `page_number` integer not null
- `page_label` text null
- `extracted_text` text not null
- `text_search` tsvector generated from `extracted_text`
- `extraction_method` text not null
- `text_quality_score` numeric null
- `has_ocr` boolean not null default false
- `source_page_link` text not null
- `page_status` text not null
- `page_error_code` text null
- `page_error_detail` text null
- `created_at`, `updated_at`

Unique constraint recommendation:

- `unique(document_id, page_number)`

### `pms_page_chunk`

One row per searchable chunk.

Suggested columns:

- `id` uuid primary key
- `page_id` uuid not null
- `chunk_index` integer not null
- `chunk_text` text not null
- `chunk_search` tsvector generated from `chunk_text`
- `embedding_model` text not null
- `embedding` vector not null
- `char_start` integer not null
- `char_end` integer not null
- `chunk_status` text not null
- `created_at`, `updated_at`

Unique constraint recommendation:

- `unique(page_id, chunk_index)`

### `rag_dictionary_term`

Unified medication, treatment, and veterinary term dictionary.

Suggested columns:

- `id` uuid primary key
- `term_type` text not null
- `canonical_name` text not null
- `aliases` text[] not null default '{}'
- `category` text null
- `active` boolean not null default true
- `source_note` text null
- `priority_score` integer not null default 100
- `confidence_score` numeric not null default 1.0
- `metadata_json` jsonb not null default '{}'::jsonb
- `created_at`, `updated_at`

Unique constraint recommendation:

- `unique(term_type, canonical_name)`

For the vet-term slice, keep the rows in the separate EVH RAG PostgreSQL schema and seed them from a loadable CSV so later detection jobs can join on stable dictionary metadata instead of hard-coded strings.

Recommended vet-term seed fields:

- `term_type`
- `canonical_name`
- `aliases`
- `category`
- `source_note`
- `active`
- `priority_score`
- `confidence_score`
- `metadata_json`

### `rag_detected_term`

One row per detected mention.

Suggested columns:

- `id` uuid primary key
- `chunk_id` uuid null
- `page_id` uuid null
- `dictionary_term_id` uuid not null
- `matched_text` text not null
- `normalized_text` text not null
- `confidence` numeric not null
- `location_json` jsonb not null
- `snippet` text null
- `context_classification` text null
- `detection_status` text not null
- `created_at`, `updated_at`

Rule:

- require either `chunk_id` or `page_id`
- prefer `chunk_id` when chunking is available

### `rag_document_group`

One row per reconstructed document segment.

Suggested columns:

- `id` uuid primary key
- `source_document_id` uuid not null
- `start_page` integer not null
- `end_page` integer not null
- `probable_date` date null
- `probable_type` text null
- `probable_source` text null
- `confidence` numeric not null
- `group_status` text not null
- `group_error_code` text null
- `group_error_detail` text null
- `created_at`, `updated_at`

Unique constraint recommendation:

- `unique(source_document_id, start_page, end_page)`

### `rag_document_summary`

One row per grouped document summary.

Suggested columns:

- `id` uuid primary key
- `document_group_id` uuid not null
- `client_id` text not null
- `pet_id` text null
- `summary_text` text not null
- `key_medications` jsonb not null default '[]'
- `key_treatments` jsonb not null default '[]'
- `key_findings` jsonb not null default '[]'
- `source_link` text not null
- `summary_model` text not null
- `summary_status` text not null
- `summary_confidence` numeric not null
- `review_state` text not null
- `reviewed_at` timestamptz null
- `created_at`, `updated_at`

### `rag_ingestion_run`

One row per ingestion attempt.

Suggested columns:

- `id` uuid primary key
- `source_system` text not null
- `run_kind` text not null
- `run_status` text not null
- `watermark_start` timestamptz null
- `watermark_end` timestamptz null
- `started_at` timestamptz not null
- `finished_at` timestamptz null
- `source_document_count` integer not null default 0
- `page_count` integer not null default 0
- `chunk_count` integer not null default 0
- `term_count` integer not null default 0
- `group_count` integer not null default 0
- `summary_count` integer not null default 0
- `error_count` integer not null default 0
- `error_code` text null
- `error_detail` text null
- `extractor_version` text null
- `embedding_model` text null
- `summary_model` text null
- `created_at`, `updated_at`

## Status fields

Use explicit status fields at each pipeline stage so the system can resume work and expose operator state.

Recommended enum values:

- `queued`
- `running`
- `succeeded`
- `needs_review`
- `failed`
- `skipped`

Suggested mapping:

- `pms_source_document.ingest_status`
- `pms_document_page.page_status`
- `pms_page_chunk.chunk_status`
- `rag_detected_term.detection_status`
- `rag_document_group.group_status`
- `rag_document_summary.summary_status`
- `rag_ingestion_run.run_status`

If a record is partially processed, keep the row and mark the stage as `needs_review` instead of deleting it.

## Indexing strategy

Recommended indexes:

- B-tree on document identity and source references
- B-tree on `(document_id, page_number)`
- GIN on `tsvector` columns for keyword search
- vector index on `embedding`
- B-tree on `client_id`, `pet_id`, `probable_date`, and `summary_status`

Recommended vector strategy:

- store one embedding per chunk
- keep the embedding model fixed per table or per migration
- do not mix dimensions in the same vector column

## Retrieval path

For the MVP timeline UI:

1. Query `rag_document_summary` by `client_id` and `pet_id`.
2. Join to `rag_document_group`.
3. Join to `pms_source_document` for the PDF reference.
4. Use `source_link` or page links from `pms_document_page` for citations.
5. Fall back to page search and term search when a summary is missing.

For search:

1. Use `tsvector` for exact and keyword matches.
2. Use vector search on `pms_page_chunk.embedding` for semantic retrieval.
3. Merge results with page and summary filters.

## MVP scope recommendation

Build in this order:

1. source document table
2. page table
3. chunk and embedding table
4. dictionary term tables
5. detected term table
6. group table
7. summary table
8. ingestion run table and status reporting

That order gives useful page search before the summarizer is finished.

## Open decisions

- Exact embedding model and vector dimension
- Whether medication and treatment dictionaries stay unified or split into separate tables
- Whether grouping runs should be user-triggered or only automated
- Whether summaries need a formal human review workflow before they appear in the UI

## Suggested next implementation step

Turn this design into a migration set and seed data layer, then wire the extractor to populate:

- source documents
- pages
- chunks
- detected terms
- grouping runs
- summaries

## Migration Plan

Use a two-track migration so the identity data and the RAG vector store do not get tangled together:

1. Prepare the Instinct client and patient exports as normalized CSV files for the operational identity database.
2. Load those identity rows into the separate relational store that owns client and patient lookup.
3. Create the EVH RAG PostgreSQL schema for documents, pages, chunks, terms, groups, summaries, and ingestion runs.
4. Keep original PDFs in object storage and only store references plus derived text and embeddings in Postgres.
5. Backfill the Postgres vector tables from the document pipeline, not from the identity migration.
