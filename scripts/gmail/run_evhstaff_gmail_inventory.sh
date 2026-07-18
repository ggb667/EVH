#!/usr/bin/env bash
set -euo pipefail

# Standalone launcher for the EVH Staff Gmail inventory helper.
# Run this from a real WSL/zsh (or other Unix-like) terminal, not through
# a Windows cmd.exe bridge.

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd -- "$script_dir/../.." && pwd)"

client_secrets_default="$HOME/dev/evhstaff_gmail_google_client_credentials.json"
token_file_default="$HOME/dev/evhstaff_gmail_token.json"

client_secrets="${1:-$client_secrets_default}"
token_file="${2:-$token_file_default}"
query="${3:-in:inbox newer_than:30d}"

if [[ ! -f "$client_secrets" ]]; then
  printf 'Client secrets file not found: %s\n' "$client_secrets" >&2
  exit 1
fi

mkdir -p "$(dirname -- "$token_file")"

exec python3 "$repo_root/scripts/gmail/evhstaff_gmail_inventory.py" \
  --client-secrets "$client_secrets" \
  --token-file "$token_file" \
  --query "$query"
