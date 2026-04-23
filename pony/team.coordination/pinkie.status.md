AUDIENCE: EVERYONE
BRANCH: pony/pinkie/weave-contact-bootstrap
WORKTREE: /home/ggb66/dev/EVH/pony/worktrees/pinkie
BRANCH_VERIFIED: yes
STATUS: IN_PROGRESS
PUSH_STATUS: local_changes_not_pushed
FILES_PLANNED: scripts/contacts/weave_contact_sync.py, scripts/contacts/__init__.py, tests/test_weave_contact_sync.py, docs/weave-instinct-account-sync-design.md, README.md, pony/work/pinkie.md
FILES_TOUCHED: scripts/contacts/weave_contact_sync.py, scripts/contacts/__init__.py, tests/test_weave_contact_sync.py, docs/weave-instinct-account-sync-design.md, README.md, pony/work/pinkie.md, pony/team.coordination/pinkie.status.md
BLOCKERS: waiting on Weave support case 901174 for application credentials and export permissions to pull the existing Weave contact list for bootstrap reconciliation; likely substantial overlap with legacy Avimark contacts already in Weave
NEXT_STEP: persist the live export artifacts into the Pinkie branch, then wait for case 901174 and run the one-time bootstrap reconciliation before any Weave import
QUESTIONS_FOR_TWI: none
DECISION_NEEDED: none
