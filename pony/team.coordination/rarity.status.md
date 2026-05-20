AUDIENCE: EVERYONE
BRANCH: pony/rarity/main
WORKTREE: /home/ggb66/dev/EVH/pony/worktrees/rarity
WORKFILE: [pony/work/rarity.md](../work/rarity.md)
BRANCH_VERIFIED: yes
STATUS: ASSIGNED
PUSH_STATUS: clean_local_branch
APPROVALS: none recorded
NOTES: user instruction recorded - when handed page-by-page data, save it into a real file instead of creating a stub or summary placeholder
NOTES: user instruction recorded - for fuzzy supplier matches, use product-name text matching to populate Suppliers while preserving the stockroom numeric fields as-is
NOTES: user instruction recorded - use `view.pushHookEvent(el, null, "live_fetch.update_global_product", payload, callback)` from the `product-catalog` LiveView root for backend updates; vary only `payload.id`, `payload.params.suppliers`, `payload.params.buying_cost`, `payload.params.unit` fields, and `payload.params.emr_products`; do not use `execJS`
NOTES: current working abstraction - intercept `view.pushHookEvent` on the `product-catalog` LiveView root and log every outgoing `live_fetch.*` event plus reply into `window.__stockroomWireLog`
NOTES: current working interceptor - wraps `view.pushHookEvent`, clones each payload, records `{event,payload,elId,ref}`, and logs replies with `pushRef`
FILES_PLANNED: none
FILES_TOUCHED: pony/work/rarity.md, pony/team.coordination/rarity.status.md, docs/inventory-ally-stockroom-ownership-matrix.md, docs/inventory-ally-stockroom-discovery-checklist.md, pony/team.coordination/twi.mailbox.md, pony/team.coordination/spike.mailbox.md
BLOCKERS: none
CURRENT_STOP: browser replay helper now emits a self-contained supplier lookup and loads the merged UR file
FILES_PLANNED: docs/stockroom-merged-stockroom-ur.csv
FILES_TOUCHED: pony/work/rarity.md, pony/team.coordination/rarity.status.md, scripts/stockroom/emit_merged_stockroom_rows.py, tests/test_emit_merged_stockroom_rows.py, docs/stockroom-merged-stockroom-ur.csv
BLOCKERS: none
NEXT_STEP: continue the browser replay helper flow from `docs/stockroom-merged-stockroom-ur.csv` if more row-level replay work is needed
NOTES: emitter verified in the venv; `/tmp/rarity-stockroom-merged.csv` was generated with 1,041 rows and the targeted Stockroom tests passed
QUESTIONS_FOR_TWI: none
DECISION_NEEDED: none
