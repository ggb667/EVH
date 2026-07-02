CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS pms_source_document (
    id uuid PRIMARY KEY,
    source_system text NOT NULL,
    source_reference_id text NOT NULL,
    clinic_id text NOT NULL,
    client_id text NULL,
    pet_id text NULL,
    filename text NOT NULL,
    source_uri text NOT NULL,
    source_checksum text NOT NULL,
    mime_type text NOT NULL,
    page_count integer NOT NULL,
    ingest_status text NOT NULL,
    ingest_error_code text NULL,
    ingest_error_detail text NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT pms_source_document_uniq UNIQUE (source_system, source_reference_id),
    CONSTRAINT pms_source_document_ingest_status_chk CHECK (
        ingest_status IN ('queued', 'running', 'succeeded', 'needs_review', 'failed', 'skipped')
    )
);

CREATE INDEX IF NOT EXISTS pms_source_document_client_id_idx
    ON pms_source_document (client_id);

CREATE INDEX IF NOT EXISTS pms_source_document_pet_id_idx
    ON pms_source_document (pet_id);

CREATE TABLE IF NOT EXISTS pms_document_page (
    id uuid PRIMARY KEY,
    document_id uuid NOT NULL REFERENCES pms_source_document (id) ON DELETE CASCADE,
    page_number integer NOT NULL,
    page_label text NULL,
    extracted_text text NOT NULL,
    text_search tsvector GENERATED ALWAYS AS (to_tsvector('english', coalesce(extracted_text, ''))) STORED,
    extraction_method text NOT NULL,
    text_quality_score numeric NULL,
    has_ocr boolean NOT NULL DEFAULT false,
    source_page_link text NOT NULL,
    page_status text NOT NULL,
    page_error_code text NULL,
    page_error_detail text NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT pms_document_page_uniq UNIQUE (document_id, page_number),
    CONSTRAINT pms_document_page_status_chk CHECK (
        page_status IN ('queued', 'running', 'succeeded', 'needs_review', 'failed', 'skipped')
    )
);

CREATE INDEX IF NOT EXISTS pms_document_page_document_id_idx
    ON pms_document_page (document_id);

CREATE INDEX IF NOT EXISTS pms_document_page_text_search_idx
    ON pms_document_page USING GIN (text_search);

CREATE TABLE IF NOT EXISTS pms_page_chunk (
    id uuid PRIMARY KEY,
    page_id uuid NOT NULL REFERENCES pms_document_page (id) ON DELETE CASCADE,
    chunk_index integer NOT NULL,
    chunk_text text NOT NULL,
    chunk_search tsvector GENERATED ALWAYS AS (to_tsvector('english', coalesce(chunk_text, ''))) STORED,
    embedding_model text NOT NULL,
    embedding vector NOT NULL,
    char_start integer NOT NULL,
    char_end integer NOT NULL,
    chunk_status text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT pms_page_chunk_uniq UNIQUE (page_id, chunk_index),
    CONSTRAINT pms_page_chunk_status_chk CHECK (
        chunk_status IN ('queued', 'running', 'succeeded', 'needs_review', 'failed', 'skipped')
    ),
    CONSTRAINT pms_page_chunk_span_chk CHECK (char_end >= char_start)
);

CREATE INDEX IF NOT EXISTS pms_page_chunk_page_id_idx
    ON pms_page_chunk (page_id);

CREATE INDEX IF NOT EXISTS pms_page_chunk_chunk_search_idx
    ON pms_page_chunk USING GIN (chunk_search);

CREATE INDEX IF NOT EXISTS pms_page_chunk_embedding_idx
    ON pms_page_chunk USING ivfflat (embedding vector_cosine_ops);

CREATE TABLE IF NOT EXISTS rag_detected_term (
    id uuid PRIMARY KEY,
    chunk_id uuid NULL REFERENCES pms_page_chunk (id) ON DELETE CASCADE,
    page_id uuid NULL REFERENCES pms_document_page (id) ON DELETE CASCADE,
    dictionary_term_id bigint NOT NULL,
    dictionary_term_source text NOT NULL DEFAULT 'mariadb',
    matched_text text NOT NULL,
    normalized_text text NOT NULL,
    confidence numeric NOT NULL,
    location_json jsonb NOT NULL,
    snippet text NULL,
    context_classification text NULL,
    detection_status text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT rag_detected_term_source_chk CHECK (chunk_id IS NOT NULL OR page_id IS NOT NULL),
    CONSTRAINT rag_detected_term_dictionary_term_source_chk CHECK (dictionary_term_source IN ('mariadb')),
    CONSTRAINT rag_detected_term_status_chk CHECK (
        detection_status IN ('queued', 'running', 'succeeded', 'needs_review', 'failed', 'skipped')
    )
);

