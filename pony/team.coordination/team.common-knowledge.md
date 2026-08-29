# EVH Team Common Knowledge

Last updated: 2026-08-29 by Twilight Sparkle.

This file collects cross-lane process/system lessons distilled from AJ, Pinkie, Rarity, and RD restart capsules/status files. It is durable team guidance, not authorization for any specific deploy, push, merge, branch switch, rebase, or cleanup.

## Next restart team instruction
- On the next EVH restart, Twilight should tell all workers to `git fetch` and, if they are on `main`, preserve local dirt/checkpoints and `git pull` from `origin/main` so they receive the pushed AJ merge and common-knowledge update.
- Workers not on `main` should fetch for awareness but should not switch branches unless explicitly retargeted.

## Git and lane safety
- Preserve local dirt/checkpoints before branch switches, pulls, merges, rebases, or shutdown. Prefer scoped stashes/checkpoints when appropriate.
- Do not use `git reset --hard` or discard uncommitted work unless the user explicitly authorizes deletion or the exact files are confirmed disposable.
- Work from the explicitly assigned worktree/branch for the lane; do not assume `/home/ggb66/dev/EVH` is the correct implementation worktree just because it is the current shell location.
- Before build, deploy, push, or release work, print/verify worktree path, branch, commit, and dirty state.
- A local main merge is not available to other agents via `git pull` until it is pushed to `origin/main`.

## Release and deployment hygiene
- EVH/RAG default release flow: make changes -> commit them -> build from the committed state -> test -> push when ready -> deploy.
- Do not deploy merely because tests pass. Confirm the intended source commit, worktree, branch, dirty state, package contents, artifact hash, and live validation evidence.
- Build/package into a fresh staging directory. Verify required dependencies and application files/routes inside the finished ZIP before upload.
- Record the source commit/worktree and ZIP/artifact SHA for every deployment.
- After AWS upload/deploy, download or inspect the deployed artifact and verify its hash/source contents before relying on live tests.
- Never silently remove a requested dependency or skip a vital check just to make packaging/tests/deploy appear green.
- Lambda environment updates are replacement operations: read and merge the complete existing `Variables` map before any update, then verify required keys immediately afterward.
- Audit-only means no edits and no deployments.

## Live-system validation and credentials
- When evaluating Instinct, Postgres, Lambda, or any other live-system behavior, use real payloads/logs/evidence; do not substitute mocks or stubs for live validation.
- If a vital environment piece is missing, record the exact missing artifact, owner, and next unblock step instead of silently skipping.
- Authoritative Instinct credential source for EVH/RAG local live tests and Lambda: AWS Secrets Manager secret `evh/instinct-api-credentials` in `us-east-1`. Never record secret contents.
- Approved RD importer/RAG Postgres bootstrap: source `~/dev/postgress_connection.zsh`; if it is missing, stale, or fails, report that exact blocker rather than guessing alternate credentials.

## RAG/Lambda packaging and runtime notes
- Known-good Lambda fat-ZIP shape has dependencies at ZIP root plus `scripts/`; do not put dependencies under `python/` unless building a Lambda Layer.
- Inspect packaged dependencies/files/routes before deploy and verify the deployed artifact afterward.
- Patient chunk retrieval should remain uncapped; do not reintroduce arbitrary `LIMIT`/`top_k` caps into retrieval requirements. Retrieval and evidence selection are separate stages.
- If OpenAI Responses returns `status=incomplete` with `reason=max_output_tokens`, retry once with a larger output budget before treating the answer as final failure.
- Preserve known-good deployed behavior unless the user specifically asks to change it.

## Importer and long-running jobs
- RD importer lane owns cron/latest client-patient sync, missing-document RAG ingestion, OCR fallback for no-text-layer PDFs, Word-document handling, and the multiple text/OCR source variants.
- For large processing programs, add or propose ETA/time-remaining reporting from live throughput so long runs have observable progress.
- Preserve checkpoints/logs/artifacts for importer work; do not restart or clean up long-running jobs from stale elapsed text alone.

## Deployed-codepath bug workflow
- For deployed behavior bugs, first identify the deployed owner/branch/codepath and current artifact before patching.
- For the Process_Emails_for_EVH email-link issue, the team-level expectation is universal mail links rather than Gmail-specific links; Rarity owns the current investigation unless retargeted.
