#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SITE_DIR="${SITE_DIR:-$ROOT_DIR/website}"
OUTPUT_ZIP="${OUTPUT_ZIP:-$ROOT_DIR/evh_site.zip}"
TARGET_PAGE="${TARGET_PAGE:-EVHInstinctPDFRAG}"
BUILD_STAMP="${BUILD_STAMP:-$(TZ=America/New_York date '+%Y-%m-%d %H:%M EDT') Commit $(git -C "$ROOT_DIR" rev-parse --short HEAD)}"

if [ ! -d "$SITE_DIR" ]; then
  echo "ERROR: site directory not found: $SITE_DIR" >&2
  exit 1
fi

if [ ! -f "$SITE_DIR/$TARGET_PAGE/index.html" ]; then
  echo "ERROR: target page not found: $SITE_DIR/$TARGET_PAGE/index.html" >&2
  exit 1
fi

TMP_DIR="$(mktemp -d /tmp/evh-site-package-XXXXXX)"
trap 'rm -rf "$TMP_DIR"' EXIT

rm -f "$OUTPUT_ZIP"
mkdir -p "$TMP_DIR/$TARGET_PAGE"
sed "s/__EVH_BUILD_STAMP__/$BUILD_STAMP/g" "$SITE_DIR/$TARGET_PAGE/index.html" > "$TMP_DIR/$TARGET_PAGE/index.html"

if grep -q '__EVH_BUILD_STAMP__' "$TMP_DIR/$TARGET_PAGE/index.html"; then
  echo "ERROR: build stamp placeholder still present after substitution" >&2
  exit 1
fi

(
  cd "$TMP_DIR"
  zip -q -r "$OUTPUT_ZIP" ./"$TARGET_PAGE"
)

printf '%s\n' "$OUTPUT_ZIP"
