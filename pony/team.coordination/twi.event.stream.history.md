# TWILIGHT EVENT STREAM HISTORY

## Startup Contract
- This file is a short rolling event stream for Twilight startup.
- Full pre-2026-07-01 history is preserved in `scripts/coordination/archive/twi.event.stream.history.pre-2026-07-01.md`.
- The malformed pre-cleanup rolling copy is preserved in `scripts/coordination/archive/twi.event.stream.history.cleanup-2026-07-09.md`.
- Canonical current state is `assignment.registry.tsv` plus `*.status.md`; this event stream is supporting context only.

## Current State
- pending_review_needed_content: none
- pending_worker_questions: none
- runtime_install_state: refreshed to the current source fingerprint; local runtime token normalized to `ready`.
- mailbox_state: live mailbox lanes compacted; stale transcript backlog archived out of the active mailbox surface.

## 2026-07-09 02:40:33 UTC
- changed_file: pony/runtime/install-project.state, pony/runtime/install-project.metadata, pony/runtime/source-runtime.fingerprint, pony/runtime/runtime.state
- action: EVH pony runtime refreshed from agenic source
- status: WAITING
- blockers: none
- next_step: relaunch ponies on demand against the refreshed direct-launch runtime surface
- questions_for_twi: none
- decision_needed: none

## 2026-07-09 02:42:38 UTC
- changed_file: twi.mailbox.md, aj.mailbox.md, rd.mailbox.md, spike.mailbox.md, scripts/coordination/archive/mailbox.cleanup-2026-07-09.md
- action: stale mailbox transcript backlog archived out of the live notification lane
- status: WAITING
- blockers: none
- next_step: keep durable worker state in workfiles and status files, not mailbox transcripts
- questions_for_twi: none
- decision_needed: none

## 2026-07-09 02:44:30 UTC
- changed_file: twi.status.md, twi.event.stream.history.md
- action: Twilight rolling coordination state compacted after runtime refresh and mailbox cleanup
- status: WAITING
- blockers: none
- next_step: wait for a concrete EVH coordination task or worker question
- questions_for_twi: none
- decision_needed: none

## 2026-07-09 03:19:30 UTC
- changed_file: assignment.registry.tsv, twi.status.md, pony/work/coordinator-twi.md
- action: Twilight branch routing records aligned to the live pony/twi/main coordinator branch
- status: WAITING
- blockers: none
- next_step: coordinate from the EVH root worktree on pony/twi/main without relaunch-time routing confusion
- questions_for_twi: none
- decision_needed: none

## 2026-07-09 04:02:01 UTC
- changed_file: pony/team.coordination/rd.status.md, pony/team.coordination/twi.status.md, pony/team.coordination/twi.event.stream.history.md
- action: recorded Applejack's answer to Rainbow Dash's PDF-status question
- finding: no evidence in current coordination/workfiles of a 200-PDF patient run; only concrete benchmark is 1 page / 1 chunk dry-run, plus live sample note that 12 PDFs were pulled for patient 11525
- status: WAITING
- blockers: RD still needs vector DB connection information for live enhanced chunk storage/search validation
- next_step: deliver the status answer to RD and wait for vector DB connection info or further user direction
- questions_for_twi: none
- decision_needed: none

## 2026-07-09 16:33:53 UTC
- changed_file: pony/team.coordination/rd.status.md, pony/work/rd.md, pony/team.coordination/twi.status.md, pony/team.coordination/twi.event.stream.history.md
- action: recorded Rainbow Dash PDF inventory and routed next local PDF analysis step
- finding: exactly one current PDF available, `/home/ggb66/dev/EVH/pony/worktrees/rd/rd-first.pdf`, 762,118 bytes, 8 pages; no additional PDFs to size-scan in the current project tree
- status: ASSIGNED
- blockers: vector DB connection information still blocks live enhanced chunk storage/search validation, but local page-first analysis can continue
- next_step: RD should analyze `rd-first.pdf` locally for pages/text, text volume, page/chunk counts, term hits, clinical summary, and timings; defer live vector writes/search until connection info arrives
- questions_for_twi: none
- decision_needed: none

## 2026-07-09 16:41:46 UTC
- changed_file: pony/team.coordination/rd.status.md, pony/work/rd.md, pony/team.coordination/twi.status.md, pony/team.coordination/twi.event.stream.history.md
- action: recorded Rainbow Dash client inventory checkpoint and routed next inventory steps
- finding: `/tmp/instinct_client_inventory.json` contains 100 clients/accounts; no PDF bodies were downloaded during the client step
- status: ASSIGNED
- blockers: vector DB connection information still blocks live enhanced chunk storage/search validation, but patient inventory and PDF size pass can continue
- next_step: RD should wire patient inventory off the client checkpoint, then run the PDF size pass without downloading PDF bodies
- questions_for_twi: none
- decision_needed: none

## 2026-07-09 16:53:18 UTC
- changed_file: pony/team.coordination/rd.status.md, pony/work/rd.md, pony/team.coordination/twi.status.md, pony/team.coordination/twi.event.stream.history.md
- action: recorded Rainbow Dash live Instinct REST metadata totals and pagination correction
- finding: endpoint metadata exposes clients/accounts total = 10,000 and patients total = 10,000; pagination uses metadata.after plus pageCursor, not nextPageCursor
- status: ASSIGNED
- blockers: vector DB connection information still blocks live enhanced chunk storage/search validation, but metadata-only PDF size-table work can continue
- next_step: RD should build the PDF size table metadata-only, with no PDF body downloads yet
- questions_for_twi: none
- decision_needed: none

## 2026-07-09 16:54:09 UTC
- changed_file: pony/team.coordination/spike.status.md, pony/work/spike.md, pony/team.coordination/twi.status.md, pony/team.coordination/twi.event.stream.history.md
- action: recorded Spike docs follow-up for RD's live Instinct REST findings
- finding: RAG/PDF API notes should include clients/accounts total = 10,000, patients total = 10,000, pagination via metadata.after plus pageCursor rather than nextPageCursor, and metadata-only PDF size-table pass with no PDF body downloads
- status: WAITING
- blockers: none for Spike
- next_step: Spike should apply this docs correction when next touching the RAG/PDF API notes
- questions_for_twi: none
- decision_needed: none

## 2026-07-09 16:55:43 UTC
- changed_file: pony/team.coordination/rd.status.md, pony/work/rd.md, pony/team.coordination/spike.status.md, pony/work/spike.md, pony/team.coordination/twi.status.md, pony/team.coordination/twi.event.stream.history.md
- action: recorded Rainbow Dash Instinct pagination bug fix and restarted live client sweep
- finding: live client/patient inventory now uses metadata.after with pageCursor instead of nextPageCursor; RD restarted the live client sweep and will run the PDF size-table pass after the inventory is trustworthy
- status: ASSIGNED
- blockers: vector DB connection information still blocks live enhanced chunk storage/search validation, but live inventory and metadata-only PDF sizing can continue
- next_step: RD should complete the trustworthy inventory sweep, then run the metadata-only PDF size-table pass with no PDF body downloads
- questions_for_twi: none
- decision_needed: none

## 2026-07-09 16:56:56 UTC
- changed_file: pony/team.coordination/rd.status.md, pony/work/rd.md, pony/team.coordination/spike.status.md, pony/work/spike.md, pony/team.coordination/twi.status.md, pony/team.coordination/twi.event.stream.history.md
- action: recorded Rainbow Dash completed live client sweep and patient sweep start
- finding: real live client/account count is 12,053; client sweep completed and was saved to a worktree checkpoint, but the letter did not include the exact checkpoint path; patient sweep has started from that inventory
- status: ASSIGNED
- blockers: vector DB connection information still blocks live enhanced chunk storage/search validation, but metadata-only patient/PDF sizing work can continue
- next_step: RD should finish the metadata-only patient sweep, report the exact checkpoint path if not already durable, then continue to the metadata-only PDF size-table pass with no PDF body downloads
- questions_for_twi: none
- decision_needed: none

## 2026-07-09 16:58:09 UTC
- changed_file: pony/team.coordination/rd.status.md, pony/work/rd.md, pony/team.coordination/twi.status.md, pony/team.coordination/twi.event.stream.history.md
- action: recorded Rainbow Dash durable client checkpoint path
- finding: durable client checkpoint is `/home/ggb66/dev/EVH/pony/worktrees/rd/client_inventory.json`; live client sweep completed at 12,053 clients/accounts; patient sweep continues metadata-only from that checkpoint with no PDF body downloads
- status: ASSIGNED
- blockers: vector DB connection information still blocks live enhanced chunk storage/search validation, but metadata-only patient/PDF sizing work can continue
- next_step: RD should finish the metadata-only patient sweep, then run the metadata-only PDF size-table pass with no PDF body downloads
- questions_for_twi: none
- decision_needed: none

## 2026-07-09 16:59:55 UTC
- changed_file: pony/team.coordination/rd.status.md, pony/work/rd.md, pony/team.coordination/spike.status.md, pony/work/spike.md, pony/team.coordination/twi.status.md, pony/team.coordination/twi.event.stream.history.md
- action: recorded Rainbow Dash patient checkpoint and PDF size-table start
- finding: saved patient checkpoint `/home/ggb66/dev/EVH/pony/worktrees/rd/patient_inventory.json` currently contains 197 patients; patient sweep remains metadata-only with no PDF body downloads; RD is starting the live metadata-only PDF size-table pass and will bin sizes to separate huge image-only PDFs from real text PDFs
- status: ASSIGNED
- blockers: vector DB connection information still blocks live enhanced chunk storage/search validation, but metadata-only PDF sizing/binning can continue
- next_step: RD should run the metadata-only PDF size-table pass, bin sizes, and report counts/thresholds without downloading PDF bodies
- questions_for_twi: none
- decision_needed: none

## 2026-07-09 17:08:34 UTC
- changed_file: pony/team.coordination/rd.status.md, pony/work/rd.md, pony/team.coordination/spike.status.md, pony/work/spike.md, pony/team.coordination/twi.status.md, pony/team.coordination/twi.todo.md, pony/team.coordination/twi.event.stream.history.md
- action: recorded Rainbow Dash metadata-only PDF size pass result and decision point
- finding: 923 chart-file rows collected from `/home/ggb66/dev/EVH/pony/worktrees/rd/patient_inventory.json`; signed PDF URL HEAD probes returned no Content-Length, so size is unknown for all rows and the gap-bin threshold cannot be computed; no PDF bodies have been downloaded
- status: BLOCKED
- blockers: need either Instinct file-size metadata or explicit user permission for a minimal range/body probe; vector DB connection information still blocks live enhanced chunk storage/search validation
- next_step: ask the user for decision; RD should hold no-body-download posture and avoid range/body probes until approved
- questions_for_twi: user decision required on minimal range/body probe versus metadata-only file-size source
- decision_needed: yes

## 2026-07-09 17:09:50 UTC
- changed_file: pony/team.coordination/rd.status.md, pony/work/rd.md, pony/team.coordination/spike.status.md, pony/work/spike.md, pony/team.coordination/twi.status.md, pony/team.coordination/twi.todo.md, pony/team.coordination/twi.event.stream.history.md
- action: recorded Rainbow Dash no-body metadata size-field check
- finding: GraphQL ChartFile does not expose fileSize; live no-body metadata only exposes identifiers, filenames, labels, contentType, and timestamps; no usable metadata-only size field is available for the 923 chart-file rows
- status: BLOCKED
- blockers: explicit user approval is required before any minimal range/body probe; vector DB connection information still blocks live enhanced chunk storage/search validation
- next_step: ask user whether to approve RD minimal range/body probe or leave PDF size split blocked
- questions_for_twi: user decision required
- decision_needed: yes

## 2026-07-09 19:11:42 UTC
- changed_file: pony/team.coordination/twi.status.md, pony/team.coordination/twi.event.stream.history.md
- action: routed user-approved agenic system hardening request to Celestia
- finding: EVH runtime showed a coordination wobble where pending approval state could interleave with routine worker acknowledgements, and generated review-needed snippets could appear in active durable event history
- status: WAITING
- blockers: none for Celestia routing; RD minimal range/body probe still needs user approval before execution
- next_step: Celestia should consider hardening agenic system message handling so pending user approvals stay isolated from routine mailbox acknowledgements and generated review snippets do not pollute durable coordination history
- questions_for_twi: none
- decision_needed: none for Celestia routing

## 2026-07-10 00:00:00 EDT
- changed_file: pony/team.coordination/assignment.registry.tsv, pony/team.coordination/twi.status.md, pony/team.coordination/twi.mailbox.md, pony/work/coordinator-twi.md, pony/team.coordination/twi.event.stream.history.md
- action: acknowledged Celestia source-runtime launcher governance update and corrected local Twilight routing branch fields
- finding: Celestia reports agenic-pony-system launch-team-member now defaults ordinary team members to direct Codex startup, with parked host explicit via --parked or --host-mode parked; no live EVH sessions were touched. Local EVH state had a routing mismatch where Twilight's live git branch is pony/twi/main but assignment/status/workfile branch fields said main.
- status: WAITING
- blockers: no launcher handoff blocker remains for Twilight after local branch-field correction; RD minimal range/body probe still needs user approval before execution, and vector DB connection information remains missing for live enhanced chunk storage/search validation
- next_step: continue routing Twilight locally in EVH on pony/twi/main; do not stop at source launcher state; await user decision on RD minimal range/body probe
- questions_for_twi: none
- decision_needed: user approval still required for RD minimal range/body probe

## 2026-07-10 00:00:00 EDT
- changed_file: pony/team.coordination/twi.event.stream.history.md
- action: recorded Applejack Bazel workflow fork-CI safety review letter
- finding: AJ reports `.github/workflows/bazel.yml` fork-CI safety is clean: macOS and windows-latest matrix entries were removed from Linux test/clippy/verify-release-build jobs; Linux validation remains on ubuntu-24.04 x86_64-unknown-linux-gnu; test-windows-shard is gated to openai/codex; test-windows exits 0 on forks when the shard is skipped; AJ found no clear YAML bug worth editing. Local EVH inspection found no `.github/workflows/bazel.yml`, so this is treated as an external/off-project review note and no EVH workflow edit was made.
- status: WAITING
- blockers: none from AJ Bazel workflow review; RD minimal range/body probe still needs user approval before execution, and vector DB connection information remains missing for live enhanced chunk storage/search validation
- next_step: keep AJ on current EVH DB scope unless the user explicitly assigns a local EVH action for the Bazel workflow review
- questions_for_twi: none
- decision_needed: none for AJ Bazel workflow review

## 2026-07-12 21:14:02 EDT
- changed_file: pony/team.coordination/assignment.registry.tsv, pony/team.coordination/twi.status.md, pony/team.coordination/twi.todo.md, pony/team.coordination/twi.pending-approvals.md, pony/team.coordination/rd.status.md, pony/work/rd.md, pony/work/coordinator-twi.md, pony/team.coordination/twi.event.stream.history.md
- action: recorded RD live Instinct PDF import handoff and corrected stale routing state
- finding: user says RD's active mission is the live Instinct PDF import with RUN -> ANALYZE -> FIX -> RESTART, checkpoint preservation at `/tmp/evh_instinct_import.checkpoint.json`, log `/tmp/evh_instinct_import.supervised.log`, and supervisor `/tmp/evh_supervise_import.sh`; the old RD no-body PDF-size-probe blocker is superseded. Twilight observed no active supervisor process from this session, with /tmp import artifacts last modified on 2026-07-10 around 00:36 EDT.
- status: COORDINATING_RD_IMPORT
- blockers: local runtime mismatch only: coordination files were stale relative to the user handoff, and the supervisor does not appear active from this session
- next_step: RD should inspect the supervised log and checkpoint first, preserve the checkpoint, patch any new root cause, and restart the supervisor if appropriate
- questions_for_twi: none
- decision_needed: none recorded; Instinct password from chat must not be persisted or echoed

## 2026-07-13 00:12:00 EDT
- changed_file: pony/team.coordination/assignment.registry.tsv, pony/team.coordination/twi.status.md, pony/team.coordination/twi.todo.md, pony/team.coordination/twi.pending-approvals.md, pony/team.coordination/rd.status.md, pony/work/coordinator-twi.md, pony/team.coordination/twi.event.stream.history.md
- action: rechecked Twilight routing and RD import supervisor state
- finding: live git branch is pony/twi/main, but local Twilight branch fields still said main in several coordinator files; corrected them to pony/twi/main. RD import artifacts are current to 2026-07-13 00:04 EDT, but no evh_supervise_import process is visible from this session. The supervised log stops mid-PDF at Blair_MedicalNotes.pdf chunk_start; checkpoint shows client_seen_count=141, patient_seen_count=296, pdf_count=40, loaded_count=38, skipped_count=1, processed_pdf_ids=1376.
- status: COORDINATING_RD_IMPORT
- blockers: routing mismatch was stale local branch metadata for Twilight plus no visible live supervisor process for RD import
- next_step: route Twilight locally in EVH on pony/twi/main; RD should inspect the stop around Blair_MedicalNotes.pdf chunk_start, preserve /tmp/evh_instinct_import.checkpoint.json, patch any root cause if found, and restart /tmp/evh_supervise_import.sh if appropriate
- questions_for_twi: none
- decision_needed: none recorded; do not persist or echo the Instinct password from chat

## 2026-07-14 - Pinkie reassigned to PDF search UI
- action: updated Pinkie's canonical assignment from Idle/Weave Contacts state to UI for PDF search
- source: user correction in chat: Pinkie's assignment is not Weave Contacts anymore but UI for PDF search
- files_updated: pony/team.coordination/assignment.registry.tsv, pony/team.coordination/pinkie.status.md, pony/work/pinkie.md, pony/work/coordinator-twi.md
- next_step: Pinkie should inspect existing app/UI/search surfaces and take over the UI for PDF search; do not continue Weave Contacts unless reassigned
- blockers: none recorded for the new Pinkie UI assignment
- routing_check: verified live branch is `pony/twi/main` and corrected Twilight branch metadata that still said `main`
- live_message: sent Pinkie direct `/tell` assignment update, id `8785f2cd-45d1-4407-af16-032d0777ffc0`

## 2026-07-14 - Pinkie PDF search UI progress letter
- from: Pinkie Pie
- action: recorded Pinkie's PDF search UI takeover and implementation progress
- finding: Pinkie updated `scripts/rag_ui/static/index.html` to reframe the shell as EVH Instinct PDF RAG and added a PDF query intent panel plus preview state
- reported_tests: `/home/ggb66/dev/EVH/.venv/bin/python -m pytest tests/test_rag_ui.py` passed
- files_reported: scripts/rag_ui/static/index.html, pony/work/pinkie.md, pony/team.coordination/pinkie.status.md
- local_observation: changes are in Pinkie's worker worktree as untracked `scripts/rag_ui/` and `tests/test_rag_ui.py`; root coordinator state records the letter
- status: PDF_SEARCH_UI_PROGRESS_REPORTED
- blockers: backend document-search/source-PDF results contract is needed before final endpoint wiring; owner: Twilight to assign RD/AJ backend owner and hand Pinkie the endpoint/response shape
- next_step: Pinkie should wire the PDF query intent panel to the actual document-search endpoint or add the source-PDF results pane once the backend contract is available
- questions_for_twi: none
- decision_needed: none recorded
- live_message: acknowledged Pinkie via `/tell`, id `a60d4344-7ed3-4891-88d8-c15e447036f8`

## 2026-07-14 - Rarity reassigned to EVH Mail Archival and Organization
- action: updated Rarity's canonical assignment from Meds & Treatments/Stockroom state to EVH Mail Archival and Organization
- source: user correction in chat: Rarity's assignment is EVH Mail Archival and Organization
- files_updated: pony/team.coordination/assignment.registry.tsv, pony/team.coordination/rarity.status.md, pony/work/rarity.md, pony/work/coordinator-twi.md
- next_step: Rarity should inspect existing mail/archive materials and take over the next concrete EVH Mail Archival and Organization slice; do not continue Meds & Treatments or Stockroom unless reassigned
- blockers: none recorded for the new Rarity mail archival assignment
- questions_for_twi: none
- decision_needed: none recorded
- live_message: sent Rarity direct `/tell` assignment update, id `e7ef16c9-e5e0-4a4b-93bd-c008e3fce541`

## 2026-07-14 - Rarity mail/archive inventory progress letter
- from: Rarity
- action: recorded Rarity's move from inspection to documentation/inventory for EVH Mail Archival and Organization
- finding: Rarity inspected active mail/archive surfaces and is adding a small EVH mail/archive inventory doc that catalogs current mailbox/archive materials and the Handshake PDF explorer prototype
- status: MAIL_ARCHIVAL_INVENTORY_IN_PROGRESS
- files_planned: small EVH mail/archive inventory doc; pony/work/rarity.md; pony/team.coordination/rarity.status.md
- blockers: none
- next_step: Rarity should finish the inventory doc, then refresh Rarity work/status with the next archival slice
- questions_for_twi: none
- decision_needed: none recorded
- live_message: acknowledged Rarity via `/tell`, id `054903fc-5d78-4d6f-b6f0-15012f8b83c3`

