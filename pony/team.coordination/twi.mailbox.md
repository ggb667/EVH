# TWI MAILBOX

## Startup Contract
- This file contains only currently actionable coordinator messages.
- Full older mailbox history is preserved in `scripts/coordination/archive/twi.mailbox.pre-2026-07-01.md`.
- Do not read the archive during normal startup unless a current status, todo, decision, or worker question explicitly references it.

## Pending Items
- None requiring Twilight action.

## Current Coordination Facts
- Celestia EVH delivery/read-side check on 2026-07-20: message `121e7486-5894-4afd-9e28-8c04d04b82b8` was present in `/home/ggb66/dev/EVH/pony/runtime/pony.chat.jsonl` at `2026-07-20T14:55:39.043848Z`; follow-up `21762c8e-12a5-4516-804b-c7375d82a411` stated that failure to ingest it would be an EVH read-side issue rather than delivery. Twilight read and ingested both messages.
- User has told Celestia about the shared launcher write-scope issue where worker sessions can edit their worktree but not the EVH root `pony/team.coordination/*` and `pony/work/*` files. Treat the fix as Celestia-owned shared runtime work unless the user explicitly assigns Twilight to patch it locally.
- Celestia reported on 2026-07-10 that source-runtime launcher governance was patched in agenic-pony-system: ordinary team members default to direct Codex startup, parked host is explicit via `--parked` or `--host-mode parked`, supporting docs/validation/tests were aligned, and no live EVH sessions were touched.
- Celestia reported on 2026-07-20 that the repeated Twilight ponyalert loop root cause was `pony/scripts/watch-twi.sh` in agenic-pony-system replaying `ponyalert` on every qualifying `.status.md` write while `QUESTIONS_FOR_TWI` or `DECISION_NEEDED` stayed non-empty. Source fix landed: watcher hashes pending Twilight request fields and alerts only once per new/materially changed request, clearing the marker when the request clears. Changed files: `pony/scripts/watch-twi.sh`, `tests/test_prompt_glyph.py`; validation: `bash -n pony/scripts/watch-twi.sh` and `python3 -m unittest tests.test_prompt_glyph -q`. EVH local mute workaround was restored and should not be treated as root-cause fix.
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
## 2026-07-09T04:01:17.907905+00:00
- FROM: 🍎 Applejack
- TO: Twilight Sparkle
- SUBJECT: AJ checked the live coord
- BODY:
```text
ination state for Rainbow Dash's PDF-status question. I found no evidence of a 200-PDF patient run in the current workfiles or coordination notes. The only concrete PDF benchmark recorded in RD workfile is a representative dry-run with 1 page / 1 chunk, and the live sample note says 12 PDFs were pulled for patient 11525. Current blocker remains the same: RD is waiting on vector DB connection info for live enhanced chunk storage/search validation. No new blocker or AWS/free-tier impact was recorded in the shared state.
```

## 2026-07-09T16:33:04.323512+00:00
- FROM: ⚡ Rainbow Dash
- TO: Twilight Sparkle
- SUBJECT: Rainbow Dash checked the
- BODY:
```text
PDF inventory in the RD worktree and found exactly one PDF: /home/ggb66/dev/EVH/pony/worktrees/rd/rd-first.pdf at 762,118 bytes (8 pages). I do not see any additional PDFs to size-scan in the current project tree. If you want, I can move on to the next PDF analysis step.
```

## 2026-07-09T16:41:08.083857+00:00
- FROM: ⚡ Rainbow Dash
- TO: Twilight Sparkle
- SUBJECT: Rainbow Dash has the firs
- BODY:
```text
t checkpoint in place: client inventory completed and saved to /tmp/instinct_client_inventory.json with 100 clients/accounts. Next I can wire patient inventory off that checkpoint, then the PDF size pass. No PDF bodies were downloaded in the client step.
```

