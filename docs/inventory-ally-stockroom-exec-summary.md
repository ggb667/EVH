# Inventory Ally + Stockroom executive summary

## Recommendation

EVH intends Instinct / Stockroom to become the inventory system of record, but should not cut over all workflows immediately.

The recommended path is:

1. establish Stockroom as the target system of record
2. use IA as the transition system only where current operations still depend on it
3. move workflows or location waves into Stockroom in a controlled sequence
4. keep IA only if it retains a narrow, justified secondary role

## Why this approach

Running both systems without explicit ownership would create avoidable risk:

- conflicting quantity updates
- duplicate staff entry
- reconciliation burden
- unclear accountability when counts differ

Using IA as a transition owner for selected workflows protects current operations while EVH moves deliberately toward Stockroom ownership.

## What success looks like

Stockroom is the destination system of record, but each workflow still needs a controlled handoff.

EVH should move each workflow from IA to Stockroom only if Stockroom proves that it can:

- support the required daily workflows
- maintain quantity and item parity within agreed tolerances
- reduce or at least not increase staff effort
- improve reporting, replenishment, or Instinct-native workflows enough to justify the change

EVH should keep both systems only if IA retains a stable, non-overlapping secondary role after Stockroom becomes authoritative.

## Recommended operating model

Transition model:

- Stockroom is the target owner
- IA temporarily owns only workflows not yet cut over
- no unrestricted dual-write

Recommended initial ownership:

- item master: transition from IA to Stockroom
- on-hand quantity: transition from IA to Stockroom by wave
- receiving: transition from IA to Stockroom by wave
- adjustments and waste: transition from IA to Stockroom by wave
- purchase orders and replenishment: transition after validation
- Instinct-native downstream uses of inventory data: Stockroom may consume mirrored data

## Decision paths

At the end of shadow mode and pilot validation, EVH should choose the final operating posture.

### Path A: migrate to Stockroom

Choose this if Stockroom is operationally complete and clearly valuable.

### Path B: keep both

Choose this only if responsibilities stay cleanly separated. Example:

- Stockroom becomes the authoritative inventory system
- IA remains only for legacy reporting, historical lookup, or a tightly bounded secondary workflow

### Path C: narrow or stop Stockroom rollout

Choose this if parity is unreliable, staff burden rises, or the added value is too small.

## Recommended timeline

- Phase 0: workflow and ownership mapping
- Phase 1: shadow mode with reconciliation
- Phase 2: bounded pilot for one location wave, category, or workflow handoff
- Phase 3: executive decision gate
- Phase 4: phased migration only if justified

## Metrics leadership should monitor

- item master parity
- on-hand variance
- adjustment variance
- purchase order accuracy
- staff time per core workflow
- training and support burden
- number of manual corrections required
- measurable Instinct-side value created by Stockroom

## Decision rule

Do not approve broad cutover on promise alone.

Approve migration only after:

- at least 2 weeks of stable shadow-mode parity
- a successful bounded pilot
- a clear operational owner for each workflow during transition and after cutover
- a rollback path that keeps IA available in read-only mode during stabilization

## Supporting document

Detailed rollout and governance guidance:

- `docs/inventory-ally-stockroom-rollout-plan.md`