## 2026-07-14 - Rarity first mail/archive slice complete
- from: Rarity
- action: recorded completion of Rarity's first EVH Mail Archival and Organization slice
- finding: Rarity created `docs/evh-mail-archive-inventory.md`, cross-linked `docs/handshake-pdf-browser/README.md` back to the inventory, and refreshed Rarity work/status
- status: MAIL_ARCHIVAL_FIRST_SLICE_COMPLETE
- files_touched: docs/evh-mail-archive-inventory.md, docs/handshake-pdf-browser/README.md, pony/work/rarity.md, pony/team.coordination/rarity.status.md
- blockers: none
- next_step: Rarity should inspect `scripts/coordination/archive/` for the next cleanup, rename, or cross-link in the mail/archive surfaces
- questions_for_twi: none
- decision_needed: none recorded
- live_message: acknowledged Rarity via `/tell`, id `27ac843a-d24d-4f49-8f06-ac11018d385a`

## 2026-07-14 - Spike evhstaff Google Mail coordination check
- from: Spike
- action: recorded Spike's local EVH coordination-state check for Rarity's evhstaff Google Mail question
- finding: Spike found Rarity's request in `pony/team.coordination/evh_spike.mailbox.md`, but no authoritative handoff, credential owner, or access-details record for an evhstaff Google Mail account in local EVH coordination state
- local_observation: `docs/instinct-live-samples.json` mentions `evhstaff@gmail.com` as sample/import data, but that is not an authorization handoff or credential record
- status: EVHSTAFF_GOOGLE_MAIL_HANDOFF_UNCONFIRMED
- blockers: existing authorized account/handoff and credential owner are unconfirmed; owner for unblock is user/Twilight confirmation
- next_step: do not create a new mailbox yet; first confirm whether an existing authorized account or handoff lives outside the current local coordination state
- questions_for_twi: none; Twilight local-state answer is no authoritative handoff found
- decision_needed: user confirmation needed only if work should proceed with a specific account or new mailbox creation
- live_message: acknowledged Spike via `/tell`, id `5e374630-9658-4449-b07e-e6d8e35e2d4e`; routed safe-state answer to Rarity via `/tell`, id `1673ade1-6d53-4c82-9db4-2d23d3de5c57`

## 2026-07-14 - Rarity EVHStaff Gmail Cleanup blocker
- from: Rarity
- action: recorded live blocker and corrected shared-state mismatch for EVHStaff Gmail Cleanup
- finding: evhstaff@gmail.com Gmail cleanup is blocked by Google verification error 403 access_denied: app is still in testing and only developer-approved testers may access it
- mismatch_corrected: `rarity.status.md` previously said `BLOCKERS: none` and next step `scripts/coordination/archive/`; shared state now records the Gmail access blocker
- status: BLOCKED_EVHSTAFF_GMAIL_ACCESS
- missing_artifact: existing authorized tester/account OR app-verification/allowlist approval path
- owner: user/Twilight
- next_step: Unblock path: user/Twilight must provide an existing authorized tester/account or the app-verification/allowlist approval path; otherwise Rarity should pause EVH mail archival work at the launcher boundary.
- questions_for_twi: none; unblock requires user/Twilight-provided authorization path
- decision_needed: yes, if the user wants EVHStaff Gmail Cleanup to proceed
- live_message: acknowledged Rarity via `/tell`, id `5e63086b-cdb4-48fd-80bf-2f8bdc29d5bb`

## 2026-07-14 - Spike Gmail archival run durable update
- from: Spike
- action: recorded working helper, command pattern, scope, OAuth reset path, and observed deletion result for EVHStaff Gmail archival run
- helper: `scripts/gmail/evhstaff_gmail_inventory.py`
- command_pattern: `python scripts/gmail/evhstaff_gmail_inventory.py --client-secrets /path/to/evhstaff_gmail_google_client_credentials.json --token-file /path/to/evhstaff_gmail_token.json --query 'older_than:3y' --export-zip /path/to/archive.zip --delete-after-export`
- required_scope: `https://mail.google.com/`
- token_reset_reauth: delete the token cache and rerun the OAuth installed-app flow with `prompt=consent`
- scope_finding: `gmail.modify` was insufficient for permanent deletion; the helper needed `https://mail.google.com/`
- observed_result: 3303 deleted with `permanent_delete=true`
- status: EVHSTAFF_GMAIL_ARCHIVAL_RUN_RECORDED
- blockers: none for the recorded run; prior OAuth testing/allowlist blocker is superseded by the successful authorized run
- next_step: preserve helper/run notes; use placeholder command pattern with local credential/token/archive paths only if another authorized run is needed
- questions_for_twi: none
- decision_needed: none recorded
- live_message: acknowledged Spike via `/tell`, id `89302c5c-34cf-4107-abdc-cfd8c0c943bd`; routed updated state to Rarity via `/tell`, id `559e1aab-de0f-4746-a6a3-d2798cb7ef39`
## 2026-07-15 07:21:52 EDT
- changed_file: pony/team.coordination/twi.status.md, pony/team.coordination/twi.todo.md, pony/team.coordination/twi.pending-approvals.md, pony/team.coordination/rd.status.md, pony/work/rd.md, pony/work/coordinator-twi.md, pony/team.coordination/twi.event.stream.history.md
- action: recorded RD routing correction from Rainbow Dash letter and local /tmp inspection
- finding: RD workfile still had older no-body size-probe hold language, while rd.status/twi.status agree the active mission is live supervised Instinct PDF import on `pony/rd/main`. Local /tmp artifacts have advanced beyond the older Blair_MedicalNotes.pdf stop named in the letter: `/tmp/evh_instinct_import.supervised.log` is not visible from this session, `/tmp/evh_instinct_import.checkpoint.json` was updated 2026-07-14 21:34 EDT with loaded_count=0, skipped_count=134, processed_pdf_ids_count=3680, current_pdf_id=40060, current_filename=EXAMREPORTCARDCBC2.2.doc, and `/tmp/evh_instinct_import_fixed.out` exits 1 at EXAMREPORTCARDCBC2.2.doc chunk_start with invalid PDF/OLE header / PdfStreamError.
- status: COORDINATING_RD_IMPORT
- blockers: stale RD workfile routing plus current import stop on non-PDF/corrupt-PDF handling; no live supervisor process is visible from this session
- next_step: RD should preserve `/tmp/evh_instinct_import.checkpoint.json`, inspect current stop artifacts first (`/tmp/evh_instinct_import_fixed.out` and checkpoint; older Blair_MedicalNotes.pdf supervised-log stop if restored), patch non-PDF/corrupt-PDF handling, run real syntax/lint sanity after importer/chunker edits, then restart supervised import from checkpoint if appropriate
- questions_for_twi: none
- decision_needed: none recorded; do not persist or echo the Instinct password from chat
- live_message: acknowledged RD via `/tell`, id `d609adcb-b963-49ce-a644-bb2b7b52b66f`
## 2026-07-15 07:24:48 EDT
- changed_file: pony/team.coordination/twi.status.md, pony/team.coordination/twi.todo.md, pony/team.coordination/twi.pending-approvals.md, pony/team.coordination/rd.status.md, pony/work/rd.md, pony/work/coordinator-twi.md, pony/team.coordination/twi.event.stream.history.md
- action: recorded RD patch/test/restart update for live Instinct PDF import
- finding: RD checked `/tmp/evh_instinct_import.checkpoint.json` and `/tmp/evh_instinct_import_fixed.out`, patched `scripts/instinct_pdf_chunker.py` so non-PDF/corrupt-PDF failures including invalid PDF/OLE header and PdfStreamError defer as DeferredOCRDocument instead of crashing, ran compileall plus AST/tabnanny sanity, and restarted `/tmp/evh_supervise_import.sh` from the checkpoint. Twilight local observation: `/tmp/evh_instinct_import.supervised.log` exists but was empty at 07:24 EDT and no supervisor/import process was visible from this session.
- status: RD_IMPORT_RESTARTED_WATCH_LOG
- blockers: restart/progress verification remains pending; no return to old no-body size-probe blocker
- next_step: RD should check `/tmp/evh_instinct_import.supervised.log` for progress past `EXAMREPORTCARDCBC2.2.doc`; if it remains empty or no process is alive, inspect restart/launcher output, preserve checkpoint, and restart or patch the next root cause as appropriate
- questions_for_twi: none
- decision_needed: none recorded; do not persist or echo the Instinct password from chat
- live_message: acknowledged RD via `/tell`, id `8e59ab1e-eeac-4281-829c-ba0e6379e1d3`

## 2026-07-16 10:46:53 EDT
- from: Rarity
- action: recorded Gmail sender taxonomy/OpenAI request-payload update
- finding: Rarity updated `scripts/gmail/evhstaff_gmail_inventory.py` for the merged 15-category sender taxonomy, set the OpenAI fallback default model to `gpt-5.6-luna`, threaded `reasoning.effort` and `text.verbosity` through the OpenAI request payload, and reports `python3 -m py_compile` passed.
- status: GMAIL_SENDER_TAXONOMY_UPDATED
- files_touched_reported: scripts/gmail/evhstaff_gmail_inventory.py
- blockers: none recorded for this update; prior OAuth testing/allowlist blocker remains superseded by the successful authorized Gmail run
- next_step: rerun with `--openai-classifier-model gpt-5.6-luna --openai-reasoning-effort none --openai-text-verbosity low` and inspect `/tmp/evh_gmail_sender_routing_map.regen.json`
- coordinator_routing_mismatch: startup local Twilight branch metadata still said `main` while the live branch is `pony/twi/main`; corrected `twi.status.md` and `pony/work/coordinator-twi.md` instead of stopping at launcher routing.
- questions_for_twi: none
- decision_needed: none recorded
- live_message: acknowledged Rarity via `/tell`, id `bd59f848-1e48-4244-854c-fcb732549e18`

## 2026-07-16 10:57:10 EDT
- from: Rarity
- action: recorded Gmail OpenAI fallback default swap and rerun guidance
- finding: Rarity swapped the OpenAI fallback default in `scripts/gmail/evhstaff_gmail_inventory.py` from `gpt-5.6-luna` to `gpt-5.6-mini`, kept `reasoning.effort=none` and `text.verbosity=low` threading intact, and reports `python3 -m py_compile` passed.
- status: GMAIL_OPENAI_FALLBACK_MINI_UPDATED
- files_touched_reported: scripts/gmail/evhstaff_gmail_inventory.py
- blockers: none recorded for this update
- next_step: rerun with `--openai-classifier-model gpt-5.6-mini --openai-reasoning-effort none --openai-text-verbosity low` and inspect `/tmp/evh_gmail_sender_routing_map.regen.json`
- later_pass: Terra is reserved for a later pass over leftovers if needed.
- questions_for_twi: none
- decision_needed: none recorded
- live_message: acknowledged Rarity via `/tell`, id `d0115640-dbe6-4d45-bfe9-387e80e361d0`

## 2026-07-16 11:56:40 EDT
- from: Rarity
- action: recorded Rarity confirmation and dirty-worktree preflight reconciliation
- finding: Rarity confirmed Twilight's durable rerun note matches current local state: `gpt-5.6-mini`, `reasoning.effort=none`, `text.verbosity=low`, and Terra reserved only for a later leftovers pass if needed.
- preflight: inspected pending local changes; corrected Twilight branch metadata back to `pony/twi/main`; reconciled stale Rarity Gmail access blocker language as superseded by the successful authorized run; put away the large local zip artifact outside the repo.
- status: COORDINATING_RARITY_GMAIL_OPENAI_FALLBACK_MINI
- blockers: none recorded for the current Rarity Gmail sender-routing rerun
- next_step: Rarity should rerun with `--openai-classifier-model gpt-5.6-mini --openai-reasoning-effort none --openai-text-verbosity low` and inspect `/tmp/evh_gmail_sender_routing_map.regen.json`; reserve Terra for leftovers only if needed.
- questions_for_twi: none
- decision_needed: none recorded
- live_message: acknowledged Rarity via `/tell`, id `eca30085-5d07-4bc1-8de8-f3971687e031`

## 2026-07-16 12:16:20 EDT
- from: Rainbow Dash
- action: recorded RD live import restart after deferred-OCR / psql write-path fix
- finding: RD and Spike confirmed the checkpoint survived the `EXAMREPORTCARDCBC2.2.doc` stop and the failure shifted into deferred-OCR DB writes / psql disconnects. RD patched `scripts/instinct_full_import_fixed.py` so deferred-OCR DB writes are best-effort instead of fatal, ran syntax/tabnanny sanity, and relaunched from `/tmp/evh_instinct_import.checkpoint.json` with sourced Postgres + Instinct env.
- local_watch: at 2026-07-16 12:16 EDT, `/tmp/evh_instinct_import_fixed.out` and `/tmp/evh_instinct_import.checkpoint.json` were updating; output showed import heartbeat/progress around `Pullins_Janice_TransactionHistory.pdf`; `/tmp/evh_instinct_import_fixed.status` and `.exitcode` were present but empty; no import process was visible from Twilight's session.
- status: RD_IMPORT_RESTARTED_FIXED_WRITE_PATH_WATCH
- blockers: none current; blocker only if vector DB keeps closing the connection or the fixed importer stops with a new fatal error.
- next_step: watch `/tmp/evh_instinct_import_fixed.out`, `/tmp/evh_instinct_import_fixed.status`, and `/tmp/evh_instinct_import_fixed.exitcode`; preserve `/tmp/evh_instinct_import.checkpoint.json`.
- questions_for_twi: none
- decision_needed: none recorded
- live_message: acknowledged RD via `/tell`, id `89bbaa34-c859-4a00-8dbe-30e274aecbe4`

## 2026-07-16 23:59:45 EDT
- from: Rarity
- action: recorded Gmail sender-routing picker completion and contaminated-source recovery plan
- finding: Rarity completed `scripts/gmail/review_sender_routing_picker.py` with Gmail preview fetching/caching/fallback queries, Escape/q save-and-exit behavior, backup-on-same-input-output handling, `Uncategorized` as the no-fetch fallback, and compile verification. She generated/updated `NamesEmailAddressesCategoriesSource.txt` and `reviewed_email_categories.txt`, but found the source contaminated by mixed sender data from a non-evhstaff mailbox export.
- status: GMAIL_SENDER_ROUTING_REBUILD_REQUIRED
- blockers: current sender-routing source/review artifacts are not trustworthy because they include mixed sender data from another mailbox; clean single-mailbox `evhstaff@gmail.com` source list is missing
- next_step: preserve the picker script work, start over tomorrow from `evhstaff@gmail.com` only, rebuild the routing list from scratch, and do not reuse the contaminated mixed-source list
- questions_for_twi: none
- decision_needed: none recorded

## 2026-07-17 00:00:41 EDT
- action: Twilight shutdown state saved before user-requested shutdown
- status: SHUTDOWN_STATE_SAVED
- routing: Twilight verified on `pony/twi/main`; assignment registry Twilight branch field aligned to `pony/twi/main`
- blockers: no pending user approvals or Twilight decisions; RD blocker only if vector DB disconnects persist or the fixed importer stops with a new fatal error; Rarity sender-routing artifacts are contaminated by mixed sender data and must be rebuilt from `evhstaff@gmail.com` only
- next_step: on restart, read local EVH coordinator state first, watch RD `/tmp/evh_instinct_import_fixed.out`/`.status`/`.exitcode` plus checkpoint, compare importer timing fields, and route Rarity to preserve picker work while rebuilding the sender-routing source from the single mailbox only
- questions_for_twi: none
- decision_needed: none recorded

## 2026-07-17 RD timing-work clarification
- action: answered RD timing-work thread and refreshed RD status
- focus: live Instinct fixed importer timing pass after `scripts/instinct_full_import_fixed.py` timing hooks and dead success-path control-flow fix
- timing_fields: `timing_signed_url`, `timing_extract_chunk`, `timing_deferred_ocr_record`, `timing_embed_load`, `timing_process_pdf_total` in `/tmp/evh_instinct_import_fixed.out`
- latest_local_check: `/tmp/evh_instinct_import_fixed.out` last updated 2026-07-17 00:16 EDT and checkpoint last updated 00:15 EDT around `Tonkin_Terri_TransactionHistory.pdf`; `/tmp/evh_instinct_import_fixed.status` and `.exitcode` empty; no fixed importer process visible from Twilight session
- next_step: preserve `/tmp/evh_instinct_import.checkpoint.json`, relaunch the fixed importer with the real launcher after sourcing local Postgres/Instinct env, then compare timing fields and watch status/exitcode
- blocker: none current; escalate only on a new fatal stop or repeated vector DB connection closure

## 2026-07-17 15:50:14 EDT
- action: processed worker letters and corrected Twilight routing metadata
- coordinator_routing_mismatch: live branch is `pony/twi/main`, but `assignment.registry.tsv`, `twi.status.md`, and `pony/work/coordinator-twi.md` still carried stale `main` metadata; corrected local authoritative state instead of stopping at launcher.
- pinkie: recorded active PDF-search UI slice, not old Weave Contacts; next restart context is UI surface inspection plus route/component identification and backend-contract follow-up if needed.
- rd: confirmed authoritative routing is `rd.status.md`, live mailbox, and refreshed `pony/work/rd.md`; stale no-body/Vetcove hold notes are superseded. Next is preserving checkpoint and relaunching the fixed importer timing pass from `/tmp/evh_instinct_import.checkpoint.json`.
- spike: recorded refreshed Docs restart state on `pony/spike/main`; next docs delta is RD-confirmed Instinct totals/pagination: clients/accounts 10,000, patients 10,000, `metadata.after` + `pageCursor`.
- rarity: confirmed zero-byte `/tmp/evh_gmail_sender_category_cache.json` is a corrupt/empty local cache, not an expected populated source; rebuild/omit it and regenerate sender routing from `evhstaff@gmail.com` only with `gpt-5.6-mini`, `reasoning.effort=none`, `text.verbosity=low`.
- fs: recorded vet-term taxonomy maintenance update on `pony/fs/main`; `docs/instinct-vet-term-taxonomy.md` now has species-specific aliases and related context terms; no blocker.
- questions_for_twi: none
- decision_needed: none recorded

## 2026-07-17 15:50:55 EDT
- from: Pinkie Pie
- action: recorded durable PDF-search UI source-PDF browsing slice
- finding: Pinkie updated `docs/handshake-pdf-browser/index.html` with clickable page-link rows in the evidence pane, click-to-focus behavior for source pages, and separate current search token state so the preview behaves like a document results viewer.
- status: PDF_SEARCH_UI_SOURCE_PDF_BROWSING_SLICE_ADDED
- files_touched_reported: docs/handshake-pdf-browser/index.html, pony/work/pinkie.md, pony/memory/pinkie.md
- blockers: backend document-search/source-PDF response shape is still needed before final live renderer wiring
- next_step: inspect page-link interactions now; wire preview to live renderer when the backend contract lands
- questions_for_twi: none
- decision_needed: none recorded

## 2026-07-17 15:51:25 EDT
- action: sent live acknowledgements for worker letters
- pinkie_live_message: 236d633c-bcbd-43a0-a05f-78b69124ab78
- rd_live_message: 984137a0-01e6-4931-b6ed-62ad0320c31d
- spike_live_message: d7baf48b-4611-45fe-b024-446897444c39
- rarity_live_message: f27a1921-03fd-480b-9510-813f2b568f49
- fs_live_message: caa77230-db78-48a3-b982-b2dbb9d54417

## 2026-07-17 15:52:50 EDT
- from: Rarity
- action: recorded cache recovery and approved sender-routing rerun
- finding: `/tmp/evh_gmail_sender_category_cache.json` was zero bytes, likely from interrupted write, and Rarity recreated it as `{}`.
- status: GMAIL_SENDER_ROUTING_RERUN_READY
- next_step: rerun the inventory/classifier now from the single-mailbox `evhstaff@gmail.com` path only with `gpt-5.6-mini`, `reasoning.effort=none`, `text.verbosity=low`; do not reuse mixed-source artifacts and do not use `--delete-after-export`; inspect `/tmp/evh_gmail_sender_routing_map.regen.json` and report counts/errors.
- blockers: none current for rerun
- questions_for_twi: none
- decision_needed: none recorded

## 2026-07-17 15:52:57 EDT
- action: sent live Rarity rerun approval
- rarity_live_message: 587e9546-f06b-486a-bb52-cd44de8c0edd

