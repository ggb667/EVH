# Pinkie Workfile

Project: EVH
Branch: pony/pinkie/main

Status: AWS_RAG_LIVE_DB_NETWORK_BLOCKED -> Lambda timeout to RDS remains the active blocker
Scope: UI for PDF search
Permissions granted: none recorded
Restart capsule:
- task: wait for deployment/AWS network owner decision on Lambda-to-RDS access path, then rerun `/api/options` and live PDF-search UI validation
- why: the UI page is live, but backend options/search cannot complete until Lambda can reach RDS
- next: confirm NAT/private-subnet route or alternate approved DB access path, then validate source_page_url and canonical-hit behavior
- blocker: AWS network path from Lambda `evh_instinct_rag_search` to `evh-vector-pg.c6hqq6a8ukmj.us-east-1.rds.amazonaws.com:5432`
Notes:
- 2026-08-20 page health is good, but `/api/options` still 500s from Lambda timeouts; this is network/path, not UI code.
