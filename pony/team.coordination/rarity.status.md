AUDIENCE: EVERYONE
BRANCH: pony/rarity/main
WORKTREE: /home/ggb66/dev/EVH/pony/worktrees/rarity
BRANCH_VERIFIED: yes
STATUS: SHUTDOWN_PARKED_PROCESS_EMAILS_FOR_EVH_EMAIL_LINK_BUG
PUSH_STATUS: clean_local_branch
APPROVALS: none recorded
FILES_PLANNED: none until restart; preserve current local dirt/checkpoints
FILES_TOUCHED: pony/memory/rarity.md, pony/work/rarity.md, pony/team.coordination/rarity.status.md; no implementation changes
BLOCKERS: none active; shutdown parking only
NEXT_STEP: on restart, identify the branch/owner, locate the link-rendering source, and patch/tests for universal mail links
QUESTIONS_FOR_TWI: none
DECISION_NEEDED: none for task recording; deploy/merge/branch changes require explicit instruction

NOTES_2026_08_29_RARITY_EMAIL_LINK_INVESTIGATION: Rarity reported the deployed `Process_Emails_for_EVH` bug is now the active lane, with the task to trace which pony/branch owns the codepath and replace Gmail-specific mail links with universal links. Twilight acknowledged via tell `116cf1fb-af34-45ff-8fe9-30a9b476a4e9`.
NOTES_2026_08_29_RARITY_SHUTDOWN_PARKED: User/Twilight requested shutdown while the Process_Emails_for_EVH investigation was active. Rarity refreshed memory/work/status for restart, preserved local dirt/checkpoints, and is parked on `pony/rarity/main` in `/home/ggb66/dev/EVH/pony/worktrees/rarity`.

NOTES_2026_08_29_RARITY_PROCESS_EMAILS_LINK_BUG_ACTIVE: Rarity switched from parked Stockroom planning to active deployed `Process_Emails_for_EVH` email-link bug investigation. Task: investigate deployed Process_Emails_for_EVH email-link bug: trace which pony/branch owns the deployed Gmail summary codepath, identify why Gmail-flavored mail links are generated instead of universal links, and prepare the fix. Continue on `pony/rarity/main` in `/home/ggb66/dev/EVH/pony/worktrees/rarity`; preserve local Stockroom dirt/checkpoints; identify owner/branch and fix point/plan before deploy/merge. Twilight ack tell `5ea3f225-5871-4982-9ffb-ca5576948449`.