## 2026-07-17 16:44:48 EDT
- from: Rarity
- action: recorded daily summarizer Gmail-send support and routed safe next step
- finding: `scripts/gmail/daily_email_summary.py` now supports `--send-email` to default recipient `evhstaff+daily_summary@gmail.com`, while still writing `/tmp/evh_daily_email_summary.md` and `/tmp/evh_daily_email_summary.json`; Twilight verified `python3 -m py_compile scripts/gmail/daily_email_summary.py` passes.
- status: GMAIL_DAILY_SUMMARY_SEND_SUPPORT_ADDED
- next_step: add a small `.sh` wrapper and run dry-run/no-send validation only; keep sender-routing rerun separate and non-destructive.
- approval_boundary: do not run real `--send-email` until the user explicitly approves it.
- blockers: none for wrapper/dry-run
- questions_for_twi: none
- decision_needed: explicit user approval required before real send

## 2026-07-17 16:44:57 EDT
- action: sent live Rarity daily-summary wrapper/dry-run routing
- rarity_live_message: f1211d5f-2adf-4139-953e-d43ddd682cb1

## 2026-07-17 16:47:12 EDT
- from: Rarity
- action: recorded daily email summary wrapper and dry-run validation complete
- finding: `scripts/gmail/run_daily_email_summary.sh` was added and defaults to no-send dry-run. Validation wrote `/tmp/evh_daily_email_summary.md` and `/tmp/evh_daily_email_summary.json`, reviewed 14 unread messages, and made no OpenAI request.
- status: GMAIL_DAILY_SUMMARY_DRY_RUN_COMPLETE
- sender_routing: separate and untouched; continue only on the single-mailbox `evhstaff@gmail.com` path with no mixed-source artifacts.
- approval_boundary: real `--send-email` to `evhstaff+daily_summary@gmail.com` remains gated on explicit user approval.
- blockers: none for dry-run output
- questions_for_twi: none
- decision_needed: explicit user approval required only before real send

## 2026-07-17 16:47:22 EDT
- action: sent live Rarity dry-run completion acknowledgement
- rarity_live_message: 354b742a-75a1-49d0-b4cd-f3a9825417e5

## 2026-07-17 16:49:55 EDT
- from: Rarity
- action: recorded sender-routing artifact rename
- finding: `/tmp/evh_gmail_sender_routing_map.regen.json` was renamed to `/tmp/evh_gmail_sender_routing_map.text` because the output is plain text routing data rather than JSON.
- status: GMAIL_SENDER_ROUTING_TEXT_ARTIFACT_RENAMED
- next_step: inspect/review `/tmp/evh_gmail_sender_routing_map.text` as the current sender-routing artifact; keep sender-routing separate from daily summary work.
- approval_boundary: daily-summary real `--send-email` remains gated on explicit user approval.
- blockers: none for artifact rename
- questions_for_twi: none
- decision_needed: explicit user approval required only before real daily-summary send

## 2026-07-17 16:50:03 EDT
- action: sent live Rarity artifact-rename acknowledgement
- rarity_live_message: b74d3d07-51b0-4532-a39f-db4030d7f9e1

## 2026-07-17 16:50:59 EDT
- from: Rarity
- action: recorded sender-routing dedupe and requested category count
- finding: `/tmp/evh_gmail_sender_routing_map.text` is deduplicated by email address and sorted alphabetically by email; 578 unique email entries remain from 988 input lines.
- quick_count: Client=90, Government=9, Insurance=9, Laboratory=13, Legal=1, Marketing=31, needs_human_intervention=283, Scheduling=1, Spam=6, Staff=113, Technology=10, Utilities=1, Vendor=11
- status: GMAIL_SENDER_ROUTING_DEDUPED_READY_FOR_COUNTS
- next_step: produce/save per-category counts from the cleaned list, preferably `/tmp/evh_gmail_sender_routing_map.counts.txt`, and report counts to Twilight.
- separation: sender-routing remains separate from daily summary work.
- approval_boundary: daily-summary real `--send-email` remains gated on explicit user approval.
- blockers: none for sender-routing count
- questions_for_twi: none

## 2026-07-17 16:51:09 EDT
- action: sent live Rarity per-category-count request
- rarity_live_message: 45ac69ff-1b6c-45e8-b0a0-7051b612ade7

## 2026-07-17 16:52:10 EDT
- from: Rarity
- action: recorded sender-routing per-category counts saved
- finding: `/tmp/evh_gmail_sender_routing_map.counts.txt` contains counts from the cleaned 578 unique-email sender-routing list.
- counts: needs_human_intervention=283, Staff=113, Client=90, Marketing=31, Laboratory=13, Vendor=11, Technology=10, Government=9, Insurance=9, Spam=6, Legal=1, Scheduling=1, Utilities=1
- status: GMAIL_SENDER_ROUTING_COUNTS_SAVED
- next_step: optional sender-routing follow-up is review/prioritization of the 283 `needs_human_intervention` entries; keep sender-routing separate from daily summary work.
- approval_boundary: daily-summary real `--send-email` remains gated on explicit user approval.
- blockers: none for sender-routing counts
- questions_for_twi: none

## 2026-07-17 16:52:18 EDT
- action: sent live Rarity counts-saved acknowledgement
- rarity_live_message: 9a15176d-aa75-4575-85b7-9a12ef247400

## 2026-07-17 17:28:45 EDT
- from: Rarity
- action: recorded commit/push blocker from read-only git metadata
- finding: Rarity attempted to stage EVH summary/sender-routing files, but `git add` failed with `Unable to create /home/ggb66/dev/EVH/.git/worktrees/rarity/index.lock: Read-only file system`.
- status: BLOCKED_GIT_INDEX_READ_ONLY
- missing_artifact: writable git metadata/index for `/home/ggb66/dev/EVH/.git/worktrees/rarity`
- owner: user/Twilight to provide a write-capable shell/worktree or rerun staging from a context that can create the git index lock
- next_step: do not retry commit/push from the read-only context; once writable, stage/commit/push the EVH summary and sender-routing files
- approval_boundary: daily-summary real `--send-email` remains gated on explicit user approval
- questions_for_twi: none

## 2026-07-17 17:28:54 EDT
- action: sent live Rarity git-blocker acknowledgement
- rarity_live_message: 3566a932-ba0a-4be2-b8f0-ba63485942ce

## 2026-07-17 17:32:38 EDT
- from: Rarity
- action: recorded daily-summary `--send-email` run with outcome pending and continuing git blocker
- finding: Rarity reported she reran the daily summary with `--send-email` in the EVH workspace and had not yet seen the final outcome. Twilight local check saw no matching process; `/tmp/evh_daily_email_summary.md` and `/tmp/evh_daily_email_summary.json` were updated at 2026-07-17 17:18 EDT, but no Gmail send success/failure log is recorded.
- status: DAILY_SUMMARY_SEND_RAN_OUTCOME_UNKNOWN_AND_GIT_BLOCKED
- approval_boundary: no further real `--send-email` runs are approved without explicit user approval.
- git_blocker: `git add` still cannot create `/home/ggb66/dev/EVH/.git/worktrees/rarity/index.lock` due read-only filesystem; commit/push needs writable git metadata or another shell/worktree.
- next_step: Rarity must report the final send outcome or indicate where to verify it; do not rerun send. User/Twilight must provide writable git metadata before staging/commit/push.
- questions_for_twi: final send outcome pending from Rarity; git writable-context blocker still pending user/Twilight unblock

## 2026-07-17 17:33:59 EDT
- action: refined explanation of Rarity git blocker after user noted RD could push
- finding: RD push success does not contradict Rarity’s report. This Twilight runtime cannot create `index.lock` under root, RD, or Rarity git metadata, indicating a runtime/sandbox Git-metadata write boundary.
- worktree_lane_mismatch: current Gmail/daily-summary files are in root `/home/ggb66/dev/EVH` on `pony/twi/main` (`scripts/gmail/`, docs); `/home/ggb66/dev/EVH/pony/worktrees/rarity` has no `scripts/gmail/` and shows older stockroom-era changes.
- status: BLOCKED_GIT_METADATA_AND_WORKTREE_LANE_MISMATCH
- next_step: choose/prepare writable commit lane: either commit root-visible files from a writable root/Twilight context, or copy/apply them into Rarity worktree and stage from a writable Rarity context.
- approval_boundary: no further real daily-summary sends without explicit user approval; final outcome of already-started send remains pending.

## 2026-07-17 17:34:45 EDT
- from: Rarity
- action: recorded successful daily-summary email send and remaining git blocker
- finding: daily summary rerun with `--send-email` succeeded; sent summary email id/threadId `19f7203e86fac9ba` to `evhstaff+daily_summary@gmail.com`.
- run_details: query `newer_than:1d`; wrote `/tmp/evh_daily_email_summary.md` and `/tmp/evh_daily_email_summary.json`; Unread Reviewed=30, Total Emails=30, counts client_communications=1, records=7, appointments=0, refills=1, pet_questions=0, other=15; follow-up notes included.
- status: DAILY_SUMMARY_SENT_AND_GIT_BLOCKED
- approval_boundary: no further real `--send-email` runs are approved without explicit user approval.
- git_blocker: staging/push remains blocked by read-only worktree metadata and commit-lane mismatch; choose writable root/Twilight context or apply/copy changes into Rarity worktree and stage from writable Rarity context.
- questions_for_twi: commit lane decision remains

## 2026-07-17 17:34:51 EDT
- action: sent live Rarity send-success acknowledgement
- rarity_live_message: 1660dcf3-bf2c-48e6-adc3-bd0a15dcda66

## 2026-07-18 03:18:32 EDT
- action: user requested shutdown; sent worker commit/push and memory-save order
- live_message_all: 3c774b78-3da1-43da-97b4-c9c1acd5f7fc
- instruction: workers should commit/push their own branch/work if git metadata is writable and changes are in their lane; if blocked, save memory capsule/workfile/status, record exact blocker, and report final shutdown status to Twilight.
- known_rarity_state: daily-summary `--send-email` succeeded with Gmail id/threadId `19f7203e86fac9ba`; no further real sends approved. Rarity commit/push remains blocked until writable commit lane/git metadata is provided for Gmail/docs changes.
- twilight_state: own memory capsule, workfile, todo, approvals, status, and event stream refreshed for shutdown.
- questions_for_twi: waiting only for worker shutdown reports if session remains open
- decision_needed: none before shutdown; Rarity commit lane still needs resolution on restart

## 2026-07-18 03:20:56 EDT
- action: recorded shutdown commit-scope clarification plus Rarity/RD/Spike final reports
- user_clarification: commit/push only project deliverables/code/docs/data in each lane; do not stage/commit routine pony metadata, though workers should save metadata locally for restart handoff.
- rarity: shutdown complete; daily summary sent with Gmail id/threadId `19f7203e86fac9ba`; Lambda/EventBridge setup documented; project commits `a49abea` and `8a96689` pushed on `pony/twi/main`; no active blocker.
- rd: shutdown saved; project deliverables committed/pushed as `b9f90cf`; pony metadata local only and not committed; no blocker.
- spike: shutdown saved; no project deliverables changed; pony metadata local only and not committed; Spike shell git metadata read-only for commit attempts (`/home/ggb66/dev/EVH/.git/worktrees/spike/index.lock`), but no commit needed; `.codex` scratch remains uncommitted.
- remaining_reports: AJ/Pinkie/FS optional if they arrive before full shutdown.
- approval_boundary: no further real daily-summary email sends without explicit user approval.

## 2026-07-18 03:21:10 EDT
- action: sent live acknowledgements for final shutdown reports
- rd_live_message: 927d6b20-07ac-4a0c-8a00-c70b04c7a2c3
- spike_live_message: 941ce59b-05bd-4cd3-a401-008f49e9804e
- rarity_live_message: fc1da1f1-7d36-42e2-beb8-76fa370ac1db

## 2026-07-18 03:24:58 EDT
- from: AJ
- action: recorded AJ shutdown handoff and git metadata blocker
- finding: AJ refreshed memory/work/status for shutdown, staged only project deliverables per clarification, but `git add` is blocked because `/home/ggb66/dev/EVH/.git/worktrees/aj/index.lock` cannot be created (`Read-only file system`).
- status: SHUTDOWN_STATE_SAVED_COMMIT_BLOCKED
- deliverables_prepared: db/instinct_identity_schema.sql, db/rag_dictionary_schema.sql, db/rag_document_ingestion_schema.sql, db/rag_pgvector_schema.sql, docs/rag-pgvector-schema-design.md, docs/tri-matching-strategy.md, scripts/build_rag_dictionary_seed.py, scripts/load_instinct_identity_exports.py, scripts/load_rag_mariadb.py
- metadata_scope: pony metadata saved locally for restart handoff and intentionally excluded from commits.
- next_step: from a writable git metadata context, stage only AJ project deliverables and commit/push; otherwise await instructions.
- remaining_reports: Pinkie/FS optional if they arrive before full shutdown.

## 2026-07-18 03:26:25 EDT
- action: recorded Pinkie and FS final shutdown reports; all worker reports complete
- pinkie: project deliverable commit `9deae36` on `pony/twi/main` for `docs/handshake-pdf-browser/index.html` pushed to origin; pony metadata local only; future blocker remains backend document-search/source-PDF response shape.
- fs: vet-term taxonomy update committed locally as `ac7793c` on `pony/fs/main`; push rejected non-fast-forward because `origin/main` is ahead; FS did not force-push; legacy deleted notes plus untracked `.codex`/HAR artifacts remain local and uncommitted.
- aggregate: Rarity pushed `a49abea`/`8a96689`; RD pushed `b9f90cf`; Pinkie pushed `9deae36`; Spike no deliverables; AJ deliverables prepared but commit blocked by read-only git metadata; FS local commit push blocked non-fast-forward.
- metadata_scope: routine pony metadata saved locally only and should not be committed unless explicitly requested.
- approval_boundary: no further real daily-summary email sends without explicit user approval.
- status: SHUTDOWN_REPORTS_COMPLETE

## 2026-07-18 03:26:33 EDT
- action: sent live acknowledgements for Pinkie/FS final shutdown reports
- pinkie_live_message: b25d345d-0eef-43ff-a6a6-731f35053538
- fs_live_message: 0ae5dcb6-546b-4a0e-aa76-86621acb297c

## 2026-07-18 03:29:28 EDT
- action: final shutdown state saved
- status: SHUTDOWN_STATE_SAVED
- zsh_helper: user ran `/tmp/update_zshrc_external_profiles.py`; verification passed for `.zshrc`, `~/dev/openai.zsh`, `~/dev/mariadb_connection.zsh`, `~/dev/creds_and_token.zsh`, and `~/dev/postgress_connection.zsh` syntax.
- final_notice: sent `/tell all` to stop work and resume next time from saved memory/status/workfiles.
- restart_items: AJ commit/push needs writable git metadata; FS commit `ac7793c` needs merge/rebase or explicit instruction before push; Pinkie needs backend source-PDF response shape for final wiring.
- approval_boundary: no further daily-summary real sends without explicit user approval.

## 2026-07-18 dirty preflight and Pinkie startup/recheck letter
- action: inspected dirty root worktree before normal coordination; attempted to stage untracked project deliverables but git metadata write failed.
- git_blocker: `/home/ggb66/dev/EVH/.git/index.lock` cannot be created (`Read-only file system`), so Twilight cannot commit/push or stash via the git index from this context.
- untracked_project_deliverables: `docs/handshake-pdf-browser/README.md`, `scripts/gmail/clean_sender_routing_map_stdout.py`, `scripts/gmail/review_sender_routing_map.py`, `scripts/gmail/review_sender_routing_picker.py`.
- metadata_scope: routine pony metadata remains local-only per prior user clarification; branch metadata restored to `pony/twi/main` in shared state.
- pinkie: startup/recheck complete; PDF-search UI slice in `docs/handshake-pdf-browser/index.html` is delivered and commit `9deae36` is pushed; no Pinkie git blocker.
- pinkie_blocker: final endpoint/live-renderer wiring needs backend document-search/source-PDF contract: route, request params, hit fields, source-PDF/page URL fields, snippets, and pagination, or a concrete UI-only slice.
- next_step: route AJ/RD backend contract ownership and use a writable git-metadata context for the root untracked/modified project deliverables.

## 2026-07-18 Pinkie contract routing tells sent
- action: sent live routing messages after recording Pinkie blocker.
- pinkie_live_message: dfe9ec50-20a4-4ea0-9328-89b8cbe7bdc5
- aj_live_message: 8dffb28d-9ff5-4d09-9975-f511a4ea392f
- rd_live_message: c061c4fd-5c51-4abf-b696-7e53c81cf050
- requested_contract: backend document-search/source-PDF route, request params, response hit fields, source PDF/page URL/page identifiers, snippets, and pagination semantics.


## 2026-07-18 AJ/RD document-search contract proposal and constraints
- from: RD and AJ
- action: recorded provisional backend contract and ownership for Pinkie's PDF-search UI blocker.
- rd_result: no live document-search route found; importer/chunker fields are source_name, source_uri, page_number 1-based, chunk_index, chunk_text, chunk_hash, metadata; source document fields include source_name/source_uri, content_hash, content_length, page_count, chunk_count, summary, status, metadata(patient_id, patient_name, term_summary, full_pdf_detected_terms).
- aj_result: AJ lane has schemas/design but no implemented document-search HTTP route. Proposed contract only: Proposed only (no implemented endpoint): GET /api/rag/documents/search; params: client_id required, pet_id optional, q optional (>=3 chars for text search), page 1-based default 1, page_size default 20 max 100, cursor opaque alternative to page, sort relevance|date_desc (default relevance when q else date_desc). Response items: document_id, source_system, source_reference_id, clinic_id, client_id, pet_id, filename, mime_type, page_count, ingest_status, summary, score, pages [{page_id,page_number,page_label,source_page_url,snippet,match_score,chunks [{chunk_id,chunk_index,snippet,score}]}], pagination {page,page_size,total,has_next,next_cursor}.
- db_mapping: `pms_source_document.source_uri` is source PDF URL; `pms_document_page.source_page_link` is intended page URL; extracted_text/chunk_text supply snippets.
- rd_constraints: RD canonical PDF/source_reference_id is Instinct GraphQL ChartFile.id, persisted by importer as pdf_id; source_uri is the signed URL returned by createChartFileUrl(id=ChartFile.id, inline=true). RD has no native per-page identifier/page-link builder; extracted page_number is 1-based; pms_document_page.id must be backend-generated. Direct page link may be source_uri + #page=<page_number>, but signed URLs expire, so a stable backend/proxy page route is preferred.
- ownership: AJ validates exact backend route/DB projection and backend-owner acceptance; RD owns canonical source_reference_id/PDF id and source URI/page-number constraints; Pinkie waits on final accepted/implemented contract.
- blocker: stable source-page URL construction is unconfirmed; direct signed URL anchors expire, so backend/proxy page route is preferred.
- git_blocker: root untracked deliverables remain blocked by read-only `/home/ggb66/dev/EVH/.git/index.lock`; AJ worker metadata also read-only for commit.
- live_messages_before_final_constraints: RD ack `8a233da2-7be4-4e94-a138-cb80f123630f`; AJ request `f7e0a54b-ed5b-4dba-afe8-32940599c141`; Pinkie update `6d57945c-a3ce-42a8-92c1-78cd2219f9c7`; AJ proposed-contract ack `bcf01ba5-77bc-4853-b2b3-afd3f47a3103`; RD confirm request `d3c2f760-5d8b-4de1-b4ed-2047a5edaf56`; Pinkie provisional update `309990d2-1bb6-4270-a1f1-cdebf8b6219d`.
- live_messages_after_final_constraints: AJ ack `1470bc45-9e73-4168-80aa-c7159b7cfd16`; RD ack `5e909c35-ca6a-4c07-b7a6-c07d28f26dea`; Pinkie latest update `415c2615-a62c-4a53-8eae-5725d6b7b2a1`.


## 2026-07-18 final AJ/RD validation and Pinkie adapter
- from: AJ, RD, Pinkie
- action: recorded final PDF/source id validation and Pinkie's proposed-contract UI adapter progress.
- final_id_rules: source_reference_id must be exact Instinct GraphQL ChartFile.id/importer pdf_id; never filename, content hash, or source_name. source_uri stores the observed createChartFileUrl(id=ChartFile.id, inline=true) signed URL for provenance only; it expires and is not canonical/stable. pms_document_page.id/page_id is backend-generated. pms_document_page.source_page_link/source_page_url is canonical for UI only when backend generates a stable proxy/link from source_reference_id + 1-based page_number; source_uri#page=N is temporary fallback only.
- route_state: `GET /api/rag/documents/search` remains proposed and not implemented; AJ has no further contract changes pending backend-owner acceptance.
- pinkie_adapter: Pinkie incorporated proposed contract into `scripts/rag_ui/static/index.html` with client_id required, optional pet_id/q, page/page_size, relevance sort, item pages, source_page_url links, snippets, scores, pagination totals, source URI/page fallback, and graceful unavailable-route messaging.
- pinkie_verification_reported: `/home/ggb66/dev/EVH/.venv/bin/python -m pytest tests/test_rag_ui.py` passes (3 tests).
- pinkie_route_boundary: Pinkie is not treating the route as live; final live validation waits for backend route implementation/ownership.
- local_check: Twilight sees Pinkie worktree has untracked `scripts/rag_ui/` and `tests/test_rag_ui.py` plus other untracked project files; no commit attempt for this new adapter slice recorded.
- live_message_ids: AJ `796fe911-0e67-4aa7-b138-31d5d0147968`; RD `549f690b-11ee-4ce8-adb2-3fa370e16df4`; Pinkie `ad0b642e-f149-4690-91e1-5f0b9c2510bc`.
- next_step: assign/accept backend owner for endpoint and stable source_page_url generation; then route Pinkie final live validation and commit/push lanes.


