-- Add fast identity columns for RAG chunk lookup.
-- Run this once on the live Postgres database.

ALTER TABLE public.pms_page_chunk
  ADD COLUMN IF NOT EXISTS client_id text,
  ADD COLUMN IF NOT EXISTS patient_id text;

UPDATE public.pms_page_chunk
SET client_id = coalesce(
      client_id,
      metadata->>'account_id',
      metadata->>'client_id'
    ),
    patient_id = coalesce(
      patient_id,
      metadata->>'patient_id',
      metadata->>'pet_id'
    )
WHERE client_id IS NULL
   OR patient_id IS NULL;

CREATE INDEX IF NOT EXISTS pms_page_chunk_client_id_idx
  ON public.pms_page_chunk (client_id);

CREATE INDEX IF NOT EXISTS pms_page_chunk_patient_id_idx
  ON public.pms_page_chunk (patient_id);

CREATE INDEX IF NOT EXISTS pms_page_chunk_client_patient_id_idx
  ON public.pms_page_chunk (client_id, patient_id);
