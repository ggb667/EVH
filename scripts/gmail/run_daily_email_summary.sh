#!/usr/bin/env bash
set -euo pipefail

# Wrapper for the daily Gmail communication summary.
# Runs the no-send path by default so it only writes the /tmp summary artifacts.

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd -- "$script_dir/../.." && pwd)"

client_secrets_default="$HOME/dev/evhstaff_gmail_google_client_credentials.json"
token_file_default="/tmp/evhstaff_gmail_token.json"
query_default='in:inbox is:unread newer_than:1d'

client_secrets="${1:-$client_secrets_default}"
token_file="${2:-$token_file_default}"
query="${3:-$query_default}"

if [[ ! -f "$client_secrets" ]]; then
  printf 'Client secrets file not found: %s\n' "$client_secrets" >&2
  exit 1
fi

mkdir -p "$(dirname -- "$token_file")"

exec python3 "$repo_root/scripts/gmail/daily_email_summary.py" \
  --client-secrets "$client_secrets" \
  --token-file "$token_file" \
  --query "$query" \
  --dry-run
