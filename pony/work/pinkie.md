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
- active subtask: define the manual Weave CSV reconciliation/import path now that Weave API access is not available
- isolation update complete: Contacts entry point now lives at `scripts/contacts/weave_contact_sync.py` on a `pony/pinkie/*` branch
- current blocker: Weave support case `901174` is closed and Weave will not provide an API, so any continuing Weave contact workflow must avoid API assumptions
- immediate task: use the local Weave export and persisted Instinct export as the comparison baseline, then decide whether any manual CSV import/reconciliation work is still justified
- launch check: user requested a Codex launch despite the preflight saying there is no immediate active coding slice; local state still shows the Weave Contacts slice as the active Pinkie assignment
- launch verification: local state checked again on 2026-05-07 and still shows the Weave Contacts slice as the active Pinkie assignment, with no new blocker beyond the existing Weave access wait
- launch verification: local state rechecked on 2026-05-08 and still shows the Weave Contacts slice as the active Pinkie assignment, with no new blocker beyond the existing Weave access wait
- launch verification: local state rechecked on 2026-05-10 and still shows the Weave Contacts slice as the active Pinkie assignment, with no new blocker beyond the existing Weave access wait
- launch verification: local state rechecked on 2026-05-15 and still shows the Weave Contacts slice as the active Pinkie assignment, with no new blocker beyond the existing Weave access wait
- launch verification: local state rechecked on 2026-05-19 and still shows the Weave Contacts slice as the active Pinkie assignment, with no new blocker beyond the existing Weave access wait
- live posture: holding on the Weave Contacts slice and ready for direct follow-up input from Twilight or the user
- sync note: Weave and Instinct are already synchronized; treat the local Weave export as a mostly matching mirror of the Instinct account list rather than a bootstrap-only gap
- support note: Weave support case `901174` is closed and Weave will not provide an API
