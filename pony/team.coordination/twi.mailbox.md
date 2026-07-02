# TWI MAILBOX

## Startup Contract
- This file contains only currently actionable coordinator messages.
- Full older mailbox history is preserved in `scripts/coordination/archive/twi.mailbox.pre-2026-07-01.md`.
- Do not read the archive during normal startup unless a current status, todo, decision, or worker question explicitly references it.

## Pending Items
- None requiring Twilight action.

## Current Coordination Facts
- User has told Celestia about the shared launcher write-scope issue where worker sessions can edit their worktree but not the EVH root `pony/team.coordination/*` and `pony/work/*` files. Treat the fix as Celestia-owned shared runtime work unless the user explicitly assigns Twilight to patch it locally.
- AJ worker-side update from 2026-06-30 is authoritative for the RAG shared load target: call it Handshake's Aurora MySQL, MariaDB-compatible database, not Postgres/pgvector.
- AJ reports the shared dictionary seed is already loaded and row-count verified in Handshake's Aurora MySQL/MariaDB-compatible database; do not route another worker to retry the same dictionary seed/load path unless the user explicitly asks.
- Weave support case `901174` is closed; Weave will not provide an API.
- Treat future Weave contact work as manual CSV import/export reconciliation only.
- Vetcove patient export tooling exists at `scripts/export_vetcove_patients.py`; current generated CSV had 19,563 living patient rows and zero city/state/zip gaps after conservative backfill.
- Appointment API list/fetch/cancel are known; writable `PATCH` is still only documented for `isConfirmed`; rescheduling is not proven.
- Rarity Stockroom replay work uses `view.pushHookEvent` on the `product-catalog` LiveView root and `live_fetch.update_global_product`.
- Worker-local state belongs in `pony/work/*.md`; mailbox/status files should summarize deltas and route requests.
- When a worker receives page-by-page data, save it into a real file immediately rather than a stub, summary placeholder, or partial reconstruction.

## Current RAG Snapshot
- `RAG-MVP-001` is active in worker statuses.
- AJ owns Handshake Aurora MySQL/MariaDB-compatible shared data/load verification and Instinct identity export normalization.
- RD owns PMS/Instinct PDF access notes.
- Rarity's shared dictionary seed has already been delivered to AJ and loaded; do not reassign the same seed build as a fresh next step.
- FS owns vet terms and document/source clues.
- Spike owns RAG architecture docs and worker contracts.
- Pinkie is `HOLD` in committed status; a newer Pinkie UI/RAG handoff was preserved in `stash@{0}` during preflight and is not applied to the branch.
