# Rarity Workfile

Project: EVH
Branch: pony/rarity/main

Status: in_progress
Scope: EVH Mail Archival and Organization
Permissions granted: none recorded
Restart capsule:
- task: choose writable commit lane for daily-summary/sender-routing files
- why: daily-summary send succeeded; remaining blocker is staging/pushing files from correct writable worktree/git metadata context
- next: do not rerun real send; either commit root-visible Gmail/docs changes from writable root/Twilight context or apply/copy them into Rarity worktree and stage from writable Rarity context
- blocker: git staging/push blocked by read-only metadata/worktree-lane mismatch
Artifact: docs/stockroom-merged-stockroom-ur.csv
- current RAG assignment: shared dictionary seed is already delivered and loaded; do not retry the same seed path unless assigned
- shared dictionary load state: AJ worker-side status reports the merged seed was loaded into Handshake's Aurora MySQL/MariaDB-compatible database and verified at 3,133 rows
- user instruction recorded: when handed page-by-page data, save it into a real file instead of creating a stub or summary placeholder
- user instruction recorded: for fuzzy supplier matches, use product-name text matching to populate `Suppliers` while preserving the stockroom numeric fields as-is
- user instruction recorded: use `view.pushHookEvent(el, null, "live_fetch.update_global_product", payload, callback)` from the `product-catalog` LiveView root to perform backend updates; only vary `payload.id`, `payload.params.suppliers`, `payload.params.buying_cost`, `payload.params.unit` fields, and `payload.params.emr_products`; do not use `execJS`
- current working abstraction: intercept `view.pushHookEvent` on the `product-catalog` LiveView root and log every outgoing `live_fetch.*` event plus reply into `window.__stockroomWireLog`
- current working interceptor:
  ```javascript
  (() => {
    const el = document.getElementById("product-catalog");
    const view = Object.values(window.liveSocket.roots).find(v => v.el && v.el.contains(el));

    if (!view) throw new Error("Could not locate LiveView root");
    if (typeof view.pushHookEvent !== "function") throw new Error("view.pushHookEvent not found");

    const orig = view.pushHookEvent.bind(view);
    window.__stockroomWireLog = [];

    view.pushHookEvent = function(el, ref, event, payload, callback) {
      const snap = typeof structuredClone === "function"
        ? structuredClone(payload)
        : JSON.parse(JSON.stringify(payload));

      window.__stockroomWireLog.push({
        ts: new Date().toISOString(),
        kind: "pushHookEvent",
        event,
        payload: snap,
        elId: el?.id ?? null,
        ref: ref ?? null,
      });

      console.log("[Stockroom wire]", event, snap);

      return orig(el, ref, event, payload, function(reply, pushRef) {
        window.__stockroomWireLog.push({
          ts: new Date().toISOString(),
          kind: "reply",
          event,
          reply,
          pushRef,
        });
        console.log("[Stockroom reply]", { event, pushRef, reply });
        return callback?.(reply, pushRef);
      });
    };

    console.log("Stockroom hook wire logging enabled");
  })();
  ```
Notes:
- primary area: EVH Mail Archival and Organization workflows and related EVH records/information management work
- owned implementation area: EVH Mail Archival and Organization; exact file/script ownership to be identified from the existing project structure before editing
- branch policy: work only on Rarity-owned branches in the `pony/rarity/*` namespace; do not do Stockroom implementation work on shared root branches
- keep the workfile current with the active Stockroom subtask before starting implementation
- active subtask: inspect `scripts/coordination/archive/` for the next cleanup, rename, or cross-link in the mail/archive surfaces
- routing note: user guidance says Rarity should stay on `pony/rarity/main` for Stockroom, so no branch move is needed unless Twilight updates the assignment registry
- current input: `Instinct_Stockroom.csv`, `Instinct_Stockroom_with_supplier_matches.csv`, `stockroom_suppliers_ids.csv`, and the Stockroom browser bundle under `Stockroom · Instinct Stockroom_files/`
- current stop: merged Stockroom row emitter is in place and verified; generated `/tmp/rarity-stockroom-merged.csv` with 1,041 rows and both targeted tests passed in the venv
- current stop: browser replay snippet generator now consumes the merged UR columns (`Buying Unit ID`, `Selling Unit ID`, `Supplier Payload`, `EMR Product IDs`) instead of the stale placeholder schema, and the targeted replay/emitter tests pass in the venv
- current stop: `scripts/gmail/evhstaff_gmail_inventory.py` now uses the merged 15-category sender taxonomy and threads OpenAI model controls through the classifier path; fallback default is `gpt-5.6-mini`; syntax check passed via `python3 -m py_compile`
- restart capsule:
  - task: rerun the Gmail sender-routing classifier with `--openai-classifier-model gpt-5.6-mini --openai-reasoning-effort none --openai-text-verbosity low`
  - why: confirm the updated routing map still produces valid structured category output with the merged enum, then reprocess leftovers later with Terra if needed
  - next: execute the inventory command against the authorized Gmail token and inspect `/tmp/evh_gmail_sender_routing_map.regen.json`
  - blocker: none recorded
