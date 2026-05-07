# Rarity Workfile

Project: EVH
Branch: pony/rarity/main

Status: assigned
Scope: Stockroom
Permissions granted: none recorded
- user instruction recorded: when handed page-by-page data, save it into a real file instead of creating a stub or summary placeholder
Notes:
- primary area: stockroom workflows and related EVH integration work
- owned script directory: `scripts/stockroom/`
- branch policy: work only on Rarity-owned branches in the `pony/rarity/*` namespace; do not do Stockroom implementation work on shared root branches
- keep the workfile current with the active Stockroom subtask before starting implementation
- current stop point: refreshed the supplier mapping reference and kept the base stockroom CSV as the active checked-in input
- active subtask: stockroom CSV support is active; supplier mapping data is ready for the next requested transform
- routing note: user guidance says Rarity should stay on `pony/rarity/main` for Stockroom, so no branch move is needed unless Twilight updates the assignment registry
- current input: `docs/Stockroom · Instinct Stockroom.csv`, plus refreshed supplier reference docs at `docs/manufacturer-supplier-mapping.csv` and `docs/manufacturer-supplier-mapping.md`
- next step: wait for the user to specify whether to inspect or transform the stockroom CSV using the refreshed supplier mapping reference
