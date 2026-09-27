#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ZIP_PATH="${ZIP_PATH:-$ROOT_DIR/deploy/evh_instinct_rag_import_delta.zip}"
FUNCTION_NAME="${FUNCTION_NAME:-evh_instinct_rag_import_delta}"
DEPLOY_S3_BUCKET="${DEPLOY_S3_BUCKET:-evh-instinct-pdf-rag-shell}"
DIRECT_UPLOAD_MAX_BYTES="${DIRECT_UPLOAD_MAX_BYTES:-52428800}"
OCR_RUNTIME_S3_URI="${OCR_RUNTIME_S3_URI:-s3://evh-instinct-pdf-rag-shell/lambda-runtime/ocr/evh-ocr-runtime-al2023-x86_64-20260927.zip}"
OCR_RUNTIME_SHA256="${OCR_RUNTIME_SHA256:-20649ba107215c34d5b26a67ee48ce950cb394a33f32010c922f4f41b9659fd5}"
OCR_RUNTIME_ARCHIVE="${OCR_RUNTIME_ARCHIVE:-${TMPDIR:-/tmp}/evh-ocr-runtime-${OCR_RUNTIME_SHA256}.zip}"

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

echo "[package] acquire pinned Amazon Linux 2023 OCR runtime"
if [[ ! -f "$OCR_RUNTIME_ARCHIVE" ]] || [[ "$(sha256sum "$OCR_RUNTIME_ARCHIVE" | awk '{print $1}')" != "$OCR_RUNTIME_SHA256" ]]; then
  rm -f "$OCR_RUNTIME_ARCHIVE"
  aws s3 cp "$OCR_RUNTIME_S3_URI" "$OCR_RUNTIME_ARCHIVE" --only-show-errors
fi
printf '%s  %s\n' "$OCR_RUNTIME_SHA256" "$OCR_RUNTIME_ARCHIVE" | sha256sum --check --status || {
  echo "OCR runtime SHA-256 validation failed: $OCR_RUNTIME_ARCHIVE" >&2
  exit 1
}

export OCR_RUNTIME_ARCHIVE OCR_RUNTIME_SHA256
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
    ("scripts/ocr_worker.py", package_root / "scripts/ocr_worker.py"),
    ("scripts/http_session.py", package_root / "scripts/http_session.py"),
    ("scripts/rd_validation_harness.py", package_root / "scripts/rd_validation_harness.py"),
    ("rd-first.pdf", package_root / "rd-first.pdf"),
]:
    dest = staging / arc
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)

# OCR is a production dependency. Extract a content-addressed runtime built
# inside the official Lambda Python 3.13 (Amazon Linux 2023) root filesystem;
# host-distribution binaries are never admitted into the deployment package.
ocr_archive = Path(os.environ["OCR_RUNTIME_ARCHIVE"])
with zipfile.ZipFile(ocr_archive) as runtime_zip:
    for member in runtime_zip.infolist():
        member_path = Path(member.filename)
        if member_path.is_absolute() or ".." in member_path.parts:
            raise SystemExit(f"unsafe OCR runtime archive member: {member.filename}")
    runtime_zip.extractall(staging)
for tool in ("tesseract", "pdftoppm", "pdftocairo", "gs", "pdftotext"):
    tool_path = staging / "bin" / tool
    if not tool_path.is_file():
        raise SystemExit(f"package validation failed: OCR runtime missing bin/{tool}")
    tool_path.chmod(0o755)
for forbidden in ("libc.so.6", "ld-linux-x86-64.so.2", "libpthread.so.0", "libm.so.6", "libdl.so.2", "librt.so.1"):
    if (staging / "lib" / forbidden).exists():
        raise SystemExit(f"package validation failed: OCR runtime bundles glibc core {forbidden}")
# The managed AL2023 runtime provides its 2.34 baseline plus the AWS 2.35
# backport symbol set. Reject newer/RELR requirements before deployment.
max_glibc = (2, 35)
for elf_path in [*(staging / "bin").iterdir(), *(staging / "lib").iterdir()]:
    if not elf_path.is_file():
        continue
    info = subprocess.run(
        ["readelf", "--version-info", str(elf_path)],
        text=True,
        capture_output=True,
        check=False,
    ).stdout
    if "GLIBC_ABI_DT_RELR" in info:
        raise SystemExit(
            f"package validation failed: {elf_path.name} requires unsupported GLIBC_ABI_DT_RELR"
        )
    required_versions = [
        tuple(map(int, match.split(".")))
        for match in __import__("re").findall(r"GLIBC_(\d+\.\d+)", info)
    ]
    if required_versions and max(required_versions) > max_glibc:
        raise SystemExit(
            f"package validation failed: {elf_path.name} requires GLIBC_{'.'.join(map(str, max(required_versions)))}"
        )

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
    "scripts/ocr_worker.py",
    "rd-first.pdf",
    "bin/tesseract",
    "bin/pdftoppm",
    "bin/pdftocairo",
    "bin/gs",
    "bin/pdftotext",
    "share/tessdata/eng.traineddata",
    "OCR_RUNTIME_MANIFEST.txt",
}
with zipfile.ZipFile(zip_path) as z:
    names = set(z.namelist())
    missing = sorted(required - names)
if missing:
    raise SystemExit(f"package validation failed; missing required modules: {', '.join(missing)}")
uncompressed_bytes = sum(item.file_size for item in z.infolist())
max_uncompressed_bytes = 262_144_000
if uncompressed_bytes > max_uncompressed_bytes:
    raise SystemExit(
        f"package validation failed: {uncompressed_bytes} uncompressed bytes exceeds Lambda limit {max_uncompressed_bytes}"
    )
print(
    f"package validation passed: {len(required)} required modules present; "
    f"{uncompressed_bytes} uncompressed bytes"
)

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

APP_VERSION="$(git rev-parse --short HEAD)"
APP_REVISION="$(git rev-parse HEAD)"

echo "[deploy] update code before stamping provenance"
ZIP_BYTES="$(stat -c '%s' "$ZIP_PATH")"
if (( ZIP_BYTES > DIRECT_UPLOAD_MAX_BYTES )); then
  DEPLOY_S3_KEY="${DEPLOY_S3_KEY:-lambda-deploy/$FUNCTION_NAME/$APP_REVISION.zip}"
  echo "[deploy] package is ${ZIP_BYTES} bytes; uploading through s3://$DEPLOY_S3_BUCKET/$DEPLOY_S3_KEY"
  aws s3 cp "$ZIP_PATH" "s3://$DEPLOY_S3_BUCKET/$DEPLOY_S3_KEY"
  aws lambda update-function-code \
    --function-name "$FUNCTION_NAME" \
    --s3-bucket "$DEPLOY_S3_BUCKET" \
    --s3-key "$DEPLOY_S3_KEY" \
    --query '{FunctionName:FunctionName,Version:Version,LastModified:LastModified}' \
    --output json
else
  echo "[deploy] package is ${ZIP_BYTES} bytes; using direct upload"
  aws lambda update-function-code \
    --function-name "$FUNCTION_NAME" \
    --zip-file "fileb://$ZIP_PATH" \
    --query '{FunctionName:FunctionName,Version:Version,LastModified:LastModified}' \
    --output json
fi

aws lambda wait function-updated \
  --function-name "$FUNCTION_NAME"

echo "[deploy] code update successful; stamp lambda version env"
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

echo "[deploy] publish code and stamped environment"
aws lambda publish-version \
  --function-name "$FUNCTION_NAME" \
  --query '{FunctionName:FunctionName,Version:Version,LastModified:LastModified}' \
  --output json

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
