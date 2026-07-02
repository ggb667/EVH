# EVH Task Board

Update this file in place. Newest active items should stay near the top.

## Status Legend

- `queued`: defined but not started
- `active`: currently owned and in progress
- `blocked`: cannot proceed without input or dependency
- `review`: implementation done, waiting for verification or decision
- `done`: closed with artifact or handoff linked

## Active

### RAG-MVP-001

- Status: `active`
- Owner: `TWILIGHT_SPARKLE`
- Area: `RAG coordination`
- Goal: first EVH RAG milestone for PMS PDF ingestion, page storage, term dictionaries, vet terms, and docs
- Deliverable: one selected client/pet timeline of reconstructed document summaries with source PDF page links
- Dependencies: sample PMS PDFs, Handshake Aurora MySQL/MariaDB-compatible shared data load, vet term taxonomy
- Blockers: none
- Started: `2026-06-30`
- Last updated: `2026-07-01`
- Assignments: RD PDFs; AJ DB; Rarity Meds & Treatments; FS Vet Terms; Spike Docs; Twilight coordination
- Coordination note: AJ reports the shared dictionary seed is already loaded and verified in Handshake's Aurora MySQL/MariaDB-compatible database; do not route a duplicate dictionary seed/load retry.
- Runtime note: coordination files take effect for worker preflight on next launch; visible tab titles require relaunching the pony terminal/session layout.

### TWILIGHT-SPARKLE-001

- Status: `active`
- Owner: `TWILIGHT_SPARKLE`
- Area: `coordination`
- Goal: establish a durable EVH worker-coordination workflow in-repo
- Deliverable: `scripts/coordination/*` operating docs and templates
- Dependencies: none
- Blockers: none
- Started: `2026-05-03`
- Last updated: `2026-05-03`
- Notes: bootstrap task for coordinator support; logged cross-project
  coordination misrouting note for Celestia at
  `scripts/coordination/CELESTIA_NOTE.md`

## Queued

No queued tasks yet.

## Blocked

No blocked tasks yet.

## Review

No review tasks yet.

## Done

Move finished items here with a one-line outcome and artifact path.