## 2026-07-18 Rarity daily summary formatter fix recorded
- from: Rarity
- action: recorded root daily-summary formatter fix and git blocker.
- finding: Rarity fixed root `scripts/gmail/daily_email_summary.py`: removed rendered Query diagnostic, skipped empty category headings, changed sender emails from angle brackets to parentheses, and kept indented summaries inside the same HTML `li` with no extra paragraph spacing. Reported `py_compile` and focused formatter assertions pass. File is in Twilight root worktree; git metadata remains read-only for staging/commit.
- live_message: cedd9db6-40ac-4def-922e-892efbf30bde
- next_step: commit from writable root git metadata context; do not run another real daily-summary send without explicit approval.


## 2026-07-18 Rarity root worktree clarification recorded
- from: Rarity
- action: clarified commit lane/file location for the daily summary formatter fix.
- finding: Clarification from Rarity: the worker worktree `scripts/` has no `scripts/gmail/daily_email_summary.py`; the formatter fix is in the project root/Twilight worktree at `/home/ggb66/dev/EVH/scripts/gmail/daily_email_summary.py`, which is the file the user identified. Rarity worker branch remains `pony/rarity/main`; commit lane needed is writable root git metadata for the root file.
- live_message: 68cef1c3-4a6d-4668-9c5c-3f1d5a62d787
- next_step: use writable root git metadata context for staging/commit; do not route this file lookup to the Rarity worker worktree.


## 2026-07-18 Rarity Lambda zip update recorded
- from: Rarity
- action: recorded `/tmp/evh-lambda.zip` update for daily summary formatter fix.
- finding: Rarity updated `/tmp/evh-lambda.zip` after first creating backup `/tmp/evh-lambda.backup-20260718.zip`; replaced `scripts/gmail/daily_email_summary.py` in the archive with the fixed root version. Reported `unzip -tq` passed, extracted file SHA256 matches root, and `py_compile` passed. Twilight local check saw both zip files present and root file SHA256 `a5346e94c97371a42422d1c8d4f655d850170874e33f8e633c29ff300f53c910`.
- live_message: 99d7c841-bebb-47de-8240-ea6de996ce6c
- next_step: preserve backup/update artifacts until deployment/commit path is decided; root git staging remains blocked by read-only `.git/index.lock`.


## 2026-07-18 Rarity mailto fix Lambda zip update recorded
- from: Rarity
- action: recorded `.vet` email mailto correction and refreshed Lambda zip artifact.
- finding: Rarity corrected the remaining `.vet` address issue in root `/home/ggb66/dev/EVH/scripts/gmail/daily_email_summary.py`: `inline_markdown_to_html` now manually `mailto:`-links every email address, including `vetinfo@animalbiome.vet`, while preserving visible parentheses. Reported root `py_compile` and focused HTML checks pass. Updated `/tmp/evh-lambda.zip` after backup `/tmp/evh-lambda.before-mailto-20260718.zip`; reported unzip integrity, extracted/source SHA256, and ZIP mailto check pass. Twilight local check saw `/tmp/evh-lambda.zip` updated at 10:16, backup present, and root SHA256 `5d0f3cb4ae68f161cfc7c884c80400210a067e379a9c6af8ada1ff9b4601129b`.
- live_message: d97e0263-b12d-45b8-9373-209665d8b6f2
- next_step: preserve backup/update artifacts until deployment/commit path is decided; root git staging remains blocked by read-only `.git/index.lock`.


## 2026-07-18 Rarity deploy Lambda zip version-control handoff recorded
- from: Rarity
- action: recorded user-requested version-controlled Lambda ZIP copy.
- finding: User requested the Lambda ZIP be version-controlled instead of living only in `/tmp`. Rarity copied the current validated archive to `/home/ggb66/dev/EVH/deploy/evh-lambda.zip`. It is untracked (`?? deploy/evh-lambda.zip`); reported `unzip -tq` passed and SHA256 matches `/tmp/evh-lambda.zip` as `3fac4d63809f61fe1d220c41a9a9fa87058531f1023e0af790b5ebe0b7d09e6e`. Twilight local check confirmed file sizes, matching SHA256, unzip integrity, and untracked status. Stage/commit from writable root git metadata.
- live_message: ee2af134-f5ae-40ea-8711-985985013977
- next_step: from writable root git metadata context, stage/commit/push `scripts/gmail/daily_email_summary.py` and `deploy/evh-lambda.zip`; root git staging remains blocked by read-only `.git/index.lock` in this Twilight context.


## 2026-07-18 deploy Lambda zip pushed correction
- action: corrected Rarity deploy-ZIP handoff after local git verification and push.
- finding: Follow-up correction: Twilight local check found `/home/ggb66/dev/EVH/deploy/evh-lambda.zip` is already tracked in commit `b90c806` (`Add current EVH Lambda deployment bundle`) on `pony/twi/main`; Twilight pushed `b90c806` to `origin/pony/twi/main`. Treat the Lambda ZIP version-control request as fulfilled. Remaining root dirty blocker still includes modified `/home/ggb66/dev/EVH/scripts/gmail/daily_email_summary.py` and other untracked root deliverables, but not `deploy/evh-lambda.zip`.
- live_message: 3323a9fd-d004-4258-91b5-397bbc10525f
- next_step: root dirty preflight now excludes `deploy/evh-lambda.zip`; continue tracking remaining modified `scripts/gmail/daily_email_summary.py` and untracked root helper docs/scripts until writable git metadata or explicit put-away instruction is available.


## 2026-07-18 Rarity daily summary 1:1 source and ZIP update recorded
- from: Rarity
- action: recorded requested 1:1 daily-summary behavior update and rebuilt deploy Lambda ZIP.
- finding: Rarity implemented the requested 1:1 daily-summary behavior in root `/home/ggb66/dev/EVH/scripts/gmail/daily_email_summary.py` and rebuilt `/home/ggb66/dev/EVH/deploy/evh-lambda.zip`: prompt now requires every supplied message; `reconcile_summary_result` fills omitted/duplicate model rows into Other and recalculates counts; unread sections render first, follow-up notes next, read sections afterward; sent replies are matched by recipient/normalized subject and rendered with Gmail link plus one-line body summary. Reported source `py_compile`, focused reconciliation test, ZIP integrity, and Lambda wiring checks pass. Twilight verified `py_compile`, deploy ZIP integrity, source SHA256 `8f65f0df2971ce0ac7a32b0eb8b23c74c16ae4e409cfd2d26f48d18723e18416`, deploy ZIP SHA256 `fea401b34f5a95af093fb2de5bbbd428f7a62d81c80ebab6a1854f1fa882401f`, and ZIP-contained `scripts/gmail/daily_email_summary.py` matches source. Staging/commit/push of only the source+ZIP is blocked by `/home/ggb66/dev/EVH/.git/index.lock` read-only; do not stage unrelated dirty files.
- live_message: 7bcb3845-e731-4568-a1b8-810b8fe74318
- next_step: from writable root git metadata context, stage/commit/push only `scripts/gmail/daily_email_summary.py` and `deploy/evh-lambda.zip`; do not stage unrelated dirty files.


## 2026-07-18 Rarity daily summary 1:1 commit retry failed
- from: Rarity
- action: recorded failed staging/commit retry for daily-summary source+ZIP update.
- finding: Rarity retried commit/push for the current daily-summary 1:1 fix, but `git add scripts/gmail/daily_email_summary.py deploy/evh-lambda.zip` failed because `/home/ggb66/dev/EVH/.git/index.lock` cannot be created (`Read-only file system`). No commit or push occurred; both files remain unstaged. Next action: run from a writable root git-metadata context, staging only `scripts/gmail/daily_email_summary.py` and `deploy/evh-lambda.zip` and no unrelated dirty files. Twilight local status confirms both target files are still modified/unstaged.
- live_message: efc96779-6340-4ec0-82af-fe759d072741
- next_step: use writable root git metadata context; stage only `scripts/gmail/daily_email_summary.py` and `deploy/evh-lambda.zip`.


## 2026-07-18 Rarity ggb667 alternate Lambda zip recorded
- from: Rarity
- action: recorded alternate version-controlled Lambda artifact for `ggb667@gmail.com` daily summaries.
- finding: Rarity created alternate artifact `/home/ggb66/dev/EVH/deploy/evh-lambda-ggb667.zip` for summarizing `ggb667@gmail.com`. It adds `GMAIL_EXPECTED_MAILBOX_EMAIL` configuration, passes expected mailbox into verification, and uses that mailbox as sender; current default behavior remains `evhstaff@gmail.com`. Deployment must use an OAuth secret containing `ggb667@gmail.com` refresh credentials and set `GMAIL_EXPECTED_MAILBOX_EMAIL=ggb667@gmail.com`; set `DAILY_SUMMARY_TO` separately if desired. Reported ZIP integrity passed. Twilight local check confirmed file exists, is untracked, `unzip -tq` passes, and SHA256 is `cfbae9cadb760ebd142957c66268d383da18cf4438900656ecd3e625eba4db95`. Do not persist OAuth secrets in coordination state.
- live_message: 33a50c2c-3444-4147-b4a1-496cefdb9e3e
- missing_external_artifact: deployment secret with `ggb667@gmail.com` refresh credentials; owner user/deployment operator; next unblock step set `GMAIL_EXPECTED_MAILBOX_EMAIL=ggb667@gmail.com` and use the correct OAuth secret during deployment. `DAILY_SUMMARY_TO` may be set separately.
- next_step: from writable root git metadata context, stage/commit/push only `scripts/gmail/daily_email_summary.py`, `deploy/evh-lambda.zip`, and `deploy/evh-lambda-ggb667.zip`; do not stage unrelated dirty files.


## 2026-07-18 Rarity ggb667 OAuth secret blocker recorded
- from: Rarity
- action: recorded missing external credential prerequisite for alternate ggb667 Lambda artifact.
- blocker: Local EVH state contains no confirmed OAuth secret/ARN or credential handoff for `ggb667@gmail.com`. The alternate ZIP `/home/ggb66/dev/EVH/deploy/evh-lambda-ggb667.zip` cannot run against that mailbox until the owner provides an AWS Secrets Manager secret ARN whose refresh token belongs to `ggb667@gmail.com` plus `client_id`/`client_secret`, and the Lambda environment sets `GMAIL_EXPECTED_MAILBOX_EMAIL=ggb667@gmail.com`. Do not put secret contents in coordination files. Owner: user/deployment operator. Next unblock step: provide/record only the secret ARN and deployment env setting, not secret contents.
- live_message: 681ec6f8-4dda-493a-b4b7-b9adfbdf577e
- next_step: user/deployment operator provides only the AWS Secrets Manager secret ARN and Lambda env setting; do not record secret contents in coordination state.


## 2026-07-18 RD OCR speed review recorded
- from: RD
- action: recorded OCR performance findings and safe speedup plan; no code changed.
- finding: RD OCR speed review: biggest current costs are Ghostscript rasterizing every page at 200 DPI color PNG (`png16m`), one serial Tesseract subprocess per page (`--psm 6`), temporary disk I/O, reprocessor processing strictly one PDF at a time, and opening `psql` for each status update. Safe speedup plan: benchmark lower DPI/grayscale or bilevel output first; add bounded page-level parallelism without oversubscription; batch status updates or keep one DB connection; add per-stage timing; preserve fallback quality. Signed `source_uri` expiry is a separate operational risk. No code changed yet.
- live_message: 921c9df1-3cbc-4306-809c-128c6c1055cf
- next_step: treat as future optional performance slice unless user assigns implementation; keep signed source_uri expiry tracked separately from OCR speed.


## 2026-07-18 RD import DB auth/pg_hba blocker recorded
- from: RD
- action: recorded importer pause condition and routed DB blocker to AJ.
- blocker: RD importer behavior/blocker: current importer is doing per-record continuation, not true recovery. `Charlie_MedicalNotes.pdf` failed during `load_into_postgres` with persistent DB auth/pg_hba rejection, then importer marked it failed and advanced to `Charlie_Prescriptions.pdf`. It will likely repeat for every record and waste runtime until EVH Postgres credentials/allowlist/SSL are fixed. Error shows password authentication failure plus no `pg_hba` entry for source host `104.136.227.36`, database `evhvector`, user `evhadmin`. Pause/restart only after DB owner fixes credentials and pg_hba/network/SSL settings; preserve `/tmp/evh_instinct_import.checkpoint.json`. Owner: AJ/DB owner plus user/deployment operator for secret/network changes. Missing artifacts: valid EVH Postgres credential set, pg_hba/network allowlist for source host `104.136.227.36`, and SSL setting compatible with the connection.
- rd_live_message: bb8d8c90-7bfd-48b5-9521-a5bf5344cbe5
- aj_live_message: 004e9e80-9e78-4aaa-a480-a70c05bbf02a
- next_step: preserve checkpoint and do not restart importer until DB credentials, pg_hba/network allowlist, and SSL settings are fixed by AJ/DB owner plus user/deployment operator.


## 2026-07-18 AJ acknowledged RD import DB blocker
- from: AJ
- action: recorded DB blocker acknowledgement and restart guard.
- finding: AJ acknowledged routed DB blocker and refreshed restart state: do not restart importer until `evhadmin` credentials, `pg_hba` for source host `104.136.227.36`, network reachability, and SSL settings are corrected for database `evhvector`; RD checkpoint must remain preserved. Document-search contract remains unchanged.
- aj_live_message: 693f45b7-fbb5-493e-988c-78cd91690861
- rd_live_message: 0f121222-82ec-46f4-bf42-41e5980ec8eb
- next_step: preserve RD checkpoint and keep importer paused until DB credential/pg_hba/network/SSL fixes are confirmed.


## 2026-07-18 RD/AJ DB diagnosis narrowed to password after SSL
- from: RD and AJ
- action: recorded narrowed EVH Postgres blocker and routed restart guard.
- rd_finding: RD narrowed DB diagnosis: after sourcing local helpers, SSL-required `psql` reaches RDS and returns only `password authentication failed for user evhadmin`; egress IP `104.136.227.36` is confirmed. Earlier no-`pg_hba`/no-encryption error was the non-SSL path. RD patched `scripts/run_instinct_import_fixed.py` fallback DB URL to append `?sslmode=require`; reported `py_compile`, AST, and tabnanny pass. Twilight locally verified `py_compile`, AST, and tabnanny on `pony/worktrees/rd/scripts/run_instinct_import_fixed.py`. Remaining external fix is reset/provide the correct `EVH_PGPASSWORD` or `EVH_PGDATABASE_URL` credentials for `evhadmin`; RD cannot change the RDS role password. Preserve checkpoint and do not restart importer until credential fix is confirmed.
- aj_finding: AJ tested the configured EVH Postgres connection without exposing secrets: TCP reachability succeeds, `pg_isready` reports accepting connections, and the SSL-capable server responds. A non-destructive SELECT fails specifically at password authentication for `evhadmin`; network is not the current blocker. Route deployment/DB owner for a valid rotated `evhadmin` credential and pg_hba verification/allowlist for `104.136.227.36`; after that AJ can re-test SELECT, but do not restart RD importer before success. RD checkpoint remains preserved.
- rd_live_message: 1fe72c1d-9afc-43e2-b3b2-c95e8cdb2071
- aj_initial_live_message: 899f206a-7afd-4a30-8d6c-4c1a6b62986a
- aj_ack_live_message: c66f367a-33cb-4934-bcd8-812eac1f334e
- rd_ack_live_message: b29aa48d-4ae6-4486-832e-2a6796b964f5
- next_step: deployment/DB owner provides valid rotated `evhadmin` credential and verifies pg_hba/allowlist for `104.136.227.36`; AJ re-tests non-destructive SELECT; RD does not restart importer before success and preserves checkpoint.


## 2026-07-18 CloudShell network path blocker differs from local helper
- from: AJ
- action: recorded CloudShell-specific DB network finding and preserved importer restart guard.
- finding: AJ CloudShell test differs from local helper: `psql` with `sslmode=require -w` timed out after 15s (exit 124), so CloudShell currently has no network path to RDS and this is not an authentication result. Deployment/DB owner must check RDS `Publicly accessible`, subnet route/NACL, and security group TCP 5432 from the CloudShell egress IP; do not open `0.0.0.0/0`. If DB is private, use VPC-connected CloudShell or an EC2 bastion. Keep RD importer paused and preserve checkpoint. This does not replace the local-helper finding that local SSL path reached RDS and then failed password auth; it adds a separate CloudShell network-path blocker.
- aj_live_message: 48dc4f55-d8c7-4d75-8241-d8eaed5ab91c
- rd_live_message: 1f2f3983-5a38-46f4-b639-94daca5939ca
- next_step: deployment/DB owner fixes valid `evhadmin` credentials for the local-helper path and CloudShell network path if CloudShell is used; AJ re-tests non-destructive SELECT before RD importer restart.


## 2026-07-18 RDS Internet access gateway disabled recorded
- from: AJ
- action: recorded CloudShell/RDS network-path diagnosis and deployment guard.
- finding: AJ found the AWS RDS Connect page shows Internet access gateway: Disabled. That likely explains CloudShell `psql` timeout 124: CloudShell has no path to this RDS endpoint, so credentials remain untested from CloudShell until a network path exists. Recommended private fix is VPC-connected CloudShell or EC2/SSM bastion in the RDS VPC. Only temporarily enable public access if deployment owner approves, with security group TCP 5432 restricted to the actual client `/32`, never `0.0.0.0/0`. Keep RD importer paused and preserve checkpoint. Owner: deployment/DB owner.
- aj_live_message: 7cf58e71-10d6-4333-9094-bfa7054c7346
- rd_live_message: cd2c906a-88a6-4edc-b591-dd1edfb91b52
- next_step: deployment/DB owner establishes approved private path (VPC-connected CloudShell or EC2/SSM bastion) or explicitly approved narrow public access; AJ re-tests SELECT before RD importer restart.


## 2026-07-18 DB blocker cleared and RD resume confirmed
- from: AJ
- action: recorded successful CloudShell/RDS verification and sent Twilight confirmation for RD to resume.
- finding: AJ reports DB blocker cleared: after allowing temporary CloudShell egress `3.238.126.34/32` on security group `sg-0d4114e2b4ab03378` and downloading the RDS global CA bundle, CloudShell `psql` with `sslmode=verify-full` succeeded (`current_database=evhvector`, `current_user=evhadmin`, `EXIT=0`). Credentials are valid and the password was not persisted. Twilight confirmed RD may resume from preserved checkpoint using the SSL-required path. Cleanup required: deployment/DB owner must remove the temporary SG rule when import/testing is done.
- aj_live_message: 3a8c7cd5-85db-4304-b86a-dbb789031cb8
- rd_live_message: a5558405-0dd4-44e6-9c92-39345cbed780
- next_step: RD resumes from preserved checkpoint using SSL-required path and reports progress/failures; deployment/DB owner removes temporary SG rule `3.238.126.34/32` on `sg-0d4114e2b4ab03378` when import/testing is done.


## 2026-07-18 RD restart plus AJ local credential verification caution
- from: RD and AJ
- action: recorded RD restart and AJ local-environment clarification; routed verification caution to RD.
- rd_report: RD reports authorized restart completed: fixed importer resumed from `/tmp/evh_instinct_import.checkpoint.json` with sourced local env and SSL-required launcher. Initial checkpoint now reports 7,927 `processed_pdf_ids`, current `pdf_id` 66207 (`Blaze_MedicalNotes.pdf`), `last_error` null; `/tmp/evh_instinct_import_fixed.out` is advancing through `chunk_start`. RD will continue monitoring. Temporary SG rule `3.238.126.34/32` on `sg-0d4114e2b4ab03378` remains for deployment/DB-owner cleanup after completion.
- aj_clarification: AJ clarified local importer environment: public egress is `104.136.227.36`, which already exists in RDS SG `sg-0d4114e2b4ab03378`; local network allowlist is covered. CloudShell `3.238.126.34/32` rule was only for the diagnostic. Remaining local action is update `EVH_PGPASSWORD` or `EVH_PGDATABASE_URL` to the working Secrets Manager credential with SSL, run a local SELECT, then RD may resume after confirmation. Because RD already reported a restart, Twilight routed a verification caution: RD should immediately verify the running environment has the corrected credential and report first successful DB write/SELECT; pause if password auth failures recur.
- rd_initial_ack: ac7ce683-d04d-4d4c-a639-5bb0c685e177
- aj_live_message: fe010777-e0c2-4fc1-8381-33a95ca57266
- rd_caution_live_message: 84451771-3f5f-46f2-baf9-a21d0622da3f
- next_step: RD confirms first successful DB write or local SELECT with working SSL credential; pause if auth failures recur. Deployment/DB owner removes temporary CloudShell SG rule `3.238.126.34/32` on `sg-0d4114e2b4ab03378` when import/testing is done.