- blocker: none for the recorded Gmail archival run and no current routing blocker for the `gpt-5.6-mini` sender-routing rerun; prior OAuth testing/allowlist blocker was resolved by successful authorized run for EVH Mail Archival and Organization
- next step: rerun the Gmail sender-routing classifier with `--openai-classifier-model gpt-5.6-mini --openai-reasoning-effort none --openai-text-verbosity low` and inspect `/tmp/evh_gmail_sender_routing_map.regen.json`; reserve Terra for a later leftovers pass if needed; do not continue Stockroom replay unless reassigned
- current slice: created `docs/evh-mail-archive-inventory.md` to map live mailbox/status lanes, archived history, and the Handshake PDF Explorer prototype
- next step: inspect `scripts/coordination/archive/` for the next archive-organizing edit

- 2026-07-14 reassignment: user corrected Rarity scope to EVH Mail Archival and Organization; Meds & Treatments/Stockroom is no longer the active assignment unless explicitly resumed.
- 2026-07-14 Rarity letter: inspected active mail/archive surfaces and moved from inspection to documentation/inventory; adding a small EVH mail/archive inventory doc for current mailbox/archive materials and the Handshake PDF explorer prototype; no blocker yet.
- 2026-07-14 first archival slice complete: created `docs/evh-mail-archive-inventory.md`, cross-linked `docs/handshake-pdf-browser/README.md` back to the inventory, and moved the next active slice to `scripts/coordination/archive/`; no blocker recorded.
- 2026-07-14 evhstaff Google Mail check: Spike found no authoritative local handoff, credential owner, or access-details record for an evhstaff Google Mail account; local docs only mention `evhstaff@gmail.com` as sample/import data. Do not create a new mailbox until user/Twilight confirms an existing authorized account/handoff or gives explicit direction.
- 2026-07-14 EVHStaff Gmail Cleanup blocker: evhstaff@gmail.com Gmail cleanup is blocked by Google verification error 403 access_denied: app is still in testing and only developer-approved testers may access it. Missing artifact/owner: existing authorized tester/account or app verification/allowlist approval path from user/Twilight. Safe posture: pause EVH mail archival work at the launcher boundary until that is provided.


- 2026-07-14 durable blocker recorded: EVHStaff Gmail Cleanup is blocked by Google 403 access_denied because the OAuth app is still in testing; access requires an existing authorized tester/account or app-verification/allowlist approval path. Pause EVH mail archival work at the launcher boundary; do not create a new mailbox until Twilight/user provides the unblock path.
- restart capsule: resume only after Twilight confirms an authorized tester/account or verification/allowlist approval; then re-enter EVH mail archival work from the launcher boundary and do not create a new mailbox.


- 2026-07-14 wrapper added: scripts/gmail/run_evhstaff_gmail_inventory.sh now launches the Gmail inventory helper directly from a Unix-like shell with default client-secrets/token paths under ~/dev and no Windows cmd.exe bridge.
- restart capsule: use the new wrapper from a real WSL/zsh terminal, then approve the browser auth prompt and wait for the inventory output.

- 2026-07-14 durable blocker recorded from Twilight letter: EVHStaff Gmail Cleanup is blocked by Google 403 access_denied because the app is still in testing. Unblock path: user/Twilight must provide an existing authorized tester/account or app-verification/allowlist approval path. Until then, pause EVH mail archival work at the launcher boundary; do not create a new mailbox.
- restart capsule: wait for an authorized tester/account or verification/allowlist path from Twilight or the user, then resume from the launcher boundary; do not create a new mailbox before that unblock.
- 2026-07-14 Gmail archival run documented: working helper `scripts/gmail/evhstaff_gmail_inventory.py`; required scope `https://mail.google.com/`; reset/re-auth by deleting token cache and rerunning OAuth installed-app flow with `prompt=consent`; `gmail.modify` was insufficient for permanent deletion; observed result `deleted_count=3303`, `permanent_delete=true`. Command pattern: `python scripts/gmail/evhstaff_gmail_inventory.py --client-secrets /path/to/evhstaff_gmail_google_client_credentials.json --token-file /path/to/evhstaff_gmail_token.json --query 'older_than:3y' --export-zip /path/to/archive.zip --delete-after-export`.
- 2026-07-16 Rarity state confirmation: current durable rerun model is `gpt-5.6-mini` with `reasoning.effort=none` and `text.verbosity=low`; Terra remains reserved for a later leftovers pass if needed; no routing blocker remains in local state; next step is rerun/inspection of `/tmp/evh_gmail_sender_routing_map.regen.json`.

