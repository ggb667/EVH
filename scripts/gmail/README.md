# Gmail helper

`evhstaff_gmail_inventory.py` can authenticate to Gmail, count messages, export them to a ZIP of raw `.eml` files, and optionally permanently delete the same messages after export.
`review_sender_routing_map.py` reviews a saved sender-routing JSON artifact and asks you to categorize only the unresolved entries.

## Files

- Script: `scripts/gmail/evhstaff_gmail_inventory.py`
- Routing reviewer: `scripts/gmail/review_sender_routing_map.py`
- Wrapper: `scripts/gmail/run_evhstaff_gmail_inventory.sh`
- OAuth client secrets JSON: `/home/ggb66/dev/evhstaff_gmail_google_client_credentials.json`
- Token cache: `/home/ggb66/dev/evhstaff_gmail_token.json`

## Common usage

The helper prints an exact count automatically for read-only report modes and before export/delete runs.

The reviewer defaults to `/tmp/evh_gmail_sender_routing_map.clean.json`, which is the saved artifact to classify interactively.

Export matching messages to a timestamped ZIP:

```bash
python3 /home/ggb66/dev/EVH/scripts/gmail/evhstaff_gmail_inventory.py \
  --client-secrets /home/ggb66/dev/evhstaff_gmail_google_client_credentials.json \
  --token-file /home/ggb66/dev/evhstaff_gmail_token.json \
  --query 'older_than:3y' \
  --export-zip
```

Export and permanently delete after export:

```bash
python3 /home/ggb66/dev/EVH/scripts/gmail/evhstaff_gmail_inventory.py \
  --client-secrets /home/ggb66/dev/evhstaff_gmail_google_client_credentials.json \
  --token-file /home/ggb66/dev/evhstaff_gmail_token.json \
  --query 'older_than:3y' \
  --export-zip \
  --delete-after-export
```

## Output files

- ZIP exports default to `/home/ggb66/older-than-3y-<UTC timestamp>.zip` for the sample query above.
- Tokens are cached in the token file path you pass.