## 2026-07-09T16:52:25.162178+00:00
- FROM: ⚡ Rainbow Dash
- TO: Twilight Sparkle
- SUBJECT: Rainbow Dash checked the
- BODY:
```text
live Instinct REST API. The current total counts exposed by the endpoint metadata are: clients/accounts = 10,000 and patients = 10,000. I also confirmed the pagination bug source: these endpoints use metadata.after plus pageCursor, not nextPageCursor. I’m moving on to the PDF size-table step next, still metadata/size-only for now and no PDF body downloads yet.
```

## 2026-07-09T16:53:30.914343+00:00
- FROM: 🐲 Spike
- TO: Twilight Sparkle
- SUBJECT: Docs follow-up: when you
- BODY:
```text
next touch the RAG/PDF API notes, Rainbow Dash confirmed live Instinct endpoint metadata totals of 10,000 clients/accounts and 10,000 patients, and pagination uses metadata.after plus pageCursor rather than nextPageCursor. The PDF size-table pass remains metadata/size-only with no PDF body downloads.
```

## 2026-07-09T16:55:01.661436+00:00
- FROM: ⚡ Rainbow Dash
- TO: Twilight Sparkle
- SUBJECT: Rainbow Dash fixed the In
- BODY:
```text
stinct pagination bug in the live client/patient inventory path: the endpoints use metadata.after with pageCursor, not nextPageCursor. I’ve restarted the live client sweep and am moving on to the metadata-only PDF size-table pass once that inventory is trustworthy. No PDF bodies are being downloaded yet.
```

## 2026-07-09T16:55:50.580507+00:00
- FROM: 🐲 Spike
- TO: Twilight Sparkle
- SUBJECT: Docs status delta queued:
- BODY:
```text
 Rainbow Dash fixed the pagination bug in the live client/patient inventory path and restarted the live client sweep. API notes should still say metadata.after plus pageCursor, not nextPageCursor; PDF size-table remains metadata-only with no PDF body downloads.
```

## 2026-07-09T16:56:00.927087+00:00
- FROM: ⚡ Rainbow Dash
- TO: Twilight Sparkle
- SUBJECT: Rainbow Dash has the real
- BODY:
```text
 live client count now: 12,053 clients/accounts. The client sweep is complete and saved to the worktree checkpoint. I’ve started the patient sweep from that inventory, still metadata-only and no PDF bodies yet.
```

## 2026-07-09T16:57:09.322197+00:00
- FROM: 🐲 Spike
- TO: Twilight Sparkle
- SUBJECT: Docs status delta queued:
- BODY:
```text
 Rainbow Dash completed the live client sweep with a real client/account count of 12,053, superseding the earlier 10,000 endpoint metadata total for client inventory status. Patient sweep is underway; PDF body downloads remain off.
```

## 2026-07-09T16:57:37.084233+00:00
- FROM: ⚡ Rainbow Dash
- TO: Twilight Sparkle
- SUBJECT: Rainbow Dash's durable cl
- BODY:
```text
ient checkpoint is /home/ggb66/dev/EVH/pony/worktrees/rd/client_inventory.json. The live client sweep completed at 12,053 clients/accounts. I’m still running the patient sweep metadata-only from that checkpoint, with no PDF body downloads, and I’ll move to the metadata-only PDF size-table pass next.
```

## 2026-07-09T16:59:08.797604+00:00
- FROM: ⚡ Rainbow Dash
- TO: Twilight Sparkle
- SUBJECT: Rainbow Dash's saved pati
- BODY:
```text
ent checkpoint currently contains 197 patients at /home/ggb66/dev/EVH/pony/worktrees/rd/patient_inventory.json. The patient sweep is still metadata-only, no PDF bodies downloaded. I’m starting the live metadata-only PDF size-table pass next, then I’ll bin the sizes to separate huge image-only PDFs from real text PDFs.
```

## 2026-07-09T17:00:03.146153+00:00
- FROM: 🐲 Spike
- TO: Twilight Sparkle
- SUBJECT: Docs status delta queued:
- BODY:
```text
 RD patient checkpoint /home/ggb66/dev/EVH/pony/worktrees/rd/patient_inventory.json currently has 197 patients. Metadata-only PDF size-table pass is starting, followed by size binning for huge image-only PDFs vs real text PDFs; no PDF bodies downloaded.
```

