#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
QUEUE_NAME="${QUEUE_NAME:-evh-instinct-import-queue}"
FUNCTION_NAME="${FUNCTION_NAME:-evh_instinct_rag_import_delta}"
ZIP_PATH="${ZIP_PATH:-$ROOT_DIR/deploy/evh_instinct_rag_import_delta_batch.zip}"
LAMBDA_TIMEOUT="${LAMBDA_TIMEOUT:-300}"
LAMBDA_MEMORY="${LAMBDA_MEMORY:-1024}"
SQS_BATCH_SIZE="${SQS_BATCH_SIZE:-1}"
CRON_RULE_NAME="${CRON_RULE_NAME:-evh-instinct-import-daily}"
CRON_SCHEDULE="${CRON_SCHEDULE:-rate(1 day)}"

cd "$ROOT_DIR"

QUEUE_URL="$(
  aws sqs get-queue-url --queue-name "$QUEUE_NAME" --query 'QueueUrl' --output text 2>/dev/null \
  || aws sqs create-queue --queue-name "$QUEUE_NAME" --query 'QueueUrl' --output text
)"
QUEUE_ARN="$(aws sqs get-queue-attributes --queue-url "$QUEUE_URL" --attribute-names QueueArn --query 'Attributes.QueueArn' --output text)"
echo "[queue] $QUEUE_URL"

echo "[preflight] py_compile"
python -m py_compile \
  scripts/rag_import_delta_lambda.py \
  scripts/instinct_batch_flow.py \
  scripts/instinct_cache_sync_pipeline.py \
  scripts/instinct_identity_sync.py

echo "[preflight] import smoke"
python - <<'PY'
import sys
import types
sys.modules.setdefault("boto3", types.ModuleType("boto3"))
import scripts.rag_import_delta_lambda
print("import smoke passed")
PY

echo "[package] build lambda zip"
ROOT_DIR="$ROOT_DIR" python3 - <<'PY'
import os, shutil, subprocess, sys, tempfile, zipfile
from pathlib import Path
root = Path(os.environ["ROOT_DIR"])
zip_path = root / "deploy/evh_instinct_rag_import_delta_batch.zip"
build_dir = Path(tempfile.mkdtemp(prefix="evh-import-delta-batch-"))
zip_path.parent.mkdir(parents=True, exist_ok=True)
subprocess.check_call([
    sys.executable, "-m", "pip", "install", "--upgrade", "--only-binary=:all:",
    "--platform", "manylinux2014_x86_64", "--implementation", "cp", "--python-version", "313",
    "--abi", "cp313", "--target", str(build_dir), "psycopg==3.2.13", "psycopg-binary==3.2.13",
    "requests==2.32.3", "boto3==1.35.99", "botocore==1.35.99",
    "langchain-core", "langchain-text-splitters", "pypdf",
])
for arc, src in [
    ("scripts/__init__.py", root / "scripts/__init__.py"),
    ("scripts/rag_import_delta_lambda.py", root / "scripts/rag_import_delta_lambda.py"),
    ("scripts/instinct_batch_flow.py", root / "scripts/instinct_batch_flow.py"),
    ("scripts/instinct_cache_sync_pipeline.py", root / "scripts/instinct_cache_sync_pipeline.py"),
    ("scripts/instinct_identity_sync.py", root / "scripts/instinct_identity_sync.py"),
    ("scripts/instinct_pdf_chunker.py", root / "scripts/instinct_pdf_chunker.py"),
]:
    dest = build_dir / arc
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)
with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as z:
    for path in sorted(build_dir.rglob("*")):
        if path.is_file():
            z.write(path, arcname=str(path.relative_to(build_dir)))
print(zip_path)
PY

echo "[deploy] update lambda code"
aws lambda update-function-code \
  --function-name "$FUNCTION_NAME" \
  --zip-file "fileb://$ZIP_PATH" \
  --publish \
  --query '{FunctionName:FunctionName,Version:Version,LastModified:LastModified}' \
  --output json
aws lambda wait function-updated --function-name "$FUNCTION_NAME"

