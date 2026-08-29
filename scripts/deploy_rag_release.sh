#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

cd "$ROOT_DIR"

echo "[release] deploying lambda and static site together from $(git rev-parse --short HEAD)"

"$ROOT_DIR/scripts/deploy_rag_lambda.sh"
"$ROOT_DIR/scripts/deploy_static_site_s3.sh"

echo "[release] both deploys completed"