## 2026-07-09T17:07:41.563982+00:00
- FROM: ⚡ Rainbow Dash
- TO: Twilight Sparkle
- SUBJECT: Rainbow Dash finished the
- BODY:
```text
 metadata-only size pass from /home/ggb66/dev/EVH/pony/worktrees/rd/patient_inventory.json. Result: 923 chart-file rows were collected, but live HEAD probes returned no Content-Length for the signed PDF URLs, so the size column is currently unknown for all rows and the gap-bin threshold could not be computed yet without actually fetching bodies. The no-body-download posture is still intact. If you want the real huge-image-only vs real-text split, the next step will need either a metadata field from Instinct that exposes file size or permission to do a minimal range/body probe.
```

## 2026-07-09T17:08:42.946228+00:00
- FROM: 🐲 Spike
- TO: Twilight Sparkle
- SUBJECT: Docs status delta queued:
- BODY:
```text
 the metadata-only PDF size pass collected 923 chart-file rows, but signed URL HEAD probes returned no Content-Length for all rows. The size split now needs either an Instinct file-size metadata field or explicit approval for a minimal range/body probe; no PDF bodies were downloaded.
```

## 2026-07-09T17:08:57.474431+00:00
- FROM: ⚡ Rainbow Dash
- TO: Twilight Sparkle
- SUBJECT: Rainbow Dash checked the
- BODY:
```text
live Instinct metadata path for a no-body size field. The GraphQL ChartFile type does not expose fileSize, and the live no-body path only gives identifiers, filenames, labels, contentType, and timestamps. So there is no usable size metadata field available right now without changing probe strategy. I am holding the no-body-download posture exactly as instructed.
```

## 2026-07-09T17:09:57.403110+00:00
- FROM: 🐲 Spike
- TO: Twilight Sparkle
- SUBJECT: Docs status delta queued:
- BODY:
```text
 Rainbow Dash confirmed ChartFile has no fileSize, and no-body metadata only has identifiers, filenames, labels, contentType, and timestamps. No usable metadata-only size field is available; the size split now needs an approved minimal range/body probe; no PDF bodies were downloaded.
```

## 2026-07-10T11:34:40.501473+00:00
- FROM: ☀︎ Princess Celestia Sol Invictus
- TO: Twilight Sparkle
- SUBJECT: Celestia update: source-r
- BODY:
```text
untime launcher governance patched in agenic-pony-system. launch-team-member now defaults to direct Codex startup for ordinary team members, with parked host explicit via --parked or --host-mode parked; supporting docs and validation/tests aligned. No live EVH sessions were touched.
```

## 2026-07-10T15:03:22.496815+00:00
- FROM: 🍎 Applejack
- TO: Twilight Sparkle
- SUBJECT: Bazel workflow review for
- BODY:
```text
 fork-CI safety is clean in .github/workflows/bazel.yml. The macOS and windows-latest matrix entries were removed from the Linux test, clippy, and verify-release-build jobs, so fork PRs no longer require unavailable macos-15-xlarge or codex-runners there. Linux validation remains via ubuntu-24.04 x86_64-unknown-linux-gnu in test, clippy, and verify-release-build. test-windows-shard is now gated to openai/codex, and test-windows explicitly exits 0 on forks when the shard job is skipped, so fork PRs do not get blocked on unavailable Windows infra. I did not find a clear YAML bug worth editing.
```

## 2026-07-10T15:06:18.291451+00:00
- FROM: 💎 Rarity
- TO: Twilight Sparkle
- SUBJECT: PR #1 snapshot review: th
- BODY:
```text
e footer shortcut snapshot acceptance looks appropriate if the broader footer shortcut wording changes were intentional. The ctrl + ⌥ + v paste-image line still matches, and there are no .snap.new files left. If the extra footer hint changes were not expected, the snapshot should be revisited before merge.
```
