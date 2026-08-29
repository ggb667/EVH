#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SITE_DIR="${SITE_DIR:-$ROOT_DIR/website}"
PACKAGE_SCRIPT="${PACKAGE_SCRIPT:-$ROOT_DIR/scripts/package_static_site.sh}"
OUTPUT_ZIP="${OUTPUT_ZIP:-$ROOT_DIR/evh_site.zip}"
AWS_REGION="${AWS_REGION:-us-east-1}"
BUCKET_NAME="${STATIC_SITE_BUCKET:-evh-instinct-pdf-rag-shell}"
TARGET_PAGE="${TARGET_PAGE:-EVHInstinctPDFRAG}"
EXPECTED_SHORT_HASH="${EXPECTED_SHORT_HASH:-$(git -C "$ROOT_DIR" rev-parse --short HEAD)}"

if [ ! -d "$SITE_DIR" ]; then
  echo "ERROR: site directory not found: $SITE_DIR" >&2
  exit 1
fi

if [ ! -f "$SITE_DIR/$TARGET_PAGE/index.html" ]; then
  echo "ERROR: target page not found: $SITE_DIR/$TARGET_PAGE/index.html" >&2
  exit 1
fi

if [ ! -x "$PACKAGE_SCRIPT" ]; then
  echo "ERROR: package script not found or not executable: $PACKAGE_SCRIPT" >&2
  exit 1
fi

"$PACKAGE_SCRIPT"

TMP_DIR="$(mktemp -d /tmp/evh-site-deploy-XXXXXX)"
trap 'rm -rf "$TMP_DIR"' EXIT
unzip -oq "$OUTPUT_ZIP" -d "$TMP_DIR"

if ! aws s3api head-bucket --bucket "$BUCKET_NAME" >/dev/null 2>&1; then
  if [ "$AWS_REGION" = "us-east-1" ]; then
    aws s3api create-bucket \
      --bucket "$BUCKET_NAME" \
      --region "$AWS_REGION" >/dev/null
  else
    aws s3api create-bucket \
      --bucket "$BUCKET_NAME" \
      --region "$AWS_REGION" \
      --create-bucket-configuration "LocationConstraint=$AWS_REGION" >/dev/null
  fi
fi

aws s3api put-public-access-block \
  --bucket "$BUCKET_NAME" \
  --region "$AWS_REGION" \
  --public-access-block-configuration \
  'BlockPublicAcls=false,IgnorePublicAcls=false,BlockPublicPolicy=false,RestrictPublicBuckets=false' >/dev/null

aws s3api put-bucket-policy \
  --bucket "$BUCKET_NAME" \
  --region "$AWS_REGION" \
  --policy "{
    \"Version\":\"2012-10-17\",
    \"Statement\":[
      {
        \"Sid\":\"PublicRead\",
        \"Effect\":\"Allow\",
        \"Principal\":\"*\",
        \"Action\":\"s3:GetObject\",
        \"Resource\":\"arn:aws:s3:::$BUCKET_NAME/*\"
      }
    ]
  }" >/dev/null

aws s3 sync "$TMP_DIR/$TARGET_PAGE/" "s3://$BUCKET_NAME/$TARGET_PAGE/" --region "$AWS_REGION" --cache-control no-store >/dev/null

aws s3 website "s3://$BUCKET_NAME/" \
  --region "$AWS_REGION" \
  --index-document index.html \
  --error-document index.html >/dev/null

URL="http://$BUCKET_NAME.s3-website-$AWS_REGION.amazonaws.com/$TARGET_PAGE/"

sleep 5
curl -fsS "$URL" >/dev/null
for path in \
  ""
do
  curl -fsS "$URL$path" >/dev/null
done

VALIDATION_HTML="$(mktemp /tmp/evh-site-validate-XXXXXX.html)"
trap 'rm -f "$VALIDATION_HTML"; rm -rf "$TMP_DIR"' EXIT
curl -fsS "$URL" -o "$VALIDATION_HTML"
if ! grep -q 'Build: ' "$VALIDATION_HTML"; then
  echo "ERROR: deployed page did not contain a build stamp" >&2
  exit 1
fi
if ! grep -q "$EXPECTED_SHORT_HASH" "$VALIDATION_HTML"; then
  echo "ERROR: deployed page build stamp did not match expected commit hash $EXPECTED_SHORT_HASH" >&2
  exit 1
fi

printf '%s\n%s\n%s\n' "$BUCKET_NAME" "$URL" "validation passed"
