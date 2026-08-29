ALTER TABLE IF EXISTS public.instinct_owner_lookup_norm RENAME TO instinct_owner_lookup;

ALTER TABLE IF EXISTS public.instinct_owner_lookup
    ADD COLUMN IF NOT EXISTS updated_at timestamptz NOT NULL DEFAULT now(),
    ADD COLUMN IF NOT EXISTS deleted_at timestamptz,
    ADD COLUMN IF NOT EXISTS merged_into_account_id text,
    ADD COLUMN IF NOT EXISTS synced_at timestamptz NOT NULL DEFAULT now();

ALTER TABLE IF EXISTS public.instinct_owner_lookup
    ALTER COLUMN account_id SET NOT NULL,
    ALTER COLUMN owner_name SET NOT NULL;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'instinct_owner_lookup_pkey'
    ) THEN
        ALTER TABLE public.instinct_owner_lookup
            ADD CONSTRAINT instinct_owner_lookup_pkey PRIMARY KEY (account_id);
    END IF;
END$$;

CREATE INDEX IF NOT EXISTS instinct_owner_lookup_owner_name_lower_idx
    ON public.instinct_owner_lookup (lower(owner_name));

CREATE INDEX IF NOT EXISTS instinct_owner_lookup_owner_name_last_first_idx
    ON public.instinct_owner_lookup (owner_name_last_first);

CREATE INDEX IF NOT EXISTS instinct_owner_lookup_phone_digits_idx
    ON public.instinct_owner_lookup (phone_digits);

ALTER TABLE IF EXISTS public.instinct_patient_lookup
    ALTER COLUMN updated_at SET DEFAULT now();

ALTER TABLE IF EXISTS public.instinct_patient_lookup
    ADD COLUMN IF NOT EXISTS deleted_at timestamptz,
    ADD COLUMN IF NOT EXISTS merged_into_patient_id bigint,
    ADD COLUMN IF NOT EXISTS synced_at timestamptz NOT NULL DEFAULT now();

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'instinct_patient_lookup_account_patient_uniq'
    ) THEN
        ALTER TABLE public.instinct_patient_lookup
            ADD CONSTRAINT instinct_patient_lookup_account_patient_uniq UNIQUE (account_id, patient_pims_code);
    END IF;
END$$;

CREATE INDEX IF NOT EXISTS instinct_patient_lookup_account_patient_lower_idx
    ON public.instinct_patient_lookup (account_id, lower(patient_name));
