# Rarity Workfile

Project: EVH
Branch: pony/rarity/main

Status: DAILY_SUMMARY_ADP_FILTER_TOKEN_HARDENING_COMMIT_BLOCKED_LABEL_FOLLOWUP_NEXT
Scope: EVH Mail Archival and Organization
Permissions granted: none recorded
Restart capsule:
- task: none recorded
- why: none recorded
- next: none recorded
- blocker: none recorded
Artifact: docs/stockroom-merged-stockroom-ur.csv
- current RAG assignment: shared dictionary seed is already delivered and loaded; do not retry the same seed path unless assigned
- current shutdown note: mail-archival deliverables are recorded; no new implementation work is active in this worktree

- 2026-07-22 routing reconfirmation: Twilight confirmed Rarity remains parked; no concrete EVH Mail Archival follow-up is assigned.
- 2026-07-25 restart: user requested the Gmail/OpenAI category guesser be restarted with plain-format output to `/tmp/reviewed_email_categories.guessed.txt`.
- 2026-07-27 routing answer: Twilight superseded the stale restart note; remain parked and do not resume the guesser unless reassigned.
- 2026-07-28 branch-label correction: authoritative Rarity branch/worktree is `pony/rarity/main` at `/home/ggb66/dev/EVH/pony/worktrees/rarity`; prior `pony/twi/main` in this workfile was stale Twilight coordinator context. Do not rewrite `rarity.status.md` to match the stale label.
- 2026-07-29 routing update: user supplied Spike documentation for the AWS email summary program; current incident triage should focus on Lambda `Process_Emails_for_EVH`, EventBridge trigger, Secrets Manager OAuth secret, and logs around refresh token/secret access failures.
- 2026-07-29 status update: OAuth consent screen has been published to In production; next step is to generate a fresh refresh token and update the AWS Secrets Manager secret before rerunning Lambda.
- 2026-07-29 resolution: local OAuth helper completed successfully for `evhstaff@gmail.com`; token cache written to `/home/ggb66/dev/EVH/.secrets/evhstaff_token.json`. Next step is to copy the new refresh token into AWS Secrets Manager and rerun `Process_Emails_for_EVH`.
- 2026-07-29 patch update: daily summary code now supports per-mailbox checkpoint naming (sanitized mailbox key) and the deployment bundle was rebuilt at `/home/ggb66/dev/EVH/deploy/evh-lambda.zip`. User should upload the rebuilt zip to the remote Lambda and ensure the mailbox-specific checkpoint path is used going forward.
- 2026-07-30 ADP filter update: scripts/gmail/daily_email_summary.py now skips `adpdonotreply@adp.com` hourly time-management meal-break notifications with subject containing `Hourly Time Management Notification`; deploy ZIP rebuilt and validated. Lambda token flow was hardened to seed from the current AWS secret and ignore stale `/tmp` cache unless the token matches. Current user follow-up is summary-labeling and inbox-placement behavior, plus auto-labeling for evhstaff inbox items.
- 2026-08-04 routing answer: authoritative Rarity state is `pony/rarity/main` at `/home/ggb66/dev/EVH/pony/worktrees/rarity`; `pony/twi/main` is Twilight coordinator startup context only. Stay parked until explicit go for Daily Communication label-routing/evhstaff auto-label investigation.
