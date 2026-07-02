AUDIENCE: EVERYONE
BRANCH: main
WORKTREE: /home/ggb66/dev/EVH
BRANCH_VERIFIED: yes
STATUS: ASSIGNED
PUSH_STATUS: clean_local_branch
FILES_PLANNED: pony/team.coordination/spike.mailbox.md, pony/team.coordination/spike.status.md
FILES_TOUCHED: pony/team.coordination/spike.mailbox.md, pony/team.coordination/spike.status.md
BLOCKERS: none
NEXT_STEP: document the managed Postgres vector DB and the loading handoff for the RAG architecture notes
QUESTIONS_FOR_TWI: none
DECISION_NEEDED: none
NOTES: AJ update recorded - Handshake is Aurora MySQL; use a separate managed Postgres DB for EVH RAG vectors and document chunks
NOTES: managed Postgres `evh-vector-pg` is available and ready for the vector DB loading step
NOTES: TRI matching strategy documented in `docs/tri-matching-strategy.md`; search spans multiple dictionary tables with exact and prefix matching plus symbol-aware tokenization
