# Rarity Workfile

Project: EVH
Branch: pony/rarity/main

Status: assigned
Scope: Meds & Treatments
Permissions granted: none recorded

Artifact: docs/stockroom-merged-stockroom-ur.csv
- current RAG assignment: shared dictionary seed is already delivered and loaded; do not retry the same seed path unless assigned
- shared dictionary load state: AJ worker-side status reports the merged seed was loaded into Handshake's Aurora MySQL/MariaDB-compatible database and verified at 3,133 rows
- user instruction recorded: when handed page-by-page data, save it into a real file instead of creating a stub or summary placeholder
- user instruction recorded: for fuzzy supplier matches, use product-name text matching to populate `Suppliers` while preserving the stockroom numeric fields as-is
- user instruction recorded: use `view.pushHookEvent(el, null, "live_fetch.update_global_product", payload, callback)` from the `product-catalog` LiveView root to perform backend updates; only vary `payload.id`, `payload.params.suppliers`, `payload.params.buying_cost`, `payload.params.unit` fields, and `payload.params.emr_products`; do not use `execJS`
- current working abstraction: intercept `view.pushHookEvent` on the `product-catalog` LiveView root and log every outgoing `live_fetch.*` event plus reply into `window.__stockroomWireLog`
- current working interceptor:
  ```javascript
  (() => {
    const el = document.getElementById("product-catalog");
    const view = Object.values(window.liveSocket.roots).find(v => v.el && v.el.contains(el));

    if (!view) throw new Error("Could not locate LiveView root");
    if (typeof view.pushHookEvent !== "function") throw new Error("view.pushHookEvent not found");

    const orig = view.pushHookEvent.bind(view);
    window.__stockroomWireLog = [];

    view.pushHookEvent = function(el, ref, event, payload, callback) {
      const snap = typeof structuredClone === "function"
        ? structuredClone(payload)
        : JSON.parse(JSON.stringify(payload));

      window.__stockroomWireLog.push({
        ts: new Date().toISOString(),
        kind: "pushHookEvent",
        event,
        payload: snap,
        elId: el?.id ?? null,
        ref: ref ?? null,
      });

      console.log("[Stockroom wire]", event, snap);

      return orig(el, ref, event, payload, function(reply, pushRef) {
        window.__stockroomWireLog.push({
          ts: new Date().toISOString(),
          kind: "reply",
          event,
          reply,
          pushRef,
        });
        console.log("[Stockroom reply]", { event, pushRef, reply });
        return callback?.(reply, pushRef);
      });
    };

    console.log("Stockroom hook wire logging enabled");
  })();
  ```
Notes:
- primary area: stockroom workflows and related EVH integration work
- owned script directory: `scripts/stockroom/`
- branch policy: work only on Rarity-owned branches in the `pony/rarity/*` namespace; do not do Stockroom implementation work on shared root branches
- keep the workfile current with the active Stockroom subtask before starting implementation
- active subtask: build a strict CSV generator that matches `Instinct_Stockroom.csv` rows against `EVHInventorySuppliers.xlsx` by item code, description, and parsed secondary IDs
- routing note: user guidance says Rarity should stay on `pony/rarity/main` for Stockroom, so no branch move is needed unless Twilight updates the assignment registry
- current input: `Instinct_Stockroom.csv`, `Instinct_Stockroom_with_supplier_matches.csv`, `stockroom_suppliers_ids.csv`, and the Stockroom browser bundle under `Stockroom · Instinct Stockroom_files/`
- current stop: merged Stockroom row emitter is in place and verified; generated `/tmp/rarity-stockroom-merged.csv` with 1,041 rows and both targeted tests passed in the venv
- current stop: browser replay snippet generator now consumes the merged UR columns (`Buying Unit ID`, `Selling Unit ID`, `Supplier Payload`, `EMR Product IDs`) instead of the stale placeholder schema, and the targeted replay/emitter tests pass in the venv
- blocker: none
- next step: load the emitted helper in the browser and use `__loadStockroomReplayRows()` / `__updateStockroomReplayByPimsId()` for row-level replay if more capture work is needed
