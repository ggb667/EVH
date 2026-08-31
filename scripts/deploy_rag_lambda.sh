#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ZIP_PATH="${ZIP_PATH:-$ROOT_DIR/deploy/evh_instinct_rag_search.zip}"
FUNCTION_NAME="${FUNCTION_NAME:-evh_instinct_rag_search}"

cd "$ROOT_DIR"

echo "[preflight] py_compile"
python -m py_compile \
  scripts/rag_ui/catalog.py \
  scripts/rag_ui/lambda_app.py

echo "[preflight] import smoke"
python - <<'PY'
import sys
import types

sys.modules.setdefault("boto3", types.ModuleType("boto3"))
import scripts.rag_ui.catalog
import scripts.rag_ui.lambda_app
print("import smoke passed")
PY

echo "[preflight] rag ui tests"
python -m pytest tests/test_rag_ui.py -q

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
zip_path = root / "deploy/evh_instinct_rag_search.zip"
build_dir = Path(tempfile.mkdtemp(prefix="evh-rag-lambda-build-"))
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
    "--implementation",
    "cp",
    "--python-version",
    "314",
    "--abi",
    "cp314",
    "--target",
    str(staging),
    "psycopg==3.2.13",
    "psycopg-binary==3.2.13",
    "pg8000==1.31.2",
    "boto3==1.35.99",
    "botocore==1.35.99",
])

for arc, src in [
    ("scripts/__init__.py", package_root / "scripts/__init__.py"),
    ("scripts/rag_ui/lambda_app.py", package_root / "scripts/rag_ui/lambda_app.py"),
    ("scripts/rag_ui/catalog.py", package_root / "scripts/rag_ui/catalog.py"),
    ("scripts/rag_ui/__init__.py", package_root / "scripts/rag_ui/__init__.py"),
    ("scripts/rag_ui/README.md", package_root / "scripts/rag_ui/README.md"),
    ("website/EVHInstinctPDFRAG/index.html", package_root / "website/EVHInstinctPDFRAG/index.html"),
    ("scripts/rag_ui/static/index.html", package_root / "website/EVHInstinctPDFRAG/index.html"),
]:
    dest = staging / arc
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)

with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as z:
    for path in sorted(staging.rglob("*")):
        if path.is_file():
            z.write(path, arcname=str(path.relative_to(staging)))
print(zip_path)
PY

echo "[deploy] update lambda code"
aws lambda update-function-code \
  --function-name "$FUNCTION_NAME" \
  --zip-file "fileb://$ZIP_PATH" \
  --publish \
  --query '{FunctionName:FunctionName,Version:Version,LastModified:LastModified}' \
  --output json

aws lambda wait function-updated \
  --function-name "$FUNCTION_NAME"

echo "[deploy] stamp lambda version env"
APP_VERSION="$(git rev-parse --short HEAD)"
CURRENT_ENV_JSON="$(aws lambda get-function-configuration --function-name "$FUNCTION_NAME" --query 'Environment.Variables' --output json)"
python3 - "$APP_VERSION" "$CURRENT_ENV_JSON" <<'PY'
import json
import subprocess
import sys

version = sys.argv[1]
current = json.loads(sys.argv[2] or "{}")
current["RAG_UI_VERSION"] = version
payload = json.dumps({"Variables": current})
subprocess.check_call([
    "aws", "lambda", "update-function-configuration",
    "--function-name", "evh_instinct_rag_search",
    "--environment", payload,
    "--output", "json",
])
PY

echo "[smoke] live lambda route check"
aws lambda invoke \
  --function-name "$FUNCTION_NAME" \
  --cli-binary-format raw-in-base64-out \
  --payload '{"rawPath":"/api/options","requestContext":{"http":{"method":"GET"}},"queryStringParameters":{"kind":"client","q":"Deborah"}}' \
  /tmp/evh_options_smoke.json \
  >/tmp/evh_options_smoke.meta.json

python - <<'PY'
import json
from pathlib import Path

payload = json.loads(Path("/tmp/evh_options_smoke.json").read_text())
if payload.get("statusCode") != 200:
    raise SystemExit(f"live lambda options smoke failed: {payload}")
body = json.loads(payload["body"])
if body.get("kind") != "client":
    raise SystemExit(f"unexpected live lambda options smoke body: {body}")
print("live lambda options smoke passed")
PY
