# Inventory Ally + Stockroom rollout plan

## Goal

Use Inventory Ally (IA) and Instinct Stockroom safely in parallel during transition, with Instinct / Stockroom as the intended long-term system of record. The remaining decision is whether EVH should:

- fully migrate operational inventory ownership from IA to Stockroom
- keep IA in a limited secondary role with a tightly bounded responsibility
- or narrow the coexistence period if IA no longer adds enough operational value

This plan assumes IA is the incumbent inventory workflow, Stockroom is the new Instinct-side inventory capability, and EVH intends Instinct to become the inventory system of record.

## Core principles

- Do not start with unrestricted dual-write.
- Instinct / Stockroom is the target system of record.
- During transition, define one temporary owner for each workflow and field until cutover is complete.
- Prefer one-way synchronization during rollout.
- Require idempotent imports, audit logs, and reconciliation reports.
- Treat discrepancies as process issues to resolve explicitly, not as noise to ignore.

## Recommended initial ownership

Start with a controlled transition model:

- Instinct / Stockroom as the target source of truth
- IA as the incumbent operational source during transition only where needed
- a phased handoff from IA-owned workflows to Stockroom-owned workflows

That means:

- EVH should decide workflow-by-workflow when Stockroom becomes the posting system
- IA should be treated as a transition system, not the desired long-term owner
- no workflow should be posted independently in both systems at the same time

## Workflow ownership model

Use this as the initial baseline. Adjust only with an explicit decision.

| Workflow / data area | Transition owner | Secondary system role | Notes |
| --- | --- | --- | --- |
| Item master identity | IA initially, then Stockroom | Mirror as needed during cutover | Plan explicit cutover to Stockroom-owned identity |
| Vendor mappings | IA initially, then Stockroom | Mirror as needed during cutover | Keep vendor code normalization explicit |
| Units of measure / pack size | IA initially, then Stockroom | Mirror as needed during cutover | No independent edits in both systems |
| On-hand quantity | IA initially, then Stockroom by pilot wave | Read-only mirror in non-owner system | Critical anti-dual-write rule |
| Receiving | IA initially, then Stockroom by pilot wave | Mirror transaction history | Shift posting authority only after parity review |
| Adjustments / shrink / waste | IA initially, then Stockroom by pilot wave | Mirror transaction history | Every adjustment needs source attribution |
| Cycle counts | IA initially, then Stockroom by pilot wave | Compare-only in non-owner system | Do not post counts in both systems |
| Purchase orders / replenishment | IA initially, then Stockroom if validated | Recommendation-only or read-only in non-owner system | Promote only after accuracy review |
| Reporting / dashboards | Shared | Shared | Duplicate reporting is acceptable if definitions match |
| Instinct-native downstream workflows | Stockroom or Instinct sidecars | Consume mirrored inventory state | Keep boundary explicit |

## Field ownership rules

Default rules:

- identity fields: one owner only
- quantity fields: one owner only
- reorder settings: one owner only per location
- timestamps and audit metadata: preserve both source and integration timestamps
- no `latest_timestamp_wins` default for overlapping operational fields

Every synchronized record should carry:

- `source_system`
- `source_record_id`
- `source_version` or source update timestamp
- `synced_at`
- raw payload snapshot or equivalent audit blob for troubleshooting

## Matching and idempotency

Primary match key order:

1. existing explicit IA-to-Stockroom mapping record
2. canonical item SKU
3. vendor item code + pack size + location
4. manual review queue for anything ambiguous

Rules:

- do not auto-merge ambiguous items
- every import must be idempotent on stable source key
- compare normalized payload hashes before writing to suppress no-op updates
- preserve inactive items instead of hard-deleting immediately

## Rollout phases

### Phase 0: discovery and mapping

Produce:

- complete workflow inventory for current IA usage
- item and location key map
- field ownership matrix
- variance tolerance definitions
- rollback and cutover contacts

Questions to answer in this phase:

- Which IA workflows are actually used today at EVH?
- Which Stockroom workflows are required on day one versus later?
- Is Stockroom needed for operational inventory work, reporting, Instinct-native integrations, or all three?
- Which fields in Stockroom cannot be cleanly derived from IA?

Exit criteria:

- approved ownership matrix
- approved key mapping strategy
- approved reconciliation metrics

### Phase 1: shadow mode

Keep IA operational where required during transition. Feed Stockroom from IA exports, sync jobs, or approved integration paths while preparing Stockroom to assume ownership.