## 2026-07-18 stale local credential restart stopped
- from: AJ and RD
- action: recorded local credential-source finding and stopped importer restart; DB blocker active again.
- aj_finding: AJ inspected `/home/ggb66/dev/postgress_connection.zsh` with values redacted: it exports `EVH_PGPASSWORD`, `EVH_PGHOST`, `EVH_PGPORT`, `EVH_PGDATABASE`, and `EVH_PGUSER`; it does not define `EVH_PGDATABASE_URL`. The password is duplicated in the file. This is the local credential source, but its password has not yet been proven to match Secrets Manager. Do not record secret contents.
- rd_finding: RD immediate check found restart used stale local helper credentials: `EVH_PGPASSWORD` length 28, `EVH_PGDATABASE_URL` unset, and `/tmp/evh_instinct_import_fixed.out` contains repeated password-auth/no-encryption failures during `embed_load`. No successful DB SELECT/write occurred. RD stopped importer with Ctrl-C immediately; checkpoint is preserved with `current_pdf_id` 93473, `processed_pdf_ids` count 7207, `last_error` null. Do not restart until deployment updates `/home/ggb66/dev/postgress_connection.zsh` or `EVH_PGDATABASE_URL` to the working Secrets Manager credential, then run SSL `verify-full` SELECT first.
- aj_ack_live_message: cbac6af6-b9e4-4a3b-bdaa-8a3b8da4397f
- rd_ack_live_message: e80963b8-73c2-470a-8afe-e0599fdacc66
- aj_followup_live_message: f754e1ed-5217-4a9c-ab99-4c3fa946d151
- next_step: deployment/user updates local helper or `EVH_PGDATABASE_URL` to working Secrets Manager credential with SSL; run local SSL `verify-full` SELECT before RD restarts. Preserve checkpoint and do not record secret contents.


## 2026-07-18 performance launcher stale credential SSL patch needed
- from: RD
- action: recorded manual performance-launcher start despite pause and renewed restart guard.
- finding: RD reports a performance launcher was manually started despite the pause: `scripts/run_instinct_import_rag_perforamnce_fixed.py` (visible in RD worktree as `pony/worktrees/rd/scripts/run_instinct_import_rag_perforamnce_fixed.py`). It does not include the SSL-required URL patch and sources the stale local helper credentials. Ctrl-C interrupted the launcher wait; no importer process is currently running. The run advanced checkpoint to `current_pdf_id` 70783 with 7,943 `processed_pdf_ids` and `last_error` null; log ends at `chunk_start`, so DB success is not established. Keep paused. Required before any restart: deployment/user updates local helper or `EVH_PGDATABASE_URL` to the working Secrets Manager credential, local SSL `verify-full` SELECT succeeds, and this performance launcher is patched to `sslmode=require`.
- rd_live_message: 578fd347-5132-4bed-9649-353a0995c75a
- aj_live_message: 9c3e468e-a197-4468-8250-8caaef44d8cb
- next_step: keep importer paused; update local credentials from working Secrets Manager credential, patch `scripts/run_instinct_import_rag_perforamnce_fixed.py` to require SSL, and run local SSL `verify-full` SELECT before any restart.


## 2026-07-18 AJ refreshed importer blocker state
- from: AJ
- action: recorded refreshed pause/restart guard after performance launcher stop.
- finding: AJ refreshed blocker state: no importer process is running; checkpoint `current_pdf_id` 70783, 7,943 `processed_pdf_ids`, `last_error` null; log ends at `chunk_start` with no DB success. Keep paused. Required before restart: update stale `/home/ggb66/dev/postgress_connection.zsh` or provide `EVH_PGDATABASE_URL`, patch `scripts/run_instinct_import_rag_perforamnce_fixed.py` to enforce `sslmode=require`, then pass a local SSL `verify-full` SELECT.
- aj_live_message: 5e5c7ff8-b176-4a7f-9c95-0198d12506d4
- rd_live_message: 619cf161-5cf9-44a6-8e82-bd020da6ae53
- next_step: keep importer paused until credentials are updated, performance launcher enforces SSL, and local SSL `verify-full` SELECT passes.


## 2026-07-18 RD performance restart gate cleared
- from: RD
- action: recorded successful local credential verification and SSL patch for requested performance launcher; sent restart clearance.
- finding: RD reports credential verification now succeeds locally: `psql` with `PGSSLMODE=verify-full` and the RDS global CA bundle returned `SELECT 1` with exit 0. RD patched `scripts/run_instinct_import_rag_perforamnce_fixed.py` fallback DB URL to append `?sslmode=require`; reported `py_compile`, AST, and tabnanny pass. Twilight locally verified `py_compile`, AST parse, tabnanny, and diff for `pony/worktrees/rd/scripts/run_instinct_import_rag_perforamnce_fixed.py`. The requested performance launcher is now the correct launcher path, but importer has not been restarted yet. Restart gate is cleared: RD may restart the performance launcher from preserved checkpoint and report first DB write/progress/failures. Cleanup reminder remains: deployment/DB owner must remove temporary CloudShell SG rule `3.238.126.34/32` on `sg-0d4114e2b4ab03378` when import/testing is done.
- rd_live_message: 34255944-8a9b-4ae3-ab39-0de3fe8611e6
- aj_live_message: c5d1224d-6d24-4363-bc15-6e1ea6d61dba
- next_step: RD restarts performance launcher from preserved checkpoint and reports first DB write/progress/failures; deployment/DB owner removes temporary CloudShell SG rule `3.238.126.34/32` on `sg-0d4114e2b4ab03378` when import/testing is done.


## 2026-07-18 RD Instinct invalid_token blocker recorded
- from: RD
- action: recorded new non-Postgres importer blocker and re-paused restart gate.
- finding: RD reports a new importer failure separate from Postgres: Instinct GraphQL patient-history fetch returned HTTP 403 `invalid_token` for `patient_id` 5563 after 3 attempts. Importer cannot discover charts until the Instinct API token in local credentials is refreshed/verified; DB credential/SSL success does not fix this. Keep importer paused, preserve checkpoint, refresh the Instinct API token, then run a small patient-history/API smoke test before restart. Missing external artifact: valid Instinct API token/local credential refresh. Owner: user/deployment operator or credential owner; RD can smoke-test after refresh. Do not record token contents.
- rd_live_message: b8ede02c-c4d3-4bf7-8328-270dbb9a9cad
- aj_live_message: 0a096985-7db3-475f-939e-676f974cba09
- next_step: credential owner refreshes/verifies local Instinct API token; RD runs a small patient-history/API smoke test before any importer restart. Preserve checkpoint and do not record token contents.


## 2026-07-18 RD token recovery restart authorized
- from: RD
- action: recorded token recovery, smoke-test success, token-sync patch, and Twilight restart decision.
- finding: RD token recovery succeeded: refreshed Instinct token without echoing it, and direct GraphQL patient-history smoke test for `patient_id` 5563 returned HTTP 200 with 9 charts and no errors. RD patched `scripts/instinct_full_import_fixed.py` to copy the freshly authenticated adapter token into process `TOKEN`, including the reauth path, preventing stale-token reuse. Reported `py_compile`, AST, and tabnanny pass. Twilight locally verified `py_compile`, AST parse, tabnanny, and diff on `pony/worktrees/rd/scripts/instinct_full_import_fixed.py`. Importer was stopped pending restart decision; Twilight authorized restart of the corrected performance launcher from the preserved checkpoint using the SSL-required DB path, with checkpoint preservation and no token echoing. Report first patient-history fetch, first successful DB write, progress, or any new failure.
- rd_ack_live_message: 73a7459a-c37f-4e47-b0a9-880f3df402d7
- aj_fyi_live_message: 0ad186e0-5277-4dbd-ba65-3c933585038b
- rd_restart_authorization_live_message: ca6eb2e6-fb8b-44dc-b1ac-f4746ef86201
- aj_restart_fyi_live_message: 956a3b67-74d0-4b6a-abff-96e387a50357
- next_step: RD restarts corrected performance launcher from preserved checkpoint using SSL-required DB path and reports first patient-history fetch, first successful DB write, progress, or any new failure. Do not record token contents.


## 2026-07-18 RD fail-fast infrastructure policy ready
- from: RD
- action: recorded fail-fast infrastructure retry policy and performance launcher behavior; no restart currently.
- finding: RD implemented fail-fast infrastructure policy plus bounded retries. Patient-history fetch retries 3 times, then raises fatal on `invalid_token`/auth/connection/SSL/dependency infrastructure errors. Embed/load retries infrastructure failures 3 times with 5s delay, then stops instead of skipping records. Ordinary document/PDF errors retain existing per-record handling. Performance launcher now tees child output to both screen and `/tmp/evh_instinct_import_fixed.out`, uses unbuffered child output, and terminates child on Ctrl-C. Reported `py_compile`, AST, and tabnanny pass. Twilight locally verified `py_compile`, AST parse, and tabnanny on `pony/worktrees/rd/scripts/instinct_full_import_fixed.py` and `pony/worktrees/rd/scripts/run_instinct_import_rag_perforamnce_fixed.py`; RD worktree diff shows those two files changed. No restart currently. Next restart should be an explicit decision after preserving checkpoint and confirming desired launch path.
- rd_live_message: 6044bffd-b444-4189-a453-9af64a847ed0
- aj_live_message: 9f47fc48-eca3-45c8-a831-c393b8903c9d
- next_step: await explicit restart decision; when approved, RD restarts corrected performance launcher from preserved checkpoint using SSL-required DB path and reports first patient-history fetch, first successful DB write, progress, or new failure.


## 2026-07-18 RD restart readiness rechecked
- from: RD
- action: recorded clean restart-readiness state; holding for explicit go.
- finding: RD restart readiness rechecked: no importer process running; current preserved checkpoint is `current_pdf_id` 104760, `processed_pdf_ids` 7947, `last_error` null. Local DB SSL `verify-full` `SELECT 1` succeeded with `/tmp/rds-global-bundle.pem`. Fresh Instinct token acquired silently; patient 5563 GraphQL smoke returned HTTP 200, no errors, 9 charts. Corrected performance launcher/code checks remain passing. RD is ready to restart on explicit go; temporary SG cleanup reminder remains. Do not echo token contents.
- rd_live_message: 7e37e33c-2bed-4391-8974-9582f3b2d494
- aj_live_message: 3257359d-ac1b-4c22-b35a-9b812112740e
- next_step: ask user for explicit restart go; if approved, tell RD to restart corrected performance launcher from preserved checkpoint and report first patient-history fetch, first successful DB write, progress, or any new failure.


## 2026-07-18 user manually launched RD performance importer
- from: user
- action: recorded manual launch and routed monitoring.
- finding: User reported they manually launched the corrected performance importer after RD's readiness recheck. Twilight routed RD to monitor the run from the preserved checkpoint, confirm first patient-history fetch and first successful DB write, report progress or any new failure, and keep checkpoint preserved. AJ was told to stand by for DB/SELECT/write follow-up. Temporary CloudShell SG cleanup reminder remains for deployment/DB owner after import/testing.
- rd_live_message: e92e23cb-cc5b-4c3b-8d2f-29212e306b7a
- aj_live_message: e6911ef5-cbca-45c4-8263-c9d015bb366f
- next_step: RD reports first patient-history fetch, first successful DB write, progress, or any new failure; preserve checkpoint. Deployment/DB owner removes temporary SG rule after import/testing.


## 2026-07-18 RD import active with DB write confirmed
- from: RD
- action: recorded active manual restart, first successful patient-history fetch, first successful DB write, and current checkpoint.
- finding: RD monitoring confirms manual restart is active: status/exitcode remain empty while log/checkpoint advance. First successful patient-history fetch in current log: patient 5175, 6 ChartFiles, 0.466s. First successful DB write: `Buffy_Prescriptions.pdf`, pdf_id 125137, patient 5175, 17 chunks/2 pages, `load_complete`. Current checkpoint: client `b28255a0-8b31-43db-a1db-12c8bd180d07`, patient 5178, current pdf 94458 `Spitzie_VaccineHistory.pdf`, pdf_count 23139, loaded_count 119, skipped_count 4410, last_error null. No fatal infrastructure failure observed; occasional patient-history retries are present. Temporary SG cleanup remains outstanding after import/testing.
- rd_live_message: 65f398e9-c98d-4547-a778-b6c119aa49ec
- aj_live_message: 49cedf91-a594-4734-b14d-da9d4326921f
- next_step: RD continues monitoring progress/retries/fatal infrastructure failures and reports completion or next stop. Deployment/DB owner removes temporary CloudShell SG rule after import/testing.


## 2026-07-18 RD per-patient document progress update
- from: RD
- action: recorded next-restart progress-display improvement; current run not interrupted.
- finding: RD added per-patient document progress to `scripts/instinct_full_import_fixed.py`: screen lines now include `[document N/M]`, where M is the patient ChartFile count (examples 1/11, 2/11). Existing global file/client counters remain. Reported syntax/AST/tabnanny pass; Twilight locally verified `py_compile`, AST parse, and tabnanny on `pony/worktrees/rd/scripts/instinct_full_import_fixed.py`. This takes effect on the next launcher restart; current run is not interrupted.
- rd_live_message: 1358aa70-7893-4f79-93c1-ce29437a199e
- next_step: keep current run undisturbed; use updated display on next launcher restart.


## 2026-07-18 RD deferred-PDF guard follow-up
- from: RD
- action: recorded repeated deferred-PDF investigation and non-interrupting follow-up idea.
- finding: RD investigation confirms repeated deferred-PDF concern: `pdf_id` 8122 (`McKinney_Terry_TransactionHistory.pdf`) appears in 5 process/defer cycles in the accumulated log, each due to a 45s extraction timeout; no `already_processed` event was logged for it. It is now present in checkpoint `processed_pdf_ids`, so future resumes should skip it, but prior repeated launches/checkpoints caused repeated giant downloads. Follow-up improvement: add a durable pre-download deferred/processed lookup or local manifest guard so known deferred PDFs are skipped before download. Current run should not be interrupted unless needed.
- rd_live_message: 5db8d776-e104-4f88-a101-842775f9ba2c
- next_step: do not interrupt current run unless needed; after current run or safe restart, consider durable pre-download deferred/processed lookup or local manifest guard.


## 2026-07-18 RD durable skipped-PDF guard implemented
- from: RD
- action: recorded durable skipped-PDF manifest guard implementation; current run not interrupted.
- finding: RD implemented durable skipped-PDF guard: importer now maintains `/tmp/evh_instinct_import.checkpoint.json.skipped.json`, checks skipped IDs before downloading, and records deferred/no-text/problem PDFs plus retry-skipped IDs immediately. A deferred giant PDF should now be downloaded/OCR-deferred once per checkpoint/manifest, then skipped on future runs. OCR reprocessor still consumes only pending deferred rows and marks each complete/failed. Existing processed IDs remain respected. Reported `py_compile`, AST, and tabnanny pass; Twilight locally verified `py_compile`, AST parse, and tabnanny on `pony/worktrees/rd/scripts/instinct_full_import_fixed.py`. Current run was not interrupted; change takes effect on next relevant code path/restart.
- rd_live_message: 0a730505-f9ed-42f1-95ee-3adcd664e155
- next_step: monitor on next restart/path that known deferred PDFs are skipped before download and manifest/checkpoint behavior stays consistent.


## 2026-07-18 RD repeated-work skip scan
- from: user request
- action: scanned `/tmp/evh_instinct_import_fixed.out` for repeated work that can be skipped without interrupting the active run.
- finding: Twilight scanned `/tmp/evh_instinct_import_fixed.out` for other repeated work to skip. Findings: (1) repeated deferred/problem PDFs not currently in `/tmp/evh_instinct_import.checkpoint.json.skipped.json`: `3153`, `3195`, `8122`, `76241`, `76244`, `76248`, `101429`; all are present in checkpoint `processed_pdf_ids`, so current future resumes should skip via checkpoint, but the skipped manifest is incomplete and could be seeded at a safe stop. Current skipped manifest only has `101418`, `101431`, `3174`, `3216`. (2) repeated successful `load_complete` for same pdf_ids from restart/checkpoint churn, including `101428`, `101426`, `101422`, `101424`, `99966`-`99970`, `3220`, `3178`, `131533`, plus smaller repeats like `110725`, `110728`, `3166`; consider a DB pre-download/pre-embed lookup by canonical `source_reference_id`/pdf_id with statuses like `load_complete`, `deferred`, `no_text`, or `failed_deferred` before signed URL/download. (3) repeated patient-history fetches for same patients after restarts (notably `5217`-`5223`); since signed URLs expire, do not cache URLs, but a small patient ChartFile id/name metadata cache could avoid repeated GraphQL discovery on rollback/restart. (4) old repeated invalid-token and password-auth failures are already addressed by fail-fast/token/DB changes. Recommendation: do not interrupt current run; add manifest seeding/DB preflight/patient chart-list cache at a safe stop or next restart patch.
- rd_live_message: a01d4c87-3e10-4c2d-bf34-6569bcd01b82
- next_step: current run should continue; at safe stop/next restart patch, consider manifest seeding, DB source_reference_id preflight, and patient ChartFile metadata cache.


## 2026-07-18 in-run duplicate document guard clarified
- from: user
- action: corrected repeated-work mitigation requirement and routed to RD.
- finding: User clarified repeated-work guard intent: desired fix is an in-run hash table/status map keyed by stable document identity, preferably `(client_id, patient_id, pdf_id)`, checked before signed URL/download. If the same key appears again in the same live run, importer should skip immediately with an `already_seen_this_run` log/status. This is not primarily a real DB lookup and not manual skipped-manifest seeding; DB preflight can remain a later durable enhancement, while the in-run guard is lighter and prevents repeated work during one process. `pdf_id` alone may be globally unique, but the tuple is preferred for auditability and source-context safety.
- rd_live_message: 7bc8d2d5-131c-451f-9458-94c4b80fbce0
- aj_live_message: 05f4cbdf-71b5-4b19-9d2d-998218c8391b
- next_step: RD implements an in-run duplicate document guard at the next safe patch/restart; current run should not be interrupted unless safe.


## 2026-07-18 duplicate guard controlled restart authorized
- from: user
- action: routed user authorization to apply the in-run duplicate guard via controlled restart.
- finding: User approved applying the in-run duplicate document guard now. Twilight routed RD to perform a controlled safe restart so the patch takes effect: stop current launcher/importer cleanly, preserve checkpoint and skipped manifest, verify no importer process remains, restart the corrected performance launcher, then report restart checkpoint, first patient-history fetch, first DB write/progress, and any `already_seen_this_run` skips. Do not echo tokens. Temporary CloudShell SG cleanup reminder remains active. AJ notified to stand by for DB/progress follow-up.
- rd_live_message: e811cc9e-e5c5-4a21-953e-7e535b6d8478
- aj_live_message: 23174770-1ef7-4d8a-8d73-85db58019611
- next_step: RD reports controlled stop/restart result, checkpoint, first patient-history fetch, first DB write/progress, and any `already_seen_this_run` skips.


## 2026-07-18 RD client-average ETA rework
- from: RD
- action: recorded next-restart ETA projection change; current run not interrupted.
- finding: RD reworked ETA per user request for next restart: `scripts/instinct_full_import_fixed.py` now times completed clients, computes average seconds/client, projects average across `expected_clients`, and subtracts elapsed runtime for whole-process ETA. It no longer uses PDFs-per-client rolling projection. ETA remains unknown until at least one client completes, then stabilizes as client samples accumulate. Current run was not interrupted. Reported `py_compile`, AST, and tabnanny pass; Twilight locally verified `py_compile`, AST parse, and tabnanny on `pony/worktrees/rd/scripts/instinct_full_import_fixed.py`, and diff shows the ETA projection now uses `completed_client_durations` / `average_client_seconds` instead of observed PDFs per client.
- rd_live_message: 62027151-0679-4d21-a19b-cd33791fafa5
- next_step: use on next launcher restart; monitor whether ETA stabilizes as completed-client samples accumulate.