- 2026-07-16 Twilight note: durable rerun model confirmed as gpt-5.6-mini with reasoning.effort none and text.verbosity low; Terra remains reserved for a later leftovers pass if needed.

- 2026-07-16 routing correction: user rejected any emitted "heuristic" source label; the sender-routing output should now report only qween, openai, or needs_human_intervention.

- restart capsule:
  - task: continue controlled Gmail sample-retrieval sweep for `needs_human_intervention` entries and prune invalid rows with no retrievable sample
  - why: user wants invalid rows removed; sample availability determines which senders stay in the working list
  - next: poll the running batch sweep session `29703` until it finishes, then apply the invalid/no-sample removal to `NamesEmailAddressesCategoriesSource.txt`
  - blocker: none recorded; progress was `80/250 valid=34 invalid=46` before the latest poll

- 2026-07-17 controlled Gmail sample-retrieval sweep completed: 250/250 `needs_human_intervention` entries checked; 133 yielded retrievable samples and 117 did not. Next step is to decide whether no-sample rows become `Uncategorized` in the working list or are otherwise filtered from the review pass.

- 2026-07-17 shutdown capsule: the review file was contaminated by mixed sender data; tomorrow restart from the correct single mailbox only (`evhstaff@gmail.com`) and rebuild the routing list from scratch. Preserve the picker work, but do not reuse the mixed source list.

- 2026-07-16 Gmail sender-routing picker completed: created `scripts/gmail/review_sender_routing_picker.py`; added Gmail preview fetching with caching and fallback queries; added Escape/q save-and-exit behavior; added backup-on-same-input-output handling; added `Uncategorized` as the no-fetch fallback; compile verification passed.
- 2026-07-16 Gmail sender-routing contamination finding: generated/updated `NamesEmailAddressesCategoriesSource.txt` and `reviewed_email_categories.txt` during the sweep, but the source was contaminated by mixed sender data from a non-evhstaff mailbox export. Correct recovery state is to start over tomorrow from the single mailbox `evhstaff@gmail.com` only and rebuild the routing list from scratch without reusing the mixed source list.
- restart capsule:
  - task: rebuild the Gmail sender-routing list from `evhstaff@gmail.com` only using the completed picker workflow
  - why: the current source/review artifacts include mixed sender data from another mailbox and are not trustworthy for EVHStaff archival routing
  - next: discard the mixed-source list for routing purposes, regenerate a clean source from the single mailbox, then rerun/review categories from scratch
  - blocker: contaminated source artifacts; clean single-mailbox source list not generated yet

Restart capsule:
- task: rebuild Gmail sender-routing from `evhstaff@gmail.com` only with a clean cache
- why: current source/review artifacts were contaminated and the zero-byte category cache blocks rerun
- next: rerun the Gmail sender-routing inventory from `evhstaff@gmail.com` only after rebuilding `/tmp/evh_gmail_sender_category_cache.json` as `{}`
- blocker: local zero-byte cache artifact was recreated as `{}`; no populated cache source expected

- 2026-07-17 zero-byte cache confirmation: `/tmp/evh_gmail_sender_category_cache.json` is zero bytes and should be treated as a corrupt/empty cache. Omit/delete/recreate it as `{}` or patch the helper to tolerate empty cache, then rebuild from `evhstaff@gmail.com` only. Do not reuse contaminated mixed-source lists.

- 2026-07-17 cache recreated rerun approved: `/tmp/evh_gmail_sender_category_cache.json` was likely interrupted and has been recreated as `{}`. Twilight approved rerun now from `evhstaff@gmail.com` only, with `gpt-5.6-mini`, `reasoning.effort=none`, `text.verbosity=low`, no mixed-source artifacts, and no destructive delete/export-cleanup flag.
- 2026-07-17 daily summary send target: `scripts/gmail/daily_email_summary.py` now defaults the send recipient to `evhstaff+daily_summary@gmail.com` when `--send-email` is used, while continuing to render `/tmp/evh_daily_email_summary.md` and `/tmp/evh_daily_email_summary.json`.
- 2026-07-17 daily summary model fix: `scripts/gmail/daily_email_summary.py` default OpenAI model updated from invalid `gpt-5.6-mini` to `gpt-5.6-terra` after the summary path returned HTTP 404.
- 2026-07-17 daily summary wrapper: added `scripts/gmail/run_daily_email_summary.sh`; wrapper defaults to the no-send dry-run path so it only writes `/tmp/evh_daily_email_summary.md` and `/tmp/evh_daily_email_summary.json`; validation run completed successfully with 14 unread messages and no OpenAI request.
- 2026-07-17 sender-routing output rename: `/tmp/evh_gmail_sender_routing_map.regen.json` was renamed to `/tmp/evh_gmail_sender_routing_map.text` because the artifact is plain text routing output, not JSON.
- 2026-07-17 sender-routing cleanup: `/tmp/evh_gmail_sender_routing_map.text` was deduplicated by email address and sorted alphabetically by email; 988 input lines collapsed to 578 unique email entries.
- 2026-07-17 sender-routing counts: `/tmp/evh_gmail_sender_routing_map.counts.txt` was written with the per-category totals from the cleaned routing list.

