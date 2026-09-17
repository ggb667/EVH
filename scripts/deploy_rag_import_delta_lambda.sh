#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ZIP_PATH="${ZIP_PATH:-$ROOT_DIR/deploy/evh_instinct_rag_import_delta.zip}"
FUNCTION_NAME="${FUNCTION_NAME:-evh_instinct_rag_import_delta}"

cd "$ROOT_DIR"

echo "[preflight] py_compile"
python -m py_compile \
  scripts/rag_import_delta_lambda.py \
  scripts/instinct_cache_sync_pipeline.py \
  scripts/instinct_identity_sync.py \
  scripts/instinct_pdf_chunker.py \
  scripts/rd_validation_harness.py

echo "[preflight] import smoke"
python - <<'PY'
import sys
import types

sys.modules.setdefault("boto3", types.ModuleType("boto3"))
import scripts.rag_import_delta_lambda
import scripts.instinct_cache_sync_pipeline
print("import smoke passed")
PY

echo "[package] build lambda zip"
ROOT_DIR="$ROOT_DIR" python3 - <<'PY'
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

root = Path(os.environ["ROOT_DIR"])
zip_path = root / "deploy/evh_instinct_rag_import_delta.zip"
build_dir = Path(tempfile.mkdtemp(prefix="evh-rag-import-delta-build-"))
staging = build_dir
package_root = root
zip_path.parent.mkdir(parents=True, exist_ok=True)

subprocess.check_call([
    sys.executable,
    "-m",
    "pip",
    "install",
    "--upgrade",
    "--only-binary=:all:",
    "--platform",
    "manylinux2014_x86_64",
    "--platform",
    "manylinux_2_28_x86_64",
    "--implementation",
    "cp",
    "--python-version",
    "313",
    "--abi",
    "cp313",
    "--target",
    str(staging),
    "psycopg==3.2.13",
    "psycopg-binary==3.2.13",
    "requests==2.32.3",
    "langchain-core==0.3.63",
    "langchain-text-splitters==0.3.8",
    "pypdf==5.4.0",
    "PyMuPDF==1.26.0",
])

for arc, src in [
    ("scripts/__init__.py", package_root / "scripts/__init__.py"),
    ("scripts/rag_import_delta_lambda.py", package_root / "scripts/rag_import_delta_lambda.py"),
    ("scripts/instinct_cache_sync_pipeline.py", package_root / "scripts/instinct_cache_sync_pipeline.py"),
    ("scripts/instinct_identity_sync.py", package_root / "scripts/instinct_identity_sync.py"),
    ("scripts/instinct_pdf_chunker.py", package_root / "scripts/instinct_pdf_chunker.py"),
    ("scripts/http_session.py", package_root / "scripts/http_session.py"),
    ("scripts/rd_validation_harness.py", package_root / "scripts/rd_validation_harness.py"),
    ("rd-first.pdf", package_root / "rd-first.pdf"),
]:
    dest = staging / arc
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)

with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as z:
    for path in sorted(staging.rglob("*")):
        if path.is_file():
            z.write(path, arcname=str(path.relative_to(staging)))
required = {
    "scripts/__init__.py",
    "scripts/rag_import_delta_lambda.py",
    "scripts/instinct_cache_sync_pipeline.py",
    "scripts/instinct_identity_sync.py",
    "scripts/instinct_pdf_chunker.py",
    "scripts/http_session.py",
    "pymupdf/__init__.py",
    "scripts/rd_validation_harness.py",
    "rd-first.pdf",
}
with zipfile.ZipFile(zip_path) as z:
    names = set(z.namelist())
    missing = sorted(required - names)
if missing:
    raise SystemExit(f"package validation failed; missing required modules: {', '.join(missing)}")
print(f"package validation passed: {len(required)} required modules present")

with zipfile.ZipFile(zip_path) as z:
    with tempfile.TemporaryDirectory(prefix="evh-rag-import-delta-import-") as import_root:
        z.extractall(import_root)
        code = """
import pathlib
import sys
root_path = pathlib.Path(sys.argv[1]).resolve()
sys.path.insert(0, str(root_path))
import pymupdf
pymupdf_path = pathlib.Path(pymupdf.__file__).resolve()
if root_path not in pymupdf_path.parents:
    raise SystemExit('pymupdf imported outside extracted ZIP: %s' % pymupdf_path)
print('package validation passed: real PyMuPDF import')
if sys.version_info[:2] == (3, 13):
    import scripts.instinct_pdf_chunker as chunker
    if chunker.pymupdf is None:
        raise SystemExit('instinct_pdf_chunker did not bind real pymupdf')
    print('package validation passed: instinct_pdf_chunker bound real PyMuPDF')
else:
    print(
        'package validation deferred: instinct_pdf_chunker import requires Python 3.13 '
        'because the package contains cp313 binary wheels; deployed Lambda branch harness must verify binding'
    )
"""
        subprocess.check_call([sys.executable, "-I", "-c", code, import_root])
