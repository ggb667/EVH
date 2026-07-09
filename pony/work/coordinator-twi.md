# Twilight Workfile

Project: EVH
Branch: pony/twi/main

Status: active
Scope: coordinate assigned EVH workers
Permissions granted: none recorded
Notes:
- startup fast path: after dirty-worktree preflight, read `assignment.registry.tsv`, `*.status.md`, `twi.todo.md`, `twi.decisions.md`, `twi.mailbox.md`, and this workfile; treat `twi.event.stream.history.md` as a short rolling log and do not open `*.archive.md` files unless current state explicitly points there
- canonical worker scopes are assigned in pony/team.coordination/assignment.registry.tsv
- keep workers aligned to their current EVH areas and handle follow-up routing
- owned script directory: `scripts/coordination/`
- worker isolation rule: AJ owns `scripts/reminders/`, Pinkie owns `scripts/contacts/`, FS owns `scripts/schedule/`, Rarity owns `scripts/stockroom/`, RD owns `scripts/vetcove/`, Spike owns `scripts/docs/`, and Twilight owns `scripts/coordination/`
- branch rule: every worker stays on their own pony branch namespace and avoids shared root branches for implementation work; Twilight coordinates from the EVH root worktree on `pony/twi/main`
- current project state: reminder importer/doc work is now documented and pushed
- current repo state: Twilight coordinates from `/home/ggb66/dev/EVH` on `pony/twi/main`; keep root-worktree coordination changes there rather than on a worker branch
- worker state: Spike was rebased onto `origin/main` and pushed as `655d7e5`
- current RAG coordination correction: AJ worker-side mailbox says the shared load target is Handshake's Aurora MySQL, MariaDB-compatible database, not Postgres/pgvector
- current RAG coordination correction: AJ reports the shared dictionary seed already loaded and verified at 3,133 `rag_dictionary_term` rows, so workers should not retry that seed/load path on relaunch
