-- Add missing resume / verification columns to the existing Instinct tables.
-- This is additive only: no CREATE TABLE, no table replacement.

ALTER TABLE rag_source_document
    ADD COLUMN IF NOT EXISTS source_system TEXT,
    ADD COLUMN IF NOT EXISTS source_reference_id TEXT,
    ADD COLUMN IF NOT EXISTS original_filename TEXT,
    ADD COLUMN IF NOT EXISTS remote_content_length BIGINT,
    ADD COLUMN IF NOT EXISTS downloaded_sha256 TEXT,
    ADD COLUMN IF NOT EXISTS chunker_version TEXT,
    ADD COLUMN IF NOT EXISTS embedding_model TEXT,
    ADD COLUMN IF NOT EXISTS vector_dimensions INTEGER,
    ADD COLUMN IF NOT EXISTS fetch_uri TEXT,
    ADD COLUMN IF NOT EXISTS fetch_uri_observed_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS local_cache_path TEXT;

ALTER TABLE pms_page_chunk
    ADD COLUMN IF NOT EXISTS source_system TEXT,
    ADD COLUMN IF NOT EXISTS source_reference_id TEXT,
    ADD COLUMN IF NOT EXISTS original_filename TEXT,
    ADD COLUMN IF NOT EXISTS chunker_version TEXT,
    ADD COLUMN IF NOT EXISTS embedding_model TEXT,
    ADD COLUMN IF NOT EXISTS vector_dimensions INTEGER,
    ADD COLUMN IF NOT EXISTS fetch_uri TEXT,
    ADD COLUMN IF NOT EXISTS fetch_uri_observed_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS local_cache_path TEXT;

ALTER TABLE rag_deferred_ocr_document
    ADD COLUMN IF NOT EXISTS source_system TEXT,
    ADD COLUMN IF NOT EXISTS original_filename TEXT,
    ADD COLUMN IF NOT EXISTS remote_content_length BIGINT,
    ADD COLUMN IF NOT EXISTS downloaded_sha256 TEXT,
    ADD COLUMN IF NOT EXISTS content_hash TEXT,
    ADD COLUMN IF NOT EXISTS content_length BIGINT,
    ADD COLUMN IF NOT EXISTS fetch_uri TEXT,
    ADD COLUMN IF NOT EXISTS fetch_uri_observed_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS local_cache_path TEXT;

UPDATE rag_deferred_ocr_document
SET document_pdf_id = COALESCE(document_pdf_id, source_reference_id)
WHERE document_pdf_id IS NULL
  AND source_reference_id IS NOT NULL;

UPDATE rag_deferred_ocr_document
SET status = 'loaded'
WHERE status IN ('complete', 'load_complete', 'skipped_already_loaded');

ALTER TABLE rag_deferred_ocr_document
    DROP COLUMN IF EXISTS source_reference_id;

-- Resume-path indexes:
-- - document_pdf_id supports direct deferred-row lookups by PDF ID
-- - the active-bucket partial index keeps worker-state lookups small and fast
CREATE INDEX CONCURRENTLY IF NOT EXISTS rag_deferred_ocr_document_document_pdf_id_idx
    ON rag_deferred_ocr_document (document_pdf_id);

CREATE INDEX CONCURRENTLY IF NOT EXISTS rag_deferred_ocr_document_active_bucket_idx
    ON rag_deferred_ocr_document (status, document_pdf_id)
    WHERE status IN ('ocr_needed', 'pending', 'ocr_not_reached_deferred', 'deferred');

CREATE INDEX CONCURRENTLY IF NOT EXISTS rag_deferred_ocr_document_content_hash_idx
    ON rag_deferred_ocr_document (content_hash)
    WHERE content_hash IS NOT NULL;

CREATE INDEX CONCURRENTLY IF NOT EXISTS rag_deferred_ocr_document_status_content_hash_idx
    ON rag_deferred_ocr_document (status, content_hash)
    WHERE content_hash IS NOT NULL;

ALTER TABLE rag_pdf_ocr_page
    ADD COLUMN IF NOT EXISTS source_system TEXT,
    ADD COLUMN IF NOT EXISTS source_reference_id TEXT,
    ADD COLUMN IF NOT EXISTS original_filename TEXT,
    ADD COLUMN IF NOT EXISTS fetch_uri TEXT,
    ADD COLUMN IF NOT EXISTS fetch_uri_observed_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS local_cache_path TEXT;
