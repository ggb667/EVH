# Rarity Workfile

Project: EVH
Branch: pony/rarity/main

Status: SHUTDOWN_PARKED_PROCESS_EMAILS_FOR_EVH_EMAIL_LINK_BUG
Scope: Gmail summaries / Process_Emails_for_EVH email-link bug
Permissions granted: none recorded
Restart capsule:
- task: shutdown handoff saved for Process_Emails_for_EVH email-link bug; preserve local dirt and checkpoints
- why: user/Twilight requested shutdown while the deployed Gmail summary codepath is still under investigation
- next: on restart, identify the branch/owner, locate the link-rendering source, and patch/tests for universal mail links
- blocker: none active; deploy/merge/branch changes require explicit instruction
Notes:
- primary area: Gmail daily summary / Process_Emails_for_EVH investigation and fix
- keep the workfile current with the active email-link bug subtask before implementation
- active subtask: deployed function is likely backed by the daily summary script, and the generated links need to be universal rather than Gmail-specific
- routing note: preserve the current branch and local dirt while tracing ownership; keep Stockroom dirt/checkpoints intact

- 2026-08-29 shutdown handoff: preserve local dirt/checkpoints, remain on `pony/rarity/main` in `/home/ggb66/dev/EVH/pony/worktrees/rarity`, and resume the Process_Emails_for_EVH email-link bug by identifying owner/branch and universal-link fix point before any deploy/merge. Preserve Stockroom checkpoints too; told Twilight with ack `5ea3f225-5871-4982-9ffb-ca5576948449`.