Run reconciliation at least daily for:

- item master parity
- on-hand quantity variance
- cost variance
- open PO variance
- adjustment totals
- inactive/discontinued item parity

Track:

- number of unmatched items
- number of quantity discrepancies
- number of manual corrections required
- sync latency

Exit criteria:

- parity within agreed tolerance for at least 2 consecutive weeks
- no unresolved critical mismatch patterns
- staff can use Stockroom reliably in preparation for workflow handoff

### Phase 2: bounded pilot

Choose one limited slice:

- one location
- one inventory category
- or one bounded workflow such as replenishment recommendations

Pilot principle:

- only one system can post final operational writes for the pilot workflow
- the other system remains mirror, compare, or recommendation-only

Recommended pilot order:

1. Stockroom recommendations only
2. Stockroom reporting plus exception review
3. Stockroom operational posting for one bounded workflow or location wave

Exit criteria:

- no unexplained drift beyond tolerance
- staff task completion time is acceptable
- purchasing or replenishment results are at least as good as IA
- exception handling is operationally sustainable

### Phase 3: decision gate

At the end of the pilot, choose one of three paths.

#### Option A: migrate from IA to Stockroom

Choose this only if Stockroom:

- covers day-to-day operational workflows adequately
- improves or preserves accuracy
- reduces duplicate work
- provides material Instinct-side value
- does not create unacceptable manual reconciliation cost

#### Option B: keep both with a stable split

Choose this only if:

- each system has a clearly bounded responsibility
- there is no uncontrolled dual-write
- sync direction is mostly one-way or tightly allowlisted
- staff are not maintaining the same operational state twice
- IA keeps only a limited secondary role after Stockroom becomes the record of authority

#### Option C: stop or narrow Stockroom use

Choose this if:

- parity cannot be maintained reliably
- Stockroom does not add enough operational or reporting value
- dual-system overhead outweighs the benefit

### Phase 4: migration, if warranted

Cut over by workflow or location wave, not by all inventory behavior at once.

Recommended cutover sequence:

1. freeze item master changes for a short window
2. run final IA vs Stockroom reconciliation
3. resolve critical discrepancies
4. switch one workflow or location wave at a time to Stockroom ownership
5. keep IA read-only for historical lookup and rollback support
6. monitor daily during stabilization

Stabilization period:

- 2 to 4 weeks minimum

## Decision scorecard

Use a simple red/yellow/green score against each category:

- transaction accuracy
- on-hand parity
- staff speed
- training burden
- purchasing quality
- reporting quality
- Instinct integration value
- support burden
- reconciliation effort
- readiness to retire IA ownership in each workflow

Migration should not proceed on a mostly yellow scorecard.

## Risks to avoid

- both systems editing on-hand quantity
- mismatched item identifiers across locations
- unmanaged unit-of-measure conversions
- silent overwrite rules
- no review queue for ambiguous matches
- no audit trail for sync activity
- reporting definitions that do not match operational calculations

## Governance and operating cadence

Recommended cadence during rollout:

- daily discrepancy review during shadow mode
- weekly rollout review with operations and technical owners
- explicit sign-off at each phase gate

Recommended owners:

- operations owner for inventory workflow decisions
- technical owner for integration and reconciliation logic
- clinic sponsor for cutover approval

## Ownership matrix template

Fill this out before implementation expands.

| Workflow / field | IA | Stockroom | System of record | Sync direction | Match key | Conflict rule | Current phase | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Item master | Yes | Yes | IA | IA -> Stockroom | SKU | IA wins | Phase 1 | |
| On-hand quantity | Yes | Yes | IA | IA -> Stockroom | SKU + location | IA wins | Phase 1 | |
| Reorder point | Yes | Yes | TBD | TBD | SKU + location | Manual until decided | Phase 0 | |
| Purchase order | Yes | Yes | IA initially | IA -> Stockroom or none | PO number | IA wins | Phase 1 | |
| Reporting metric definitions | Yes | Yes | Approved metric spec | Compare only | Metric ID | Manual review | Phase 1 | |

## Immediate next steps

1. Confirm the first workflow or location wave that will move into Stockroom ownership.
2. Inventory the exact IA workflows EVH uses today that still need transition handling.
3. Complete the ownership matrix for item master, on-hand quantity, receiving, adjustments, and purchase orders.
4. Define variance tolerances for shadow-mode reconciliation and cutover readiness.
5. Implement or document the minimum audit trail required for every synced write.
