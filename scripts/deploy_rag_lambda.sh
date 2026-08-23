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
python - <<'PY'
import zipfile
from pathlib import Path

root = Path("/home/ggb66/dev/EVH")
zip_path = root / "deploy/evh_instinct_rag_search.zip"
with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as z:
    for arc, src in [
        ("scripts/__init__.py", root / "pony/worktrees/pinkie/scripts/__init__.py"),
        ("scripts/rag_ui/lambda_app.py", root / "pony/worktrees/pinkie/scripts/rag_ui/lambda_app.py"),
        ("scripts/rag_ui/catalog.py", root / "pony/worktrees/pinkie/scripts/rag_ui/catalog.py"),
        ("scripts/rag_ui/__init__.py", root / "pony/worktrees/pinkie/scripts/rag_ui/__init__.py"),
        ("scripts/rag_ui/README.md", root / "pony/worktrees/pinkie/scripts/rag_ui/README.md"),
        ("scripts/rag_ui/static/index.html", root / "pony/worktrees/pinkie/website/EVHInstinctPDFRAG/index.html"),
    ]:
        z.write(src, arcname=arc)
print(zip_path)
PY

echo "[deploy] update lambda code"
aws lambda update-function-code \
  --function-name "$FUNCTION_NAME" \
  --zip-file "fileb://$ZIP_PATH" \
  --publish \
  --query '{FunctionName:FunctionName,Version:Version,LastModified:LastModified}' \
  --output json

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