echo "[deploy] configure daily EventBridge trigger"
RULE_ARN="$(aws events put-rule --name "$CRON_RULE_NAME" --schedule-expression "$CRON_SCHEDULE" --state ENABLED --description 'Daily EVH Instinct incremental import' --query RuleArn --output text)"
FUNCTION_ARN="$(aws lambda get-function --function-name "$FUNCTION_NAME" --query 'Configuration.FunctionArn' --output text)"
TARGET_INPUT='{"mode":"enqueue","all_new":true,"run_id":"daily-eventbridge"}'
TARGETS_JSON="$(python3 - "$FUNCTION_ARN" "$TARGET_INPUT" <<'PY'
import json, sys
print(json.dumps([{"Id": "evh-instinct-daily-target", "Arn": sys.argv[1], "Input": sys.argv[2]}]))
PY
)"
aws events put-targets --rule "$CRON_RULE_NAME" --targets "$TARGETS_JSON" --output json
aws lambda add-permission --function-name "$FUNCTION_NAME" --statement-id "${CRON_RULE_NAME}-invoke" --action lambda:InvokeFunction --principal events.amazonaws.com --source-arn "$RULE_ARN" 2>/dev/null || true

echo "[deploy] configure timeout/memory"
aws lambda update-function-configuration \
  --function-name "$FUNCTION_NAME" \
  --timeout "$LAMBDA_TIMEOUT" \
  --memory-size "$LAMBDA_MEMORY" \
  --query '{FunctionName:FunctionName,LastModified:LastModified,Timeout:Timeout,MemorySize:MemorySize,LastUpdateStatus:LastUpdateStatus}' \
  --output json
aws lambda wait function-updated --function-name "$FUNCTION_NAME"

echo "[deploy] configure env"
CURRENT_ENV_JSON="$(aws lambda get-function-configuration --function-name "$FUNCTION_NAME" --query 'Environment.Variables' --output json)"
python3 - "$CURRENT_ENV_JSON" "$QUEUE_URL" "$QUEUE_ARN" <<'PY'
import json, os, subprocess, sys
current = json.loads(sys.argv[1] or "{}")
current["EVH_IMPORT_QUEUE_URL"] = sys.argv[2]
current["EVH_IMPORT_QUEUE_ARN"] = sys.argv[3]
current["EVH_BATCH_FLOW_VERSION"] = "1"
current["STEP13_DOCUMENT_LIMIT"] = os.environ.get("STEP13_DOCUMENT_LIMIT", "1000").strip() or "1000"
payload = json.dumps({"Variables": current})
subprocess.check_call([
    "aws", "lambda", "update-function-configuration",
    "--function-name", "evh_instinct_rag_import_delta",
    "--environment", payload,
    "--query", "{FunctionName:FunctionName,LastModified:LastModified,LastUpdateStatus:LastUpdateStatus,RevisionId:RevisionId}",
    "--output", "json",
])
PY

echo "[deploy] wire SQS event source mapping"
EXISTING_MAPPING="$(aws lambda list-event-source-mappings --function-name "$FUNCTION_NAME" --event-source-arn "$QUEUE_ARN" --query 'EventSourceMappings[0].UUID' --output text 2>/dev/null || true)"
if [[ -z "$EXISTING_MAPPING" || "$EXISTING_MAPPING" == "None" ]]; then
  aws lambda create-event-source-mapping \
    --function-name "$FUNCTION_NAME" \
    --event-source-arn "$QUEUE_ARN" \
    --batch-size "$SQS_BATCH_SIZE" \
    --function-response-types ReportBatchItemFailures \
    --enabled \
    --output json
else
  aws lambda update-event-source-mapping \
    --uuid "$EXISTING_MAPPING" \
    --batch-size "$SQS_BATCH_SIZE" \
    --function-response-types ReportBatchItemFailures \
    --enabled \
    --output json
fi

echo "[smoke] enqueue mode"
aws lambda invoke \
  --function-name "$FUNCTION_NAME" \
  --cli-binary-format raw-in-base64-out \
  --payload '{"mode":"enqueue","patient_limit":1,"document_limit":1}' \
  /tmp/evh_import_delta_enqueue_smoke.json \
  >/tmp/evh_import_delta_enqueue_smoke.meta.json

python - <<'PY'
import json
from pathlib import Path
payload = json.loads(Path("/tmp/evh_import_delta_enqueue_smoke.json").read_text())
if payload.get("statusCode") != 200:
    raise SystemExit(f"enqueue smoke failed: {payload}")
print("enqueue smoke passed")
PY