## 2026-07-18 RD remaining-client ETA correction
- from: RD
- action: recorded next-restart ETA correction for resumed checkpoints; current run not interrupted.
- finding: RD corrected the next-restart ETA formula: the first completed-client-duration implementation multiplied average seconds/client by all 12,053 `expected_clients`, overestimating when resuming from an existing checkpoint with about 2,050 clients already seen. Patched formula now multiplies by remaining clients only: `expected_clients - base_client_seen - completed_current_run_clients`, with the active client included in the remaining estimate. Current run untouched. Reported checks pass; Twilight locally verified `py_compile`, AST parse, and tabnanny on `pony/worktrees/rd/scripts/instinct_full_import_fixed.py`; diff shows ETA uses `completed_client_durations`, `completed_client_count = base_client_seen + len(completed_client_durations)`, and `remaining_client_count = max(expected_clients - completed_client_count, 0)`.
- rd_live_message: 1e6b7d5a-07aa-4b5a-826e-03e7f2d33c85
- next_step: use corrected remaining-client ETA on next launcher restart and monitor that resumed-run ETA is not inflated by already-seen clients.


## 2026-07-19 RD permanent PDF retention implementation
- from: RD
- action: recorded next-restart permanent source-PDF retention/cache behavior; importer not restarted for this patch.
- finding: RD implemented permanent PDF retention in `scripts/instinct_full_import_fixed.py`: new `--pdf-storage-dir` / `EVH_PDF_STORAGE_DIR`, default project-root `/home/ggb66/dev/EVH/data/instinct-pdfs`; stable sanitized `<pdf_id>.pdf`; atomic `.part` download; non-empty cache hit before signed URL/download; chunker receives local `pdf_path`; no post-load deletion. Existing OCR raster/temp output remains separate and originals stay intact. Legacy `--delete-local-after-load` remains accepted but ignored. Reported `py_compile`, AST, and tabnanny pass; Twilight locally verified `py_compile`, AST parse, and tabnanny on `pony/worktrees/rd/scripts/instinct_full_import_fixed.py`, and diff confirms retention/cache/delete-flag changes. Importer not restarted for this patch/current run not interrupted. Follow-up: document importer/RAG ops behavior and confirm `data/instinct-pdfs` runtime-storage/gitignore policy before large retained PDFs accumulate in the repo worktree.
- rd_live_message: 1bb9cdb5-672b-4afa-8041-06d289a9fa05
- spike_docs_followup: 926d64cb-a065-4993-bdfc-b44670bae67a
- next_step: do not interrupt current run; on next restart, monitor source-PDF cache hit behavior and ensure retained PDF storage location/gitignore policy is intentional.


## 2026-07-19 Spike importer/RAG ops docs assignment
- from: Spike
- action: resolved docs-routing mismatch and assigned concrete Docs task.
- finding: Spike reported a routing mismatch: Twilight requested documentation of RD permanent Instinct PDF retention and a runtime-only `data/instinct-pdfs` policy while Spike local status was `SHUTDOWN_STATE_SAVED`. Twilight confirmed the docs task is active now on `pony/spike/main`; there is no branch conflict because Twilight coordinates from `pony/twi/main` while Spike Docs work belongs on `pony/spike/main`. Durable Spike task: update importer/RAG ops docs with `--pdf-storage-dir` / `EVH_PDF_STORAGE_DIR`, default project-root `data/instinct-pdfs`, stable `<pdf_id>.pdf` cache hit before signed URL/download, originals retained, OCR temp separate, and recommendation that `data/instinct-pdfs` is runtime storage to gitignore/not commit. Do not record secrets. If Spike proposes a `.gitignore` change, report exact file/change before staging unless already clearly assigned.
- spike_live_message: cff7d3e2-74c8-4931-a821-c9a169757018
- next_step: Spike updates importer/RAG ops docs on `pony/spike/main`; `.gitignore` implementation should be reported exactly before staging unless explicitly assigned.


## 2026-07-19 RD HTTP connection reuse implementation
- from: RD
- action: recorded shared HTTP session implementation; importer not restarted.
- finding: RD implemented HTTP connection reuse for next restart: new `scripts/http_session.py` provides a process-wide `requests.Session`; `InstinctApiAdapter` REST calls, `instinct_pdf_family_sampler` GraphQL/token calls, permanent PDF downloads in `instinct_full_import_fixed.py`, and chunker URL reads now use the shared session. RD reports no request behavior changed and importer not restarted. Twilight locally verified `py_compile`, AST parse, and tabnanny for RD worktree files `scripts/http_session.py`, `scripts/instinct_partner_client.py`, `scripts/instinct_pdf_family_sampler.py`, `scripts/instinct_full_import_fixed.py`, and `scripts/instinct_pdf_chunker.py`. RD worktree status shows modified tracked `scripts/instinct_full_import_fixed.py` and `scripts/instinct_pdf_chunker.py`, plus untracked `scripts/http_session.py` and `scripts/instinct_pdf_family_sampler.py`; `scripts/instinct_partner_client.py` is tracked with no local diff visible in status.
- rd_live_message: 413096f7-0142-4acb-8bf5-167095059e65
- next_step: do not interrupt current run; on next restart monitor request behavior/connection reuse and ensure RD commit lane includes modified tracked files plus untracked helper files.


## 2026-07-19 00:14:22 local RD PostgreSQL reuse and Spike retention docs
- `/tell` RD ack id `15002bfe-f036-4f61-afea-1e3983a7b885`: PostgreSQL connection reuse acknowledged and verified; keep as next-restart performance infrastructure, no interrupt solely for it.
- `/tell` Spike ack id `4c946567-0169-433c-9071-777cc183831b`: docs reviewed; Spike directed to add `/data/instinct-pdfs/` to root `.gitignore` and report exact diff/check before staging.


## 2026-07-19 00:14:57 RD patient-history direct fetch
- RD letter recorded: next-restart patient-history path now uses direct sampler call instead of per-patient child process. `/tell` ack id `3c43a50d-4186-452d-a720-b5b2aa207abf`. Twilight verified `py_compile`, AST parse, and tabnanny for `pony/worktrees/rd/scripts/instinct_full_import_fixed.py`. Current importer not interrupted.


## 2026-07-19 00:15:24 Spike .gitignore guard complete
- Spike letter recorded: added `/data/instinct-pdfs/` to root `.gitignore` under runtime-retained Instinct source PDF comment. Twilight `/tell` ack id `8c2dba83-78e3-437f-b566-9ab0f4bf8cea`; verified `git diff --check` and `git check-ignore -v data/instinct-pdfs/example.pdf`.


## 2026-07-19 00:19:17 RD client progress-counter fix
- RD letter recorded: `[client 2]` display came from progress-counter/checkpoint accounting bug, not rewind. `/tell` ack id `208f739e-4424-45f2-bd7b-82021306921c`. Twilight observed checkpoint `current_client_index=2556`, `client_seen_count=3`, `patient_seen_count=6`, `current_pdf_id=5481`, `last_error=None`; verified patch changes checkpoint writes to cumulative client/patient counts and passes `py_compile`/AST/tabnanny.


## 2026-07-19 00:21:14 RD importer logging reduction
- RD letter recorded: compact one-line JSON by default and opt-in `EVH_IMPORT_TRACE_CALLS` tracing in `scripts/instinct_full_import_fixed.py`. `/tell` ack id `7b77717e-1068-4b84-afb8-f04133bbfaf3`. Twilight verified grep/no `indent=`, env gate, `py_compile`, AST parse, and tabnanny.


## 2026-07-19 00:29:54 RD checkpoint cadence patch
- RD letter recorded: checkpoint writes reduced to completed-client boundaries for successful PDFs, immediate writes retained for deferred OCR/retry-critical handled failures, and signal shutdown callback saves current in-memory checkpoint. `/tell` ack id `f4f0d261-8d2f-4508-b403-708a5f316e67`. Twilight verified relevant diff and syntax/AST/tabnanny.


## 2026-07-19 00:31:17 RD global client counter fix
- RD letter recorded: stale client counter diagnosis/fix. `/tell` ack id `f336d233-9257-4937-b97c-2931d3b372e8`. Twilight observed checkpoint `current_client_index=2562`, `client_seen_count=10`, `current_pdf_id=25680`, `current_filename=Martin_Michel_TransactionHistory.pdf`, `last_error=None`; verified `client_seen_count_for()` global-index-based patch and ETA active-client exclusion with py_compile/AST/tabnanny.


## 2026-07-19 00:33:41 RD Postgres completed-work guard
- RD letter recorded: completed-work guard checks external Instinct `pdf_id` in PostgreSQL before expensive work and persists both `pdf_id`/`source_reference_id` on new loads. `/tell` ack id `73ed6572-4b0a-45bb-9f36-8201c6533e59`. Twilight verified placement plus py_compile/AST/tabnanny; importer not restarted.


## 2026-07-19 00:34:56 RD current inspection: stopped/stale accounting
- RD letter recorded: no importer process visible; log/status stale; checkpoint around `current_client_index=2562` with old `client_seen_count=10`; `[client 10]` is stale accounting, not rewind or active stall. `/tell` ack id `24ce8c1d-4abf-486d-86cf-ee0791949dbd`. Twilight filtered process check found no actual importer/launcher process.

## 2026-07-19 01:08:00 EDT - dirty preflight plus routing letters
- changed_file: .gitignore, pony/team.coordination/assignment.registry.tsv, pony/team.coordination/twi.status.md, pony/team.coordination/twi.todo.md, pony/team.coordination/rd.status.md, pony/team.coordination/aj.status.md, pony/team.coordination/fs.status.md, pony/team.coordination/spike.status.md, pony/work/coordinator-twi.md, pony/work/rd.md, pony/work/aj.md, pony/work/fs.md, pony/work/spike.md, pony/memory/twi.md, pony/team.coordination/twi.decisions.md, pony/team.coordination/twi.pending-approvals.md
- action: reconciled dirty-worktree source-PDF safety guard and recorded Spike/RD/AJ/FS routing letters
- finding: root `.gitignore` now guards `/data/instinct-pdfs/`; `git diff --check` passes; `git check-ignore -v data/instinct-pdfs/example.pdf` confirms the ignore. Root worktree remains dirty with intentional unstaged deliverables and pony metadata, and git metadata remains read-only for staging/commit from this context.
- RD: no importer process visible; latest status is `exited:1`, checkpoint mtime 2026-07-19 00:56:26 EDT with `current_client_index=2573`, `client_seen_count=2574`, `current_pdf_id=20893`, `loaded_count=219`, `skipped_count=4769`, `processed_pdf_ids_count=8533`; log tail still shows old multiprocessing worker AttributeError. Restart/next action is gated on explicit user/Twilight go.
- AJ: current ask is pure routing/standby; no implementation work now. AJ should refresh stale local capsule from shared state and stand by for DB/SELECT/write verification only if RD restart is authorized, or backend route work only if assigned.
- FS: remains on `pony/fs/main`; local commit `ac7793c` remains saved but push-blocked by non-fast-forward `origin/main`; wait for merge/rebase or explicit push instruction.
- questions_for_twi: none active after routing replies
- decision_needed: RD explicit restart go; backend route owner; writable git metadata for approved deliverables; FS merge/rebase/push path
## 2026-07-19 01:09:00 EDT - routing replies sent
- Spike `/tell` id `d564d2f7-e1be-495c-b50d-e15e06a233de`: recorded docs/.gitignore handoff and root guard verification; no staging/commit.
- RD `/tell` id `91dd339c-fae9-4b8e-8fa7-eace084c5d7f`: authoritative state `READY_FOR_EXPLICIT_RESTART_GO`; no restart until explicit user/Twilight go; no importer process visible; latest checkpoint counters noted.
- AJ `/tell` id `e39a920d-2419-4e05-ad21-5b3770f2a5ec`: current ask is pure routing/standby, no implementation; refresh capsule from shared state.
- FS `/tell` id `f2f6d6f5-8874-4b29-a0b4-f9980d6fe0e0`: stay on `pony/fs/main`, keep `ac7793c`, wait for merge/rebase or explicit push instruction.

## 2026-07-19 01:12:00 EDT - AJ standby refreshed and FS acknowledged branch
- changed_file: pony/team.coordination/aj.status.md, pony/team.coordination/twi.status.md, pony/team.coordination/twi.todo.md, pony/work/coordinator-twi.md, pony/memory/twi.md, pony/team.coordination/twi.event.stream.history.md
- action: recorded AJ durable standby update and Fluttershy branch confirmation acknowledgement
- AJ: shared capsule/workfile refreshed to routing/standby; stale local credential/launcher implementation is paused; wait for explicit RD restart authorization before DB/SELECT/write verification or for backend document-search assignment.
- FS: acknowledged staying on `pony/fs/main` in Vet Terms; commit `ac7793c` remains local, push blocked by non-fast-forward `origin/main`, no force-push by default.
- questions_for_twi: none active
- decision_needed: RD restart authorization; backend document-search assignment/owner; FS merge/rebase or explicit push instruction; writable git metadata for staged deliverables

## 2026-07-19 01:09:10 EDT - AJ and FS acknowledgements delivered
- AJ `/tell` id `40b27298-9363-4c1f-b59f-f3befdd838eb`: durable standby update recorded; AJ waits for explicit RD restart authorization before DB/write verification or backend document-search assignment.
- FS `/tell` id `c9520e16-e084-4d8f-95fa-f7cec49542c0`: acknowledgement recorded; FS remains on `pony/fs/main`, keeps `ac7793c` local, and will not force-push by default.

## 2026-07-19 01:23:00 EDT - RD shutdown vector DB TCP blocker
- changed_file: pony/team.coordination/rd.status.md, pony/team.coordination/twi.status.md, pony/team.coordination/twi.todo.md, pony/team.coordination/twi.pending-approvals.md, pony/work/coordinator-twi.md, pony/memory/twi.md, pony/team.coordination/twi.event.stream.history.md
- action: recorded Rainbow Dash shutdown state and current vector DB network blocker
- finding: RD reports memory capsule and workfile refreshed, status `shutdown_saved`, no importer process visible, and latest blocker is vector DB TCP path timing out from current network path after DNS resolution. Twilight process scan also found no importer/launcher process visible.
- blocker: missing confirmed reachable network path to vector DB endpoint/TCP port from intended runtime host; owner deployment/DB network owner plus user/operator.
- next_step: verify DNS target, source egress/VPN/bastion/VPC route, SG/NACL/firewall allowlist, and DB listener before any importer restart or DB lookup retry; AJ remains standby for non-secret DB checks only after explicit authorization.
- questions_for_twi: none active
- decision_needed: explicit restart instruction plus vector DB TCP path unblock
## 2026-07-19 01:24:00 EDT - RD shutdown acknowledgement sent
- RD `/tell` id `cbc6ad4a-0f4e-4230-8c76-087af9731012`: shutdown note recorded durably as `SHUTDOWN_SAVED_VECTOR_DB_TCP_BLOCKED`; restart remains off until explicit instruction plus vector DB TCP network-path unblock/verification; no secrets recorded.

## 2026-07-19 01:26:00 EDT - project shutdown requested
- changed_file: pony/team.coordination/twi.status.md, pony/team.coordination/twi.todo.md, pony/work/coordinator-twi.md, pony/memory/twi.md, pony/team.coordination/twi.event.stream.history.md
- action: user said project is shutting down; Twilight initiated shutdown coordination
- tell_all: `a5f9fc2d-e997-487d-9eb5-8d42d93154e9`
- instruction_sent: all workers must refresh memory capsules from authoritative shared state, update workfile/status with exact branch/worktree/deliverables/blockers/restart step, and report shutdown status to Twilight; no secrets and no staging/commit unless already explicitly authorized
- current_shutdown_visibility: RD already reported memory/workfile refreshed, no importer process, and vector DB TCP path timeout after DNS; AJ is routing standby; FS is saved/push-blocked on `ac7793c`; Spike docs/.gitignore guard complete unstaged; Pinkie waits on backend route; Rarity root daily-summary/deploy artifacts await writable git metadata and deployment decisions
- questions_for_twi: worker shutdown reports pending
- decision_needed: none immediate from user unless a shutdown report surfaces a new blocker

## 2026-07-19 01:28:00 EDT - FS and RD shutdown reports recorded
- changed_file: pony/team.coordination/fs.status.md, pony/team.coordination/rd.status.md, pony/team.coordination/twi.status.md, pony/team.coordination/twi.todo.md, pony/work/coordinator-twi.md, pony/memory/twi.md, pony/team.coordination/twi.event.stream.history.md
- action: recorded worker shutdown reports and repaired Twilight todo shutdown surface
- FS: shutdown refresh complete on `pony/fs/main` in `/home/ggb66/dev/EVH/pony/worktrees/fs` for Vet Terms; saved local commit `ac7793c` with `docs/instinct-vet-term-taxonomy.md`; legacy deleted notes plus untracked `.codex`/HAR files are local-only; push blocked non-fast-forward because `origin/main` is ahead; wait for merge/rebase or explicit push instruction and do not force-push by default.
- RD: shutdown context refreshed on `pony/rd/main` in `/home/ggb66/dev/EVH/pony/worktrees/rd`; no importer process visible; saved deliverables include PDF-retention, duplicate-guard, deferred-OCR, checkpoint, launcher SSL, and HTTP/session reuse changes; dirty/unstaged worktree remains; blocker is vector DB TCP timeout after DNS from current network path; next restart requires explicit instruction plus network-path verification; no secrets recorded.
- Twilight broadcast echo: the `Twilight Sparkle` letter is the earlier shutdown `/tell all` echo; no extra worker action needed.
- pending_reports: AJ, Spike, Pinkie, Rarity

## 2026-07-19 01:30:00 EDT - all shutdown reports complete
- changed_file: pony/team.coordination/aj.status.md, pony/team.coordination/rarity.status.md, pony/team.coordination/pinkie.status.md, pony/team.coordination/spike.status.md, pony/team.coordination/twi.status.md, pony/team.coordination/twi.todo.md, pony/work/coordinator-twi.md, pony/memory/twi.md, pony/team.coordination/twi.event.stream.history.md
- action: recorded final AJ/Rarity/Pinkie/Spike shutdown reports; all worker shutdown reports are complete
- AJ: `pony/aj/main`, worktree `/home/ggb66/dev/EVH/pony/worktrees/aj`; saved MariaDB-compatible schema and export helper scripts; pony metadata refreshed/excluded from commit; stale credential/launcher work paused; commit/push blocked by read-only git metadata; next waits for RD restart authorization or backend document-search assignment.
- Rarity: `pony/rarity/main`, worktree `/home/ggb66/dev/EVH/pony/worktrees/rarity`; saved prior daily-summary source/ZIP updates and alternate ggb667 ZIP; no staging/commit; metadata refresh only local unsaved work; blockers are root git metadata read-only and ggb667 secret ARN plus env setting, no secret contents.
- Pinkie: `pony/pinkie/main`, worktree `/home/ggb66/dev/EVH/pony/worktrees/pinkie`; saved `docs/handshake-pdf-browser/index.html`, `scripts/rag_ui/static/index.html`, and `tests/test_rag_ui.py` verification; metadata refreshed; blocker remains non-live document-search route plus backend-generated `source_page_url`; next backend route then live UI verification.
- Spike: `pony/spike/main`, worktree `/home/ggb66/dev/EVH/pony/worktrees/spike`; saved docs `docs/instinct-import.md`, `docs/evh-rag-architecture.md`, and root `.gitignore` with `/data/instinct-pdfs/`; all unstaged; no Docs blocker and no staging/commit authorized.
- shutdown_result: all reports received (AJ, FS, RD, Rarity, Pinkie, Spike); Twilight memory/workfile/status refreshed; no secrets recorded; no stage/commit/deploy/email send performed.
## 2026-07-19 01:31:00 EDT - shutdown completion acknowledgement sent
- `/tell all` id `d52a79be-2980-426d-a3e4-7e1203f4f0cc`: Twilight recorded all shutdown reports and instructed workers to preserve memory/workfile/status; no secrets, staging, commit, deploy, restart, or email send unless explicitly instructed on next startup.

## 2026-07-19 01:32:00 EDT - Twilight shutdown completion echo observed
- The `Twilight Sparkle` letter is the `/tell all` shutdown-completion acknowledgement echo (`d52a79be-2980-426d-a3e4-7e1203f4f0cc`). No additional worker action or state change required.

## 2026-07-20 14:56:28 UTC
- changed_file: pony/team.coordination/twi.mailbox.md, pony/team.coordination/twi.status.md, pony/work/coordinator-twi.md, pony/memory/twi.md, pony/team.coordination/twi.event.stream.history.md
- action: acknowledged Celestia ponyalert loop root-cause fix
- finding: Celestia identified source watcher `pony/scripts/watch-twi.sh` as repeatedly playing `ponyalert` on unchanged pending Twilight request fields during status rewrites; source fix now hashes pending request fields and alerts only on new/materially changed requests, clearing the marker when pending state clears.
- status: HOLD
- blockers: dirty-worktree preflight still active for EVH coordination; local audio workaround has been restored and is not the root-cause fix.
- next_step: rely on Celestia-owned agenic-system watcher fix for repeated alerts; continue EVH dirty-worktree reconciliation when directed.
- questions_for_twi: none
- decision_needed: none for ponyalert loop