CREATE INDEX IF NOT EXISTS rag_detected_term_chunk_id_idx
    ON rag_detected_term (chunk_id);

CREATE INDEX IF NOT EXISTS rag_detected_term_page_id_idx
    ON rag_detected_term (page_id);

CREATE INDEX IF NOT EXISTS rag_detected_term_dictionary_term_id_idx
    ON rag_detected_term (dictionary_term_id);

CREATE TABLE IF NOT EXISTS rag_document_group (
    id uuid PRIMARY KEY,
    source_document_id uuid NOT NULL REFERENCES pms_source_document (id) ON DELETE CASCADE,
    start_page integer NOT NULL,
    end_page integer NOT NULL,
    probable_date date NULL,
    probable_type text NULL,
    probable_source text NULL,
    confidence numeric NOT NULL,
    group_status text NOT NULL,
    group_error_code text NULL,
    group_error_detail text NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT rag_document_group_uniq UNIQUE (source_document_id, start_page, end_page),
    CONSTRAINT rag_document_group_span_chk CHECK (end_page >= start_page),
    CONSTRAINT rag_document_group_status_chk CHECK (
        group_status IN ('queued', 'running', 'succeeded', 'needs_review', 'failed', 'skipped')
    )
);

CREATE INDEX IF NOT EXISTS rag_document_group_source_document_id_idx
    ON rag_document_group (source_document_id);

CREATE INDEX IF NOT EXISTS rag_document_group_probable_date_idx
    ON rag_document_group (probable_date);

CREATE TABLE IF NOT EXISTS rag_document_summary (
    id uuid PRIMARY KEY,
    document_group_id uuid NOT NULL REFERENCES rag_document_group (id) ON DELETE CASCADE,
    client_id text NOT NULL,
    pet_id text NULL,
    summary_text text NOT NULL,
    key_medications jsonb NOT NULL DEFAULT '[]'::jsonb,
    key_treatments jsonb NOT NULL DEFAULT '[]'::jsonb,
    key_findings jsonb NOT NULL DEFAULT '[]'::jsonb,
    source_link text NOT NULL,
    summary_model text NOT NULL,
    summary_status text NOT NULL,
    summary_confidence numeric NOT NULL,
    review_state text NOT NULL,
    reviewed_at timestamptz NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT rag_document_summary_status_chk CHECK (
        summary_status IN ('queued', 'running', 'succeeded', 'needs_review', 'failed', 'skipped')
    )
);

CREATE INDEX IF NOT EXISTS rag_document_summary_client_id_idx
    ON rag_document_summary (client_id);

CREATE INDEX IF NOT EXISTS rag_document_summary_pet_id_idx
    ON rag_document_summary (pet_id);

CREATE INDEX IF NOT EXISTS rag_document_summary_review_state_idx
    ON rag_document_summary (review_state);

CREATE TABLE IF NOT EXISTS rag_ingestion_run (
    id uuid PRIMARY KEY,
    source_system text NOT NULL,
    run_kind text NOT NULL,
    run_status text NOT NULL,
    watermark_start timestamptz NULL,
    watermark_end timestamptz NULL,
    started_at timestamptz NOT NULL,
    finished_at timestamptz NULL,
    source_document_count integer NOT NULL DEFAULT 0,
    page_count integer NOT NULL DEFAULT 0,
    chunk_count integer NOT NULL DEFAULT 0,
    term_count integer NOT NULL DEFAULT 0,
    group_count integer NOT NULL DEFAULT 0,
    summary_count integer NOT NULL DEFAULT 0,
    error_count integer NOT NULL DEFAULT 0,
    error_code text NULL,
    error_detail text NULL,
    extractor_version text NULL,
    embedding_model text NULL,
    summary_model text NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT rag_ingestion_run_status_chk CHECK (
        run_status IN ('queued', 'running', 'succeeded', 'needs_review', 'failed', 'skipped')
    )
);

CREATE INDEX IF NOT EXISTS rag_ingestion_run_source_system_idx
    ON rag_ingestion_run (source_system);

CREATE INDEX IF NOT EXISTS rag_ingestion_run_run_status_idx
    ON rag_ingestion_run (run_status);
