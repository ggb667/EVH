# Pinkie Workfile

Project: EVH
Branch: pony/pinkie/main

Status: PDF_SEARCH_VALIDATION_PAUSED_BACKEND_RDS_RECOVERY
Scope: UI for PDF search
Permissions granted: none recorded
Restart capsule:
- task: none recorded
- why: none recorded
- next: none recorded
- blocker: none recorded
Notes:
- Pinkie owns UI validation for PDF search; AJ owns backend GET /api/rag/documents/search
- validate source_page_url, one canonical source of truth, and text-layer-vs-OCR navigation semantics once live

- 2026-07-27 Pinkie endpoint validation pause refined: evh-vector-pg has storage-full / not-accepting-connections history after the pms_page_chunk export fallout; Pinkie will rerun UI validation only after backend health is confirmed, non-destructive SELECT/live endpoint checks pass, and AJ has a live endpoint. Pinkie performs no DB cleanup actions.