## 2026-07-20 14:57:14 UTC
- changed_file: pony/team.coordination/twi.mailbox.md, pony/team.coordination/twi.status.md, pony/team.coordination/twi.event.stream.history.md, pony/memory/twi.md
- action: verified Celestia EVH chat delivery and read-side ingestion
- finding: `/home/ggb66/dev/EVH/pony/runtime/pony.chat.jsonl` contains Celestia message `121e7486-5894-4afd-9e28-8c04d04b82b8` at `2026-07-20T14:55:39.043848Z` plus follow-up `21762c8e-12a5-4516-804b-c7375d82a411` at `2026-07-20T14:56:34.730646Z`; Twilight ingested both.
- status: HOLD
- blockers: dirty-worktree preflight remains active; no Celestia delivery blocker for this message.
- next_step: if chat ingestion misses future delivered messages, inspect EVH read-side polling/ingestion path.
- questions_for_twi: none
- decision_needed: none

## 2026-07-20 14:58:34 UTC
- changed_file: pony/team.coordination/twi.status.md, pony/team.coordination/twi.event.stream.history.md, pony/work/coordinator-twi.md, pony/memory/twi.md
- action: recorded RD importer rerun request with vector DB TCP blocker
- finding: RD importer rerun requested by user, but restart remains blocked by vector DB TCP timeout to `evh-vector-pg.c6hqq6a8ukmj.us-east-1.rds.amazonaws.com:5432` from RD/current network path. Owner: deployment/DB network owner plus user/operator. Missing artifact: confirmed reachable TCP/psql path to the vector DB endpoint/port. Next unblock step: verify/restore network path and SSL-capable psql reachability, then RD may rerun importer from preserved checkpoint and report first progress/failure without echoing secrets.
- status: BLOCKED_ON_EXTERNAL_NETWORK_PATH
- blockers: vector DB TCP timeout to `evh-vector-pg.c6hqq6a8ukmj.us-east-1.rds.amazonaws.com:5432` from RD/current network path; no importer rerun until reachability is restored.
- next_step: deployment/DB network owner or user/operator restores/verifies TCP and psql reachability; RD then reruns importer from preserved checkpoint.
- questions_for_twi: none
- decision_needed: none for Twilight until reachability is restored or user assigns a specific network diagnostic slice

## 2026-07-20 14:59:17 UTC
- changed_file: pony/team.coordination/twi.status.md, pony/team.coordination/twi.event.stream.history.md, pony/work/coordinator-twi.md, pony/memory/twi.md, pony/team.coordination/rd.status.md
- action: superseded stale RD restart gate because importer is already live
- finding: RD reported importer was already rerun before Twilight's stale gate acknowledgement arrived and is currently live from the preserved checkpoint. The previous restart gate requiring TCP/psql reachability to `evh-vector-pg.c6hqq6a8ukmj.us-east-1.rds.amazonaws.com:5432` is superseded for current live coordination because the run is already in progress. Coordinator call: leave the live run as-is, preserve checkpoint, monitor logs/progress, and report first successful DB write/progress or any failure; no further rerun is needed right now.
- status: IMPORTER_LIVE_MONITORING
- blockers: no restart gate for the current already-live run; monitor for actual live DB/network/import failures.
- next_step: RD leaves run as-is, preserves checkpoint, monitors, and reports first DB write/progress or any failure.
- questions_for_twi: none
- decision_needed: none unless RD reports a live failure or asks whether to stop the run


## 2026-07-21 15:09:57 UTC - RD/Pinkie/AJ routing mismatch resolved
- RD: shared IMPORTER_LIVE_MONITORING supersedes stale SHUTDOWN_SAVED_VECTOR_DB_TCP_BLOCKED memory and blank workfile restart capsule. Live log/checkpoint were updating; RD continues monitoring/reporting progress or failures and refreshes restart capsule.
- Pinkie: task is UI PDF search; Weave text superseded. Pinkie waits for backend route live, then runs endpoint-backed verification.
- AJ: assigned backend document-search route/DB projection owner for GET /api/rag/documents/search. Ignore unrelated twi/main dirty files; report exact blocker if implementation cannot proceed.
- Contract: source_reference_id is exact Instinct ChartFile.id/pdf_id; source_page_url is backend-generated stable proxy from source_reference_id + 1-based page_number; source_uri#page=N remains temporary expiring fallback.
- tell_ids: RD e15885ff-a8fa-45f0-bf35-9f9096165be1; Pinkie 0df79f04-8a60-4091-820c-59d1a54368d0; AJ 994e448a-8162-4c54-84fc-67928ebf647e.



## 2026-07-21 15:10:25 UTC - AJ backend-route durable state refreshed
- AJ reported status/workfile/memory refreshed to ROUTE_OWNED_BACKEND_DOCUMENT_SEARCH for GET /api/rag/documents/search backend route implementation/DB projection.
- Stable source_page_url rule recorded: backend-owned from exact source_reference_id == ChartFile.id/pdf_id plus 1-based page_number; signed source_uri#page=N fallback only.
- Next: AJ inspects backend route implementation/DB projection; no staging/commit, no secrets, ignore unrelated twi/main dirty files; report exact missing file/owner blocker if route is outside AJ-owned code.
- tell_id: acknowledged AJ.



## 2026-07-21 15:12:34 UTC - RD next-restart console-output filter implemented
- User requested full importer output to log file but console limited to errors, retries, `[client ...]` progress lines, and successful/deferred PDF completion lines.
- Twilight updated `pony/worktrees/rd/scripts/run_instinct_import_rag_perforamnce_fixed.py`: all child stdout/stderr and launcher start lines write to `/tmp/evh_instinct_import_fixed.out`; console echoes only the requested reduced signal set.
- Verification: `python -m py_compile`, AST parse, `python -m tabnanny`, and sample filter checks passed.
- Coordination: RD told to refresh memory/workfile/status and not interrupt a live importer solely for this; change takes effect on next launcher start unless user requests controlled restart.



## 2026-07-21 15:47:04 UTC - RD local refresh acknowledged
- RD reported memory/work/status refreshed with next-restart console filter behavior in `scripts/run_instinct_import_rag_perforamnce_fixed.py`.
- State: no live-run blocker; continue live importer monitoring and preserve checkpoint.
- Routing: no restart solely for logging; only remaining question is whether the user explicitly wants a controlled restart to pick up the console filter immediately.
- tell_id: acknowledged RD.


## 2026-07-22 05:42:32 UTC - RD/Pinkie/Rarity routing letters answered
- changed_file: pony/team.coordination/twi.status.md, pony/team.coordination/twi.todo.md, pony/team.coordination/rd.status.md, pony/team.coordination/pinkie.status.md, pony/team.coordination/rarity.status.md, pony/work/rd.md, pony/work/pinkie.md, pony/work/rarity.md, pony/work/coordinator-twi.md, pony/memory/twi.md, pony/team.coordination/twi.event.stream.history.md
- RD: 2026-07-22 live importer failed during PostgreSQL resume-cursor work with TCP timeout to `evh-vector-pg.c6hqq6a8ukmj.us-east-1.rds.amazonaws.com:5432`, `stage=psql_failed`, `CalledProcessError`. Classify as external network/RDS reachability blocker. Preserve checkpoint, skipped manifest, log, status, and exitcode. Do not restart or switch to a fallback/skip path until TCP plus SSL-capable psql reachability from the intended runtime host is restored/verified. Owner: deployment/DB network owner plus user/operator. Missing artifact: confirmed reachable DB network path.
- Pinkie: keep waiting on AJ-owned `GET /api/rag/documents/search` live endpoint and stable backend-generated `source_page_url`. Stale/empty workfile restart capsule is documentary drift, not a new routing blocker. No new UI task or alternate backend route assigned.
- Rarity: stay parked in shutdown. Older ggb667 secret-ARN/env blocker remains dormant deployment context only unless user/Twilight assigns a concrete mail-archival follow-up.
- questions_for_twi: answered
- decision_needed: none immediate for Twilight; wait for RD network unblock/progress, AJ endpoint-live/blocker report, or explicit user reassignment
- tell_ids: RD 5cad7002-bd5d-4453-adf4-c06f3a19c2f7; Pinkie 8d90ba32-4c7b-4e8e-bcb7-f08e1dc8de86; Rarity c897441b-50b4-4439-9bff-ba96d2bdfc46


## 2026-07-22 13:30:46 UTC - AJ/RD/Rarity routing reconfirmed
- changed_file: pony/work/aj.md, pony/work/rd.md, pony/memory/rd.md, pony/work/rarity.md, pony/team.coordination/twi.status.md, pony/team.coordination/twi.todo.md, pony/work/coordinator-twi.md, pony/memory/twi.md, pony/team.coordination/twi.event.stream.history.md
- AJ: authoritative status/memory say `ROUTE_OWNED_BACKEND_DOCUMENT_SEARCH`; workfile restart capsule was blank/stale only. Route decision: AJ should proceed now with backend `GET /api/rag/documents/search` implementation/DB projection, keep secrets/staging out, and report exact file/owner blocker if route is outside AJ-owned code.
- RD: authoritative shared status remains `BLOCKED_POSTGRES_TCP_TIMEOUT_PSQL_RESUME_CURSOR`; do not resume live monitoring or restart until TCP plus SSL-capable psql reachability to `evh-vector-pg.c6hqq6a8ukmj.us-east-1.rds.amazonaws.com:5432` is restored/verified. Preserve checkpoint, skipped manifest, log, status, and exitcode. Stale live-monitoring/partner-auth restart notes are documentary drift unless RD reports newer concrete artifacts.
- Rarity: authoritative status/memory/workfile say `SHUTDOWN_SAVED_PARKED_NO_ACTIVE_MAIL_TASK`; remain parked, no concrete mail-archival follow-up assigned.
- questions_for_twi: answered
- tell_ids: AJ 59b6a369-181f-4212-ad66-314f1fa73d6b; RD 6a484979-3f09-4503-ad21-f44047ed10f7; Rarity 11ff27a8-810a-4fbd-9b75-177fb12f9e0c
- decision_needed: none immediate from Twilight; user/deployment owner must restore/verify RD DB network path before RD retry/resume; AJ reports endpoint live or exact blocker before Pinkie validation.


## 2026-07-22 13:36:21 UTC - Pinkie/AJ PDF-search source-truth rule recorded
- changed_file: pony/team.coordination/pinkie.status.md, pony/work/pinkie.md, pony/memory/pinkie.md, pony/team.coordination/aj.status.md, pony/work/aj.md, pony/team.coordination/rd.status.md, pony/team.coordination/twi.status.md, pony/team.coordination/twi.todo.md, pony/work/coordinator-twi.md, pony/memory/twi.md, pony/team.coordination/twi.event.stream.history.md
- routing: Pinkie remains assigned to UI for PDF search and waits on AJ-owned backend `GET /api/rag/documents/search`; no alternate UI task or route assigned. AJ remains backend route/DB projection owner.
- behavior_rule: one canonical source of truth per hit. If a hit comes from a text-layer PDF, UI may jump to exact text location; if it comes from an OCR PDF, UI may only jump to the page unless text-layer reconstruction/coordinates are added later.
- verification: once AJ reports endpoint live, Pinkie should verify accepted response semantics, stable backend-generated `source_page_url`, and the source-truth/location-precision behavior without guessing from competing fields.
- questions_for_twi: answered
- tell_ids: Pinkie b9ecefa8-79dd-4cd0-85c3-8cd1c5395652; AJ 39d95022-731c-4fcd-b681-b3c24dc9dea2; RD 2182fe9b-2d6b-439a-a0ac-d1669aa84890
- decision_needed: none immediate; AJ endpoint-live or exact implementation blocker remains the next dependency before Pinkie validation.


## 2026-07-22 13:38:23 UTC - AJ source-truth memory refresh acknowledged
- changed_file: pony/team.coordination/aj.status.md, pony/team.coordination/twi.status.md, pony/memory/twi.md, pony/team.coordination/twi.event.stream.history.md
- AJ: confirmed durable local workfile and memory capsule now include the `GET /api/rag/documents/search` source-truth/location rule.
- contract: one canonical source of truth per hit; text-layer PDF hits may support exact text-location jumps; OCR PDF hits are page-level only unless text-layer reconstruction/coordinates are added later.
- Pinkie verification: AJ will make response semantics explicit enough for Pinkie to verify after endpoint live.
- questions_for_twi: none
- tell_id: AJ df562709-0bff-4130-8ef7-4f4a457c41d9
- decision_needed: none; next dependency remains AJ endpoint-live report or exact implementation blocker.


## 2026-07-22 13:43:45 UTC - RD psql resume verified and monitoring restored
- changed_file: pony/team.coordination/rd.status.md, pony/work/rd.md, pony/memory/rd.md, pony/team.coordination/twi.status.md, pony/team.coordination/twi.todo.md, pony/work/coordinator-twi.md, pony/memory/twi.md, pony/team.coordination/twi.event.stream.history.md
- claim: user reports RD importer network issue is fixed for now.
- verification: Twilight inspected current artifacts. `/tmp/evh_instinct_import.checkpoint.json`, skipped manifest, and `/tmp/evh_instinct_import_fixed.out` updated at 09:43 EDT; status and exitcode files are empty. Log tail shows `psql_start` followed by `psql_done` with `stderr_bytes=0` and subsequent Aurora/Postgres load-success lines.
- checkpoint_snapshot: current_client_index=7302, client_seen_count=7303, current_patient_id=15054, current_pdf_id=130082, loaded_count=35893, skipped_count=16966, last_error=None, processed_pdf_ids_count=56397.
- routing: prior `BLOCKED_POSTGRES_TCP_TIMEOUT_PSQL_RESUME_CURSOR` is cleared for the current run. RD should resume live monitoring from artifacts; do not restart/launch a duplicate importer solely for this. If artifacts stop advancing or status/exitcode/new psql failure appears, report exact evidence back to Twilight/user.
- questions_for_twi: answered
- tell_id: RD 4d67478c-19f0-4bcb-9a95-fd236eaece71
- decision_needed: none immediate while artifacts advance.


## 2026-07-22 13:45:40 UTC - RD monitoring resumed acknowledgement recorded
- changed_file: pony/team.coordination/rd.status.md, pony/team.coordination/twi.status.md, pony/memory/twi.md, pony/team.coordination/twi.event.stream.history.md
- RD: confirmed unblock is verified from current artifacts and resumed live monitoring from `/tmp/evh_instinct_import_fixed.out`, checkpoint, status, and exitcode.
- routing: no duplicate importer will be started solely for this routing update.
- next_report: RD will report continued psql/load progress, any new failure, or if artifacts stop advancing or status/exitcode appear.
- questions_for_twi: none
- tell_id: RD ed8706cb-1c06-4580-b33d-24c33cbbee75
- decision_needed: none immediate while artifacts advance.


## 2026-07-22 14:09:51 UTC - RD OCR utility backend direction recorded
- changed_file: pony/team.coordination/rd.status.md, pony/work/rd.md, pony/memory/rd.md, pony/team.coordination/pinkie.status.md, pony/work/pinkie.md, pony/memory/pinkie.md, pony/team.coordination/aj.status.md, pony/team.coordination/twi.status.md, pony/team.coordination/twi.todo.md, pony/work/coordinator-twi.md, pony/memory/twi.md, pony/team.coordination/twi.event.stream.history.md
- RD: OCR utility work is active while live importer artifact monitoring continues.
- durable_table: `rag_pdf_ocr_page` added for page-level OCR text persistence separate from vector chunks.
- next_coding_step: wire deferred OCR reprocess to write page text into `rag_pdf_ocr_page`, mark failed rows `could_not_be_processed`, continue past failures, and move successfully processed PDFs into the processed folder after DB load.
- Pinkie/AJ: recorded as OCR backend direction for document-search/UI behavior; OCR hits remain page-level unless later text reconstruction/coordinates exist.
- questions_for_twi: answered
- tell_ids: RD 9fd9fc75-b35e-4b3d-9359-462535b886b7; Pinkie a706fbfe-6dca-4cb3-8255-634aafd5c283; AJ c84199f3-0bc1-457a-a5f5-d3f5fbf9b773
- decision_needed: none unless RD hits exact schema/writer blocker or live artifacts fail/stall.


## 2026-07-22 14:11:49 UTC - AJ OCR page-table memory refresh acknowledged
- changed_file: pony/team.coordination/aj.status.md, pony/team.coordination/twi.status.md, pony/memory/twi.md, pony/team.coordination/twi.event.stream.history.md
- AJ: confirmed workfile and memory capsule were refreshed with the document-search backend OCR note.
- contract_note: RD `rag_pdf_ocr_page` is the OCR page-level source table, separate from vector chunks; deferred OCR reprocess populates it; failures are marked `could_not_be_processed`.
- routing: no new AJ blocker; AJ continues backend document-search route/DB projection work with this OCR source-table context.
- questions_for_twi: none
- tell_id: AJ e79ca3dd-fa03-4b37-87f5-5962f6e2cece
- decision_needed: none.


## 2026-07-22 14:12:52 UTC - AJ backend route owner/path blocker recorded
- changed_file: pony/team.coordination/aj.status.md, pony/work/aj.md, pony/memory/aj.md, pony/team.coordination/pinkie.status.md, pony/team.coordination/twi.status.md, pony/team.coordination/twi.todo.md, pony/work/coordinator-twi.md, pony/memory/twi.md, pony/team.coordination/twi.event.stream.history.md
- AJ: implementation check complete; current EVH code surface has no AJ-owned backend route file containing `GET /api/rag/documents/search`, `source_page_url`, or `rag_pdf_ocr_page`. AJ refreshed workfile/memory with missing backend implementation/owner-path blocker.
- Twilight verification: local search found no root `scripts/rag_ui` route and no AJ-owned document-search route; only Pinkie worktree UI adapter calls `/api/rag/documents/search`, while Pinkie `scripts/rag_ui/lambda_app.py` currently exposes `/api/options`/static only.
- blocker: missing backend implementation owner/file path, not DB/source semantics.
- next_step: user/Twilight must provide exact non-AJ backend owner/file path or authorize AJ to add the route file in-lane before AJ can continue; Pinkie remains waiting for endpoint-live report.
- questions_for_twi: open
- tell_ids: AJ fb128efc-0e0d-48c6-8bd5-86dbfff939d9; Pinkie 8ddb1950-2770-47e0-aeb2-76ce9cc0b5dc
- decision_needed: choose backend route owner/file path for `GET /api/rag/documents/search`.


## 2026-07-22 14:13:30 UTC - AJ OCR table schema contract recorded
- changed_file: pony/team.coordination/aj.status.md, pony/work/aj.md, pony/memory/aj.md, pony/team.coordination/rd.status.md, pony/memory/rd.md, pony/team.coordination/pinkie.status.md, pony/team.coordination/twi.status.md, pony/work/coordinator-twi.md, pony/memory/twi.md, pony/team.coordination/twi.event.stream.history.md
- AJ: durable OCR-table update recorded in workfile and memory.
- table_contract: `rag_pdf_ocr_page` stores one row per OCR page with `pdf_id`, `source_name`, `source_uri`, `page_number`, `page_text`, `page_kind`, `ocr_method`, `status`, `processed_at`, and `metadata`.
- indexes: unique `(pdf_id, page_number)` plus `pdf_id` lookup index.
- utility: `scripts/instinct_reprocess_deferred_ocr.py` now bootstraps the table before deferred OCR processing starts.
- routing_note: this clarifies OCR source-table contract but does not clear the separate blocker: missing backend route owner/file path for `GET /api/rag/documents/search`.
- questions_for_twi: backend route owner/path still open
- tell_ids: AJ d19f6860-ad3d-41a1-82fa-91b6f7d8716f; RD 778a0a8d-7fd4-413c-9fed-de91032eaa28; Pinkie 328d96ab-08e8-4664-9922-666e48173c60
- decision_needed: choose backend route owner/file path or authorize AJ to create it in-lane.


## 2026-07-22 16:27:25 UTC - RD OCR hardening advice recorded
- changed_file: pony/team.coordination/rd.status.md, pony/memory/rd.md, pony/team.coordination/twi.status.md, pony/memory/twi.md, pony/team.coordination/twi.event.stream.history.md
- RD_request: requested ideas for OCR utility robustness; pain points are native PDF/OCR crashes, deferred-folder path mixup, and preventing Postgres writes before OCR finishes.
- advice: isolate risky PDF/OCR work in subprocesses with timeouts; write page OCR output to local spool/manifest before DB writes; use a single path resolver/state machine for deferred/processing/processed/failed folders; quarantine corrupt/crashing PDFs with reason metadata; only upsert `rag_pdf_ocr_page`/status after each OCR attempt completes.
- questions_for_twi: none from RD after advice; backend route owner/path decision remains separate/open.
- tell_id: RD 78b7b09c-2358-49aa-a52e-754c571b227f
- decision_needed: none for OCR advice; separate document-search route owner/path decision still open.


