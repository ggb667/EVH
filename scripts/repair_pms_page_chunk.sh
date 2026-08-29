#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  repair_pms_page_chunk.sh [--estimate N] [--batch-size N] [--sleep SECONDS] [--algorithm 1|2|3]

Environment:
  EVH_PGHOST, EVH_PGPORT, EVH_PGDATABASE, EVH_PGUSER, EVH_PGPASSWORD

Defaults:
  --estimate    2424021
  --batch-size  500
  --sleep       0
  --algorithm   1

Notes:
  - Uses the in-place update against public.pms_page_chunk.
  - Prints per-batch timing, rows updated, and an estimated remaining count.
  - Stops when a batch updates 0 rows.
EOF
}

estimate=2424021
batch_size=500
sleep_seconds=0
algorithm=1

while (($#)); do
  case "$1" in
    --estimate)
      estimate="${2:?missing value for --estimate}"
      shift 2
      ;;
    --batch-size)
      batch_size="${2:?missing value for --batch-size}"
      shift 2
      ;;
    --sleep)
      sleep_seconds="${2:?missing value for --sleep}"
      shift 2
      ;;
    --algorithm)
      algorithm="${2:?missing value for --algorithm}"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

if [[ "$algorithm" != "1" && "$algorithm" != "2" && "$algorithm" != "3" ]]; then
  echo "Invalid --algorithm value: $algorithm (expected 1, 2, or 3)" >&2
  exit 1
fi

for var in EVH_PGHOST EVH_PGPORT EVH_PGDATABASE EVH_PGUSER EVH_PGPASSWORD; do
  if [[ -z "${!var:-}" ]]; then
    echo "Missing required environment variable: $var" >&2
    exit 1
  fi
done

psql_base=(
  psql
  --no-psqlrc
  --set=ON_ERROR_STOP=1
  --host "$EVH_PGHOST"
  --port "$EVH_PGPORT"
  --dbname "$EVH_PGDATABASE"
  --username "$EVH_PGUSER"
  --tuples-only
  --no-align
  --quiet
)

batch_sql() {
  case "$algorithm" in
    1)
      cat <<SQL
with batch as (
    select
      p.ctid,
      r.client_id,
      r.patient_id,
      coalesce(nullif(p.metadata->>'original_filename', ''), nullif(p.metadata->>'originalfilename', ''), nullif(regexp_replace(p.source_name, '^.*:[0-9]+:', ''), p.source_name)) as originalfilename,
      coalesce(p.metadata->>'source_reference_id', p.metadata->>'pdf_id') as pdf_id
    from public.pms_page_chunk p
    join public.rag_document_identity r
      on r.document_pdf_id = coalesce(p.metadata->>'source_reference_id', p.metadata->>'pdf_id')
    where p.document_pdf_id is null
       or p.client_id is null
       or p.patient_id is null
       or p.original_filename is null
    order by p.ctid
    limit ${batch_size}
  )
  update public.pms_page_chunk p
  set
    document_pdf_id = batch.pdf_id,
    client_id = batch.client_id,
    patient_id = batch.patient_id,
    original_filename = batch.originalfilename
  from batch
  where p.ctid = batch.ctid
returning 1;
SQL
      ;;
    2)
      cat <<SQL
with batch as (
    select
      p.ctid,
      r.client_id,
      r.patient_id,
      coalesce(nullif(p.metadata->>'original_filename', ''), nullif(p.metadata->>'originalfilename', ''), nullif(regexp_replace(p.source_name, '^.*:[0-9]+:', ''), p.source_name)) as originalfilename,
      coalesce(p.metadata->>'source_reference_id', p.metadata->>'pdf_id') as pdf_id
    from public.pms_page_chunk p
    join public.rag_document_identity r
      on r.document_pdf_id = coalesce(p.metadata->>'source_reference_id', p.metadata->>'pdf_id')
    where p.document_pdf_id is null
       or p.client_id is null
       or p.patient_id is null
       or p.original_filename is null
    limit ${batch_size}
  )
  update public.pms_page_chunk p
  set
    document_pdf_id = batch.pdf_id,
    client_id = batch.client_id,
    patient_id = batch.patient_id,
    original_filename = batch.originalfilename
  from batch
  where p.ctid = batch.ctid
returning 1;
SQL
      ;;
    3)
      if [[ -z "${last_id:-}" ]]; then
        echo "Internal error: last_id is required for algorithm 3" >&2
        exit 1
      fi
      cat <<SQL
with batch as (
    select
      p.id,
      p.ctid,
      r.client_id,
      r.patient_id,
      coalesce(nullif(p.metadata->>'original_filename', ''), nullif(p.metadata->>'originalfilename', ''), nullif(regexp_replace(p.source_name, '^.*:[0-9]+:', ''), p.source_name)) as originalfilename,
      coalesce(p.metadata->>'source_reference_id', p.metadata->>'pdf_id') as pdf_id
    from public.pms_page_chunk p
    join public.rag_document_identity r
      on r.document_pdf_id = coalesce(p.metadata->>'source_reference_id', p.metadata->>'pdf_id')
    where p.id > ${last_id}
      and (
        p.document_pdf_id is null
        or p.client_id is null
        or p.patient_id is null
        or p.original_filename is null
      )
    order by p.id
    limit ${batch_size}
  )
  update public.pms_page_chunk p
  set
    document_pdf_id = batch.pdf_id,
    client_id = batch.client_id,
    patient_id = batch.patient_id,
    original_filename = batch.originalfilename
  from batch
  where p.ctid = batch.ctid
returning p.id;
SQL
      ;;
  esac
}

printf 'Starting pms_page_chunk repair loop\n'
printf '  estimate remaining: %s\n' "$estimate"
printf '  batch size: %s\n' "$batch_size"
printf '  sleep between batches: %ss\n' "$sleep_seconds"
printf '  algorithm: %s\n' "$algorithm"
last_id=0
printf '  last_id: %s\n' "$last_id"

batch_num=0
total_updated=0

while true; do
  batch_num=$((batch_num + 1))
  start_ns=$(date +%s%N)
  batch_output="$("${psql_base[@]}" -c "$(batch_sql)")"
  updated="$(printf '%s\n' "$batch_output" | sed '/^$/d' | wc -l | tr -d ' ')"
  end_ns=$(date +%s%N)
  elapsed_ms=$(( (end_ns - start_ns) / 1000000 ))

  if [[ "$algorithm" == "3" && "$updated" -gt 0 ]]; then
    last_id="$(printf '%s\n' "$batch_output" | awk 'BEGIN{max=0} /^[0-9]+$/ {if ($1 > max) max=$1} END{print max}')"
  fi

  total_updated=$((total_updated + updated))
  remaining=$(( estimate - total_updated ))
  if (( remaining < 0 )); then
    remaining=0
  fi

  if [[ "$algorithm" == "3" ]]; then
    printf 'batch=%d updated=%d elapsed_ms=%d total_updated=%d est_remaining=%d last_id=%s\n' \
      "$batch_num" "$updated" "$elapsed_ms" "$total_updated" "$remaining" "$last_id"
  else
    printf 'batch=%d updated=%d elapsed_ms=%d total_updated=%d est_remaining=%d\n' \
      "$batch_num" "$updated" "$elapsed_ms" "$total_updated" "$remaining"
  fi

  if (( updated == 0 )); then
    printf 'Done: no rows updated in the last batch.\n'
    break
  fi

  if (( sleep_seconds > 0 )); then
    sleep "$sleep_seconds"
  fi
done