- 2026-07-17 daily summary send support: `scripts/gmail/daily_email_summary.py` now sends rendered Communication Summary to `evhstaff+daily_summary@gmail.com` by default when `--send-email` is used, while still writing `/tmp/evh_daily_email_summary.md` and `/tmp/evh_daily_email_summary.json`; `python3 -m py_compile scripts/gmail/daily_email_summary.py` passed. Twilight routed next slice as small `.sh` wrapper plus dry-run/no-send validation only; real send requires explicit user approval.

- 2026-07-17 daily summary dry-run complete: added `scripts/gmail/run_daily_email_summary.sh` defaulting to no-send dry-run. Validation wrote `/tmp/evh_daily_email_summary.md` and `/tmp/evh_daily_email_summary.json`, reviewed 14 unread messages, and made no OpenAI request. Sender-routing rerun remains separate and untouched; real `--send-email` to `evhstaff+daily_summary@gmail.com` requires explicit user approval.

- 2026-07-17 sender-routing artifact rename acknowledged: `/tmp/evh_gmail_sender_routing_map.regen.json` was renamed to `/tmp/evh_gmail_sender_routing_map.text` because the artifact is plain text routing data, not JSON. Sender-routing remains separate from daily summary work.

- 2026-07-17 sender-routing deduped: `/tmp/evh_gmail_sender_routing_map.text` was deduplicated by email address and sorted alphabetically by email; now 578 unique email entries, down from 988 input lines. Twilight requested a per-category count next; quick check counts: Client=90, Government=9, Insurance=9, Laboratory=13, Legal=1, Marketing=31, needs_human_intervention=283, Scheduling=1, Spam=6, Staff=113, Technology=10, Utilities=1, Vendor=11.

- 2026-07-17 sender-routing counts saved: `/tmp/evh_gmail_sender_routing_map.counts.txt` contains counts from the 578 unique-email list: needs_human_intervention=283, Staff=113, Client=90, Marketing=31, Laboratory=13, Vendor=11, Technology=10, Government=9, Insurance=9, Spam=6, Legal=1, Scheduling=1, Utilities=1. Sender-routing remains separate from daily summary work; real daily-summary send remains approval-gated.

Restart capsule:
- task: commit and push the daily-summary and sender-routing work
- why: user asked to save the memory, plan, and completed work to GitHub
- next: stage only EVH summary/sender-routing files plus rarity memory/workfile, commit tersely, push the current branch, and report back
- blocker: other ponies' status files are dirty in the tree, so stage only the intended EVH files
- blocker: git metadata for the active worktree is currently read-only for lockfile creation, so `git add`/commit/push cannot proceed from this shell

- 2026-07-17 Rarity git index read-only blocker: attempted to stage EVH summary/sender-routing files, but `git add` failed with `Unable to create /home/ggb66/dev/EVH/.git/worktrees/rarity/index.lock: Read-only file system`. Memory capsule/workfile saved; commit/push blocked until the repo metadata is writable or a write-capable shell/worktree is provided.

- 2026-07-17 daily-summary send ran outcome unknown: Rarity reported running daily summary with `--send-email`; final outcome not yet reported. Twilight saw no process later and `/tmp/evh_daily_email_summary.md`/`.json` updated at 17:18 EDT, but there is no recorded Gmail send success/failure. Do not rerun real send without explicit user approval. Git add/commit/push remains blocked: `Unable to create /home/ggb66/dev/EVH/.git/worktrees/rarity/index.lock: Read-only file system`.

- 2026-07-17 daily-summary send succeeded: Gmail id/threadId `19f7203e86fac9ba` sent to `evhstaff+daily_summary@gmail.com`; query `newer_than:1d`; wrote `/tmp/evh_daily_email_summary.md` and `/tmp/evh_daily_email_summary.json`; Unread Reviewed=30, Total Emails=30, counts client_communications=1, records=7, appointments=0, refills=1, pet_questions=0, other=15; follow-up notes included. Do not rerun real send without explicit approval. Git staging/push still blocked until writable commit lane is chosen.