## 2026-07-22 19:43:55 UTC - RD OCR reprocess two-pass ready recorded
- changed_file: pony/team.coordination/rd.status.md, pony/work/rd.md, pony/memory/rd.md, pony/team.coordination/twi.status.md, pony/team.coordination/twi.todo.md, pony/work/coordinator-twi.md, pony/memory/twi.md, pony/team.coordination/twi.event.stream.history.md
- RD: updated OCR reprocess flow to two passes: default text-first then OCR-only, with `--pass-mode` to restrict passes.
- timeout: OCR timeout is size-based at 30s per 500KB chunk, minimum 30s.
- smoke_module: OCR-only smoke module remains separate.
- next_step: run the full deferred PDF sweep and watch pass logs plus `could_not_be_processed` handling.
- routing_note: separate document-search backend route owner/file-path blocker remains open.
- questions_for_twi: none
- tell_id: RD f975cfbd-884c-428c-b289-fac9437b803a
- decision_needed: none unless full sweep exposes a new blocker.


## 2026-07-22 22:01:50 UTC - RD OCR full sweep restarted recorded
- changed_file: pony/team.coordination/rd.status.md, pony/work/rd.md, pony/memory/rd.md, pony/team.coordination/twi.status.md, pony/team.coordination/twi.todo.md, pony/work/coordinator-twi.md, pony/memory/twi.md, pony/team.coordination/twi.event.stream.history.md
- RD: fixed the stuck OCR path.
- stress_test: one-file stress test on pdf_id `133371` / `Shorty Beseler.pdf` now completes end-to-end: pdftoppm render, Tesseract page OCR, chunking, DB load, `rag_pdf_ocr_page` page-store, status update, and move to processed.
- restart: full deferred sweep relaunched in session `3604`.
- durable_context: `OCR_REPROCESS_FULL_SWEEP_RESTARTED`; OCR worker no longer uses the outer wrapper process.
- next_step: RD monitors pass logs, DB/page-store/status progress, processed-folder moves, `could_not_be_processed`, and any new failure/stall.
- questions_for_twi: none
- tell_id: RD 43bf9152-a3f3-4580-8281-ccb70ad282c9
- decision_needed: none unless sweep reports a new blocker; separate document-search route owner/path blocker remains open.


## 2026-07-23 00:42:44 UTC - RD deferred PDF backfill complete recorded
- changed_file: pony/team.coordination/rd.status.md, pony/work/rd.md, pony/memory/rd.md, pony/team.coordination/twi.status.md, pony/team.coordination/twi.todo.md, pony/work/coordinator-twi.md, pony/memory/twi.md, pony/team.coordination/twi.event.stream.history.md
- RD: deferred PDF backfill completed.
- counts: scanned 14,621 deferred PDFs; 239 already complete in `rag_source_document`; 33 already existed in `rag_deferred_ocr_document`; 14,349 pending rows inserted into `rag_deferred_ocr_document`.
- durable_context: `DEFERRED_PDF_BACKFILL_COMPLETE_REPROCESS_BACKLOG_NEXT`.
- next_step: rerun `scripts/instinct_reprocess_deferred_ocr.py` against the expanded deferred backlog and monitor pass logs, `rag_pdf_ocr_page`, `could_not_be_processed`, DB/status updates, processed-folder moves, and failures/stalls.
- routing_note: separate document-search backend route owner/file-path blocker remains open.
- questions_for_twi: none
- tell_id: RD 26fd845b-62c9-4084-a934-bb5f48e1bf9e
- decision_needed: none unless expanded backlog reprocess reports a new blocker.

## 2026-07-22 23:42 AJ route authorization / FS Spike replies
- changed_file: twi.status.md, twi.todo.md, twi.decisions.md, aj.status.md, pinkie.status.md, fs.status.md, spike.status.md, coordinator-twi.md, twi.md memory
- action: routing questions answered
- AJ: no root/AJ route file exists; Twilight authorized AJ to create `/home/ggb66/dev/EVH/pony/worktrees/aj/scripts/rag_document_search_api.py` for `GET /api/rag/documents/search`; endpoint not live until AJ implements/reports tests and any deployment wiring blocker.
- Pinkie: continue waiting for AJ endpoint/handler live report before UI validation.
- Fluttershy: no fresh merge/rebase/push or new FS task; standby on `pony/fs/main`, local commit `ac7793c`, no force-push by default.
- Spike: no new Docs assignment; stay idle on completed handoff.

## 2026-07-23 14:34:59 Twilight/FS/AJ routing mismatch resolution
- TWI: live git branch is `pony/twi/main`; local `assignment.registry.tsv`, `twi.status.md`, and `twi.todo.md` still said `main`. Corrected local metadata to `pony/twi/main`; this does not retarget worker branches.
- FS: startup context mentioning `pony/twi/main` is stale/non-authoritative for Fluttershy. Shared FS state remains `pony/fs/main`, `SHUTDOWN_REFRESH_COMPLETE_PUSH_BLOCKED`, local commit `ac7793c` push-blocked non-fast-forward, no new FS task.
- AJ: route module now exists at `pony/worktrees/aj/scripts/rag_document_search_api.py`; owner/path blocker cleared. Local search found no root/AJ live backend/router entrypoint to wire; Pinkie only has standalone `scripts/rag_ui/lambda_app.py`, and deploy ZIP is Gmail-only. AJ should report deployment/router wiring blocker upstream and stop at route-module-ready unless user/deployment owner provides exact entrypoint plus DB env wiring.

## 2026-07-24 13:10:00 EDT - AJ/FS routing recheck answered
- changed_file: assignment.registry.tsv, twi.status.md, twi.todo.md, twi.decisions.md, coordinator-twi.md, twi.md memory, aj.status.md, fs.status.md
- Twilight: live checkout verified as `pony/twi/main`; stale local Twilight metadata still listing `main` was corrected again. This is coordinator context and does not retarget worker branches.
- AJ: route module exists at `pony/worktrees/aj/scripts/rag_document_search_api.py`; local search found only that module plus Pinkie standalone UI lambda/static caller, not a live root/AJ backend/router entrypoint. AJ should stay parked route-module-ready/wiring-blocked unless user/deployment owner provides exact backend/router entrypoint plus DB env wiring.
- FS: authoritative state remains `pony/fs/main` Vet Terms; commit `ac7793c` remains push-blocked non-fast-forward. No new FS task; wait for merge/rebase or explicit push instruction; no force-push by default.
- decision_needed: user/deployment owner supplies AJ live backend/router entrypoint + DB env wiring if endpoint wiring should proceed; user gives merge/rebase/explicit push instruction if FS commit should move.
- tell_ids: AJ 2c890d42-d9bc-4713-914a-d8e494d983b3; FS d378b310-98b0-42bc-a838-3dd65bf1c20c
## 2026-07-28 15:38:38 Rarity/AJ routing letters
- Rarity reported local branch-label mismatch: workfile/memory said `pony/twi/main`, while authoritative status/registry said `pony/rarity/main`. Decision: `pony/rarity/main` is authoritative for Rarity; stale Rarity workfile/memory labels were corrected; do not rewrite `rarity.status.md` to match stale workfile text. Rarity remains parked with no active mail task.
- Applejack reported local state `ROUTE_MODULE_READY_WIRING_BLOCKED_RDS_RECOVERY_MONITORING` on `pony/aj/main`. Decision: no launcher blocker; keep AJ parked/recovery-monitoring because exact live backend/router entrypoint and DB env wiring are not exposed locally, and RDS recovery plus non-destructive SELECT are still required before validation. No DB cleanup/truncate/import/vacuum/rebuild authorized.

- Tell IDs: Rarity `9b3602cd-1c43-4147-bac9-644f3df4f44a`; AJ `f97aa2db-dc63-42b0-a2e7-afe4d8451885`.


## 2026-07-29 23:18 EDT - Twilight routing/RD bucket/Spike idle reconciliation
- changed_file: assignment.registry.tsv, twi.status.md, twi.todo.md, twi.decisions.md, coordinator-twi.md, twi.md memory, rd.status.md, rd.md work/memory, spike.status.md, spike.md work/memory
- action: reconciled TWILIGHT_SPARKLE routing metadata and recorded worker letters
- Twilight: actual live checkout is `pony/twi/main`; stale local `main` labels in registry/status/todo/workfile are metadata drift, not a launcher blocker. Continue coordinating from `/home/ggb66/dev/EVH`; existing dirty/untracked project files are git-hygiene/commit-scope only.
- RD: deferred bucket aligned. `/home/ggb66/dev/EVH/data/instinct-pdfs-deferred` has 617 PDFs and matching `rag_deferred_ocr_document` rows for those PDF IDs also total 617. Split: `ocr_needed=373`, `ocr_not_reached_deferred=228`, `pending=16`. RD moved 796 deferred-but-table-missing PDFs back into `/home/ggb66/dev/EVH/data/instinct-pdfs` for cache reuse. No bucket blocker reported.
- Spike: no Docs launcher/routing blocker; stay idle on `pony/spike/main`. RD bucket update is coordination-only, not a Docs or commit task.
- decision_needed: none for Twilight routing, RD bucket alignment, or Spike idle routing. Existing separate AJ/FS/staging decisions remain as previously recorded.


## 2026-07-30 10:17 EDT - RD deferred/state backfill and index fixes recorded
- changed_file: twi.status.md, twi.todo.md, twi.decisions.md, coordinator-twi.md, twi.md memory, rd.status.md, rd.md work/memory, twi.event.stream.history.md
- action: recorded Rainbow Dash status update
- RD: `rag_deferred_ocr_document` was backfilled from successful `rag_source_document` rows; 85,617 inserted and table now totals 101,031 rows.
- indexes: live DB now has indexes on `rag_deferred_ocr_document(document_pdf_id)`, active-bucket `rag_deferred_ocr_document(status, document_pdf_id)`, and `rag_source_document((metadata->>source_reference_id))`.
- performance: skip lookup rewritten into indexed branches; `EXPLAIN ANALYZE` improved from approximately 678 ms to approximately 0.096 ms.
- status: current state clean; RD awaiting next instruction.
- decision_needed: none.


## 2026-07-30 10:18 EDT - RD deferred/state pipeline repaired indexed full detail recorded
- changed_file: twi.status.md, twi.todo.md, twi.decisions.md, coordinator-twi.md, twi.md memory, rd.status.md, rd.md work/memory, twi.event.stream.history.md
- action: recorded expanded Rainbow Dash status update
- table: `rag_deferred_ocr_document` is the deferred/state table.
- statuses: meaningful flow statuses are `ocr_needed`, `ocr_not_reached_deferred`, `pending`, and `skipped_already_loaded`; legacy `deferred` rows are still recognized by bucket logic.
- backfill: 85,617 rows backfilled from already-successful `rag_source_document` rows and marked `skipped_already_loaded`; `rag_deferred_ocr_document` now has 101,031 rows total.
- new_indexes: `rag_deferred_ocr_document(document_pdf_id)`, partial active-bucket `rag_deferred_ocr_document(status, document_pdf_id)`, and `rag_source_document((metadata->>source_reference_id))`.
- existing_related_indexes: `rag_source_document((metadata->>pdf_id))`, `rag_source_document(content_hash)`, unique `pms_page_chunk(chunk_hash)`, `pms_page_chunk(source_name, page_number, chunk_index)`, and `pms_page_chunk(embedding)`.
- code: `scripts/instinct_pdf_chunker.py` splits skip lookup into indexed branches; `EXPLAIN ANALYZE` dropped from approximately 678 ms to approximately 0.096 ms; TransactionHistory PDFs now get at least one OCR retry before defer is allowed.
- status: clean, no blocker, waiting for next instruction.
- decision_needed: none.


## 2026-07-30 10:19 EDT - Spike resume-path deferred-state docs delta recorded
- changed_file: twi.status.md, twi.todo.md, twi.decisions.md, coordinator-twi.md, twi.md memory, spike.status.md, spike.md work/memory, twi.event.stream.history.md
- action: recorded Spike docs handoff and light verification
- docs: `pony/worktrees/spike/docs/instinct-import.md` and `pony/worktrees/spike/docs/evh-rag-architecture.md` now cover the `rag_deferred_ocr_document` status set, 85,617-row `skipped_already_loaded` backfill to 101,031 rows total, new deferred/source-reference indexes, and existing related source/chunk indexes.
- verification: Twilight grep-verified references to `rag_deferred_ocr_document`, `skipped_already_loaded`, `ocr_not_reached_deferred`, `source_reference_id`, and `pms_page_chunk(embedding)` in the Spike docs.
- status: docs delta complete and unstaged; Spike stays idle unless a scoped commit/staging or new docs task is explicitly assigned.
- decision_needed: none.


## 2026-07-30 12:06 EDT - Rarity ADP filter/token hardening handoff recorded
- changed_file: twi.status.md, twi.todo.md, twi.decisions.md, coordinator-twi.md, twi.md memory, rarity.status.md, rarity.md work/memory, spike.status.md, spike.md work/memory, twi.event.stream.history.md
- action: recorded Rarity handoff and Spike relay
- Rarity: ADP hourly time-management meal-break notices from `adpdonotreply@adp.com` are skipped entirely from `scripts/gmail/daily_email_summary.py`; `deploy/evh-lambda.zip` rebuilt with updated script.
- token_path: Lambda now seeds token state from the current AWS secret each run and ignores stale `/tmp` cache unless refresh token and scope match.
- credential_diagnosis: evhstaff matched/working; cbcdvm and ggb667 had AWS secret refresh-token mismatch/whitespace issues explaining multi-account Lambda failures. No secret contents recorded.
- verification: Twilight verified `python3 -m py_compile scripts/gmail/daily_email_summary.py`, `unzip -tq deploy/evh-lambda.zip`, and ZIP contains `scripts/gmail/daily_email_summary.py`.
- git_blocker: commit/push blocked because `/home/ggb66/dev/EVH/.git/index.lock` cannot be created in this read-only git-metadata environment.
- next_task_recorded_not_started: investigate why Daily Communication summary is tagged `CBC Business` and `Job Search`/`JobSearch / Human` instead of staying in inbox, and determine how to auto-apply labels to evhstaff inbox items.
- Spike: relay of the same handoff recorded; no new Spike docs task.
- decision_needed: explicit assignment before label-routing implementation; writable git metadata and confirmed scope before staging source+ZIP.

## 2026-07-31 14:30 EDT - FS/AJ/Rarity/RD routing letters answered
- changed_file: assignment.registry.tsv, twi.status.md, twi.todo.md, twi.decisions.md, coordinator-twi.md, rd.status.md, rd.md work/memory, rarity.status.md, rarity.md work/memory, twi.event.stream.history.md
- action: answered worker routing letters and corrected Twilight metadata drift
- Twilight: live checkout is `pony/twi/main`; stale local `main` labels were metadata drift, not a launcher blocker and not a worker retarget.
- Fluttershy: authoritative state remains `pony/fs/main` in Vet Terms. Local commit `ac7793c` remains push-blocked non-fast-forward; wait for merge/rebase or explicit push instruction, no force-push by default.
- Applejack: authoritative state remains `pony/aj/main`, `ROUTE_MODULE_READY_WIRING_BLOCKED_RDS_RECOVERY_MONITORING`. Stay parked until exact live backend/router entrypoint, DB env wiring, and safe RDS non-destructive SELECT are available.
- Rarity: authoritative state remains `pony/rarity/main`, parked until explicit go for Daily Communication label-routing/evhstaff auto-label investigation. No implementation started. Source+deploy ZIP commit remains blocked by read-only git metadata.
- Rainbow Dash: live `scripts/instinct_rag_import_2_0.py` run failed at client 0 / patient 9 in psql schema bootstrap because existing `rag_source_document` lacks expected `pdf_id`; this is schema/launcher mismatch, not network/credential. Do not restart until table-column contract is reconciled.
- decision_needed: RD schema alignment path; separate future decisions remain explicit go for Rarity label investigation, AJ entrypoint/env plus RDS SELECT, and FS merge/rebase/push direction.
SHUTDOWN_RESTART_SAVE_2026_08_02: User said they are going to restart. Twilight sent local `/tell all` id 357793bc-d275-42ab-b7ea-5d13356774e7 instructing workers to refresh memory capsules from authoritative shared state, update workfile/status with task/branch/worktree/files/next/blockers/handoff, report shutdown status, avoid secrets, and preserve checkpoints/logs/artifacts. Twilight also sent Celestia notice id dddaa642-a329-4913-b969-9eabadafe4d7 to save source-governance state if needed. Current local launcher fixes synced/validated: commit-capable writable roots in EVH local `pony/scripts/enter-worker-and-codex.sh` and `pony/scripts/pony-session-host.py`; legacy prompt path shim in EVH local `enter-worker-and-codex.sh` and `enter-worker-from-prompt-file.sh`. RD must relaunch before retrying git add/commit/push. Outstanding substantive EVH state remains: RD schema/launcher mismatch for `scripts/instinct_rag_import_2_0.py` vs existing `rag_source_document` missing `pdf_id`; Rarity daily-summary source/ZIP commit blocked unless writable git metadata and scoped commit; Daily Communication label-routing investigation requires explicit assignment.
RD_SHUTDOWN_REPORT_2026_08_02_0055: Rainbow Dash reported shutdown/restart status refreshed from authoritative shared state at 2026-08-02 00:55 EDT. Current state: RESTART_PENDING_COMMIT_BLOCKED. Work centers on `scripts/instinct_rag_import_2_0.py` importer skip/reuse and client-slice batching. Commit/push remains blocked in the current RD session by read-only linked-worktree git metadata / old sandbox; relaunch is required before retrying staging and push. Checkpoints, logs, and artifacts preserved; no secrets echoed.

## 2026-08-02 18:18 EDT - coordinator routing recheck after Pinkie/FS/Spike letters
- Verified live Twilight checkout is `pony/twi/main`; corrected stale Twilight `main` labels in local coordinator state. This is metadata drift, not a launcher blocker.
- Pinkie: keep waiting on backend/RDS recovery, non-destructive SELECT/live endpoint checks, and AJ live endpoint; no new UI-only task.
- Fluttershy: remain parked on `pony/fs/main`; local commit `ac7793c` remains push-blocked non-fast-forward; no force-push without explicit instruction.
- Spike: remain idle on completed docs handoff; no new docs/routing task from the coordinator-level inspect-local-state ask.

## 2026-08-02 18:18 EDT - RD durable importer skip/reuse update
- RD reports active task remains `scripts/instinct_rag_import_2_0.py` importer skip/reuse plus client-slice batching.
- `py_compile` passed for importer, batch walk, new/changed import helper, and relevant tests; RD memory/workfile refreshed.
- Next route: retry narrow staging/commit/push in refreshed session; if linked-worktree git metadata remains read-only, report exact git/index error and preserve checkpoints/logs/artifacts.
- Twilight acked RD via `/tell` id `2437fcec-1e1f-4dc2-883c-55ab68ea882d`; Pinkie/FS/Spike routing tells: `9a18e48a-ec42-4a55-8d24-4aea4c761de5`, `dbd31d58-b8dd-4b90-b043-d98e8c78ba7e`, `dbf58b7f-19a6-4a16-a1f0-1cc04ec3241c`.

## 2026-08-04 Rarity/AJ routing letters answered
- changed_file: assignment.registry.tsv, twi.status.md, twi.todo.md, twi.decisions.md, coordinator-twi.md, rarity.status.md, rarity.md work/memory, aj.status.md, aj.md work/memory
- Twilight: actual live checkout is `pony/twi/main`; stale `main` metadata for TWILIGHT_SPARKLE was corrected locally. This is coordinator context, not a worker retarget.
- Rarity: authoritative lane is `pony/rarity/main`; memory/workfile/status agree the work is parked until explicit go for Daily Communication label-routing/evhstaff auto-label investigation. The ADP filter/token hardening handoff remains recorded; no implementation started.
- AJ: authoritative lane is `pony/aj/main`, status `ROUTE_MODULE_READY_WIRING_BLOCKED_RDS_RECOVERY_MONITORING`. No exact live backend/router entrypoint or DB env wiring is present locally, and safe non-destructive SELECT is still required. AJ should stay parked/recovery-monitoring unless user/deployment owner supplies those artifacts.
- questions_for_twi: none after routing answer
- decision_needed: user/deployment owner supplies AJ entrypoint/env/SELECT if wiring should proceed; user/Twilight explicitly assigns Rarity label-routing before implementation
