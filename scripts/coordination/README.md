# EVH Coordination

Owned by Twilight for coordinator-support EVH work.

This directory is the repo-local control surface for EVH worker coordination.
Use it when multiple workers are active or when a task needs a durable handoff.

## Files

- `TASK_BOARD.md`: live assignment board and status ledger.
- `TASK_TEMPLATE.md`: template for opening a new worker assignment.
- `HANDOFF_TEMPLATE.md`: required structure for worker closeout notes.
- `COORDINATOR_CHECKLIST.md`: checklist for Twilight or a coordinator agent.

## Workflow

1. Open `TASK_BOARD.md`.
2. Add a new task block from `TASK_TEMPLATE.md`.
3. Assign one clear owner and define deliverables, dependencies, and stop
   conditions.
4. Require the worker to leave a closeout note using `HANDOFF_TEMPLATE.md`.
5. Update the task status as soon as it moves between `queued`, `active`,
   `blocked`, `review`, and `done`.

## Rules

- One owner per task. Reviewers and helpers can be listed separately.
- Keep task descriptions concrete enough that another worker can take over.
- Record blockers immediately; do not leave blocked work marked `active`.
- A task is not `done` until the board links to the final artifact or note.
- If work changes repo state, the handoff must name the touched files and any
  verification that was or was not run.
