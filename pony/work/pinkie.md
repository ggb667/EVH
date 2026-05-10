# Pinkie Workfile

Project: EVH
Branch: pony/pinkie/main

Status: in_progress
Scope: Weave Contacts
Permissions granted: none recorded
Notes:
- primary area: Weave contacts workflows and related EVH integration work
- owned script directory: `scripts/contacts/`
- branch policy: work only on Pinkie-owned branches in the `pony/pinkie/*` namespace; do not do Contacts implementation work on shared root branches
- active subtask: bootstrap Weave contact import by reconciling the live Instinct export against existing Weave contacts before first upload
- isolation update complete: Contacts entry point now lives at `scripts/contacts/weave_contact_sync.py` on a `pony/pinkie/*` branch
- current blocker: waiting on Weave support case `901174` for application credentials/export access so the existing Weave contact list can be pulled for bootstrap reconciliation
- immediate task: persist the live Instinct export artifacts into the branch so shutdown does not depend on `/tmp`
- launch check: user requested a Codex launch despite the preflight saying there is no immediate active coding slice; local state still shows the Weave Contacts slice as the active Pinkie assignment
- launch verification: local state checked again on 2026-05-07 and still shows the Weave Contacts slice as the active Pinkie assignment, with no new blocker beyond the existing Weave access wait
- launch verification: local state rechecked on 2026-05-08 and still shows the Weave Contacts slice as the active Pinkie assignment, with no new blocker beyond the existing Weave access wait
- live posture: holding on the Weave Contacts slice and ready for direct follow-up input from Twilight or the user
