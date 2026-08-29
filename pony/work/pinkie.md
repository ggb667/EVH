# Pinkie Workfile

Project: EVH
Branch: pony/pinkie/main

Status: in_progress
Scope: Weave Contacts
Permissions granted: none recorded
Restart capsule:
- task: shutdown handoff / idle standby
- why: preserve current restart context and keep local dirt/checkpoints intact for the next Pinkie session
- next: on resume, read memory capsule first, then workfile and shared status, then verify branch/commit/dirty state before acting
- blocker: none
Notes:
- primary area: Weave contacts workflows and related EVH integration work
- owned script directory: `scripts/contacts/`
- branch policy: work only on Pinkie-owned branches in the `pony/pinkie/*` namespace; do not do Contacts implementation work on shared root branches
- active subtask: bootstrap Weave contact import by reconciling the live Instinct export against existing Weave contacts before first upload
- isolation update complete: Contacts entry point now lives at `scripts/contacts/weave_contact_sync.py` on a `pony/pinkie/*` branch
- current blocker: waiting on Weave support case `901174` for application credentials/export access so the existing Weave contact list can be pulled for bootstrap reconciliation
- immediate task: persist the live Instinct export artifacts into the branch so shutdown does not depend on `/tmp`
 - shutdown note: preserve dirty tracked files in `pony/README.md` and `pony/pony.system.config.yaml`; do not discard or overwrite them during idle
