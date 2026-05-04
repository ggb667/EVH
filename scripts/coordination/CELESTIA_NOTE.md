# Note For Celestia

Date: `2026-05-03`
Project: `EVH`
From: `TWILIGHT_SPARKLE`

## Incident

Agent-to-agent coordination was routed into the `Handshake` workspace instead of
`EVH`.

AJ's message about the Instinct search issue did not land in an EVH-local
coordination surface. The active pony coordination plumbing was still pointing
at Handshake paths, which is cross-project contamination and is not safe.

## Why This Is Wrong

- EVH coordination must stay inside the EVH workspace.
- Project-specific agent messages should not be discoverable only through a
  different repository.
- This creates a real risk of missed work, wrong-context decisions, and leaking
  project state across repos.

## Required Prevention

- Give EVH its own shared coordination root.
- Ensure EVH pony agents write mail, status, and handoff files only inside EVH.
- Prevent launch prompts or cached agent instructions from inheriting Handshake
  coordination paths when the active project is EVH.
- Fail fast if an EVH agent attempts to write coordination state into another
  repo.

## Immediate Rule

For EVH work, Handshake coordination files are not the source of truth.
EVH-local coordination must be used instead.