print(zip_path)
PY

if [[ "${PACKAGE_ONLY:-0}" == "1" ]]; then
  echo "[package] PACKAGE_ONLY=1; skipping deploy and smoke"
  exit 0
fi

if [[ "${DEPLOY_LAMBDA:-0}" != "1" ]]; then
  echo "[package] validation complete; set DEPLOY_LAMBDA=1 for an explicit AWS deploy"
  exit 0
fi

echo "[deploy] stamp lambda version env"
APP_VERSION="$(git rev-parse --short HEAD)"
CURRENT_ENV_JSON="$(aws lambda get-function-configuration --function-name "$FUNCTION_NAME" --query 'Environment.Variables' --output json)"
python3 - "$FUNCTION_NAME" "$APP_VERSION" "$CURRENT_ENV_JSON" <<'PY'
import json
import os
import subprocess
import sys

function_name = sys.argv[1]
version = sys.argv[2]
current = json.loads(sys.argv[3] or "{}")
current["RAG_IMPORT_DELTA_VERSION"] = version
current["STEP13_DOCUMENT_LIMIT"] = os.environ.get("STEP13_DOCUMENT_LIMIT", "1000").strip() or "1000"

required = ("EVH_PGDATABASE", "EVH_PGHOST", "EVH_PGPORT", "EVH_PGUSER", "EVH_PGPASSWORD")
for name in required:
    value = os.environ.get(name, "").strip() or str(current.get(name, "")).strip()
    if not value:
        raise SystemExit(f"Missing required deploy env var: {name}")
    current[name] = value

for name in ("INSTINCT_CLIENT_ID", "INSTINCT_CLIENT_SECRET"):
    value = os.environ.get(name, "").strip() or str(current.get(name, "")).strip()
    if not value:
        raise SystemExit(f"Missing required deploy env var: {name}")
    current[name] = value

optional = ("EVH_PGDATABASE_URL", "INSTINCT_API_BASE_URL")
for name in optional:
    value = os.environ.get(name, "").strip()
    if value:
        current[name] = value

for name in ("INSTINCT_CLIENT_SECRET_ARN", "OPENAI_API_KEY_SECRET_ARN"):
    value = os.environ.get(name, "").strip() or str(current.get(name, "")).strip()
    if value:
        current[name] = value

payload = json.dumps({"Variables": current})
subprocess.check_call([
    "aws", "lambda", "update-function-configuration",
    "--function-name", function_name,
    "--environment", payload,
    "--query", "{FunctionName:FunctionName,LastModified:LastModified,LastUpdateStatus:LastUpdateStatus,RevisionId:RevisionId}",
    "--output", "json",
])
PY

aws lambda wait function-updated \
  --function-name "$FUNCTION_NAME"

echo "[deploy] publish code with stamped environment"
aws lambda update-function-code \
  --function-name "$FUNCTION_NAME" \
  --zip-file "fileb://$ZIP_PATH" \
  --publish \
  --query '{FunctionName:FunctionName,Version:Version,LastModified:LastModified}' \
  --output json

aws lambda wait function-updated \
  --function-name "$FUNCTION_NAME"

if [[ "${RUN_NORMAL_SMOKE:-0}" != "1" ]]; then
  echo "[deploy] normal smoke disabled; set RUN_NORMAL_SMOKE=1 only when explicitly authorized"
  exit 0
fi

echo "[smoke] lambda invoke"
SMOKE_RUN_ID="deploy-smoke-$(date -u +%Y%m%dT%H%M%SZ)-$$"
aws lambda invoke \
  --function-name "$FUNCTION_NAME" \
  --cli-binary-format raw-in-base64-out \
  --payload "{\"run_id\":\"$SMOKE_RUN_ID\",\"start_patient\":0,\"patient_start\":0,\"patient_batch\":1,\"patient_limit\":1,\"document_limit\":1,\"max_seconds\":120}" \
  /tmp/evh_rag_import_delta_smoke.json \
  >/tmp/evh_rag_import_delta_smoke.meta.json

python - <<'PY'
import json
from pathlib import Path

payload = json.loads(Path("/tmp/evh_rag_import_delta_smoke.json").read_text())
if payload.get("statusCode") != 200:
    raise SystemExit(f"lambda smoke failed: {payload}")
body = json.loads(payload["body"])
if body.get("status") != "ok":
    raise SystemExit(f"unexpected lambda smoke body: {body}")
print("lambda smoke passed")
PY
