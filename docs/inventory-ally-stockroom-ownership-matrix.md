# EVH Inventory Ally + Stockroom ownership matrix

## Purpose

This is the working EVH matrix for deciding which system owns each inventory workflow during rollout.

Current status:

- IA is assumed to be the current operational inventory system
- Stockroom is assumed to be the new Instinct-side capability under evaluation
- Instinct / Stockroom is the intended system of record
- EVH-specific workflows below are proposed transition defaults and should be confirmed with operations before implementation expands

## Working assumptions

- EVH should avoid unrestricted dual-write
- Stockroom is the target system of record
- one system should own each operational quantity-changing workflow at any point in time
- Stockroom should begin in shadow mode unless a narrower pilot is explicitly approved
- reporting can exist in both systems if the metric definition is shared and reconciled
- room-only tracking is the current EVH planning assumption; sub-location tracking is not in scope for the first rollout wave
- manual location creation in Stockroom is acceptable because the location count is small

## EVH stock areas currently identified

The following EVH stock areas have been identified for rollout planning:

- Treatment
- Pharmacy
- Reception
- Lab
- Kennel
- Room 1
- Room 2
- Room 3
- Room 4
- Room 5
- Autoclave
- X-Ray / Dental

## Recommended first-wave pilot locations

Based on the current EVH guidance, the recommended first-wave Stockroom pilot locations are:

- Treatment
- Pharmacy
- Reception
- Lab
- Kennel

These appear to be the "first 5" areas most likely to be included in the initial pilot. Confirm this before operational cutover.

## EVH working matrix

| Workflow / field | IA in use | Stockroom in use | Transition owner -> target owner | Sync direction | Match key | Conflict rule | Rollout phase | EVH note |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Item master identity | Yes | Planned | IA -> Stockroom | IA -> Stockroom during transition | SKU or mapped item ID | transition owner wins until cutover | Phase 1 | Create explicit item mapping table before broad sync |
| Item description and category | Yes | Planned | IA -> Stockroom | IA -> Stockroom during transition | SKU | transition owner wins until cutover | Phase 1 | Normalize naming before parity reviews |
| Vendor item code / PIMS mapping | Yes | Planned | IA -> Stockroom | IA -> Stockroom during transition | SKU + vendor code | transition owner wins until cutover | Phase 1 | Confirmed active in IA; keep vendor aliases explicit |
| Unit of measure / pack size | Yes | Planned | IA -> Stockroom | IA -> Stockroom during transition | SKU + UOM | transition owner wins until cutover | Phase 1 | Confirmed active in IA; do not allow silent unit conversion |
| Location / stock area mapping | Yes | Planned | IA -> Stockroom | IA -> Stockroom during transition | location code | Manual review if ambiguous | Phase 0 | Initial EVH locations identified: Treatment, Pharmacy, Reception, Lab, Kennel, Room 1-5, Autoclave, X-Ray / Dental |
| On-hand quantity by room | Yes | Planned | IA -> Stockroom by wave | IA -> Stockroom until cutover, then Stockroom authoritative | SKU + location | current owner wins | Phase 1 | Confirmed active in IA via counts and estimated quantities; no direct Stockroom edits until the location wave is cut over |
| Receiving | Yes | Planned | IA -> Stockroom by wave | IA -> Stockroom until cutover | receiving transaction ID | current owner wins | Phase 1 | Mirror transactions for audit and parity |
| Adjustments / shrink / waste | Yes | Planned | IA -> Stockroom by wave | IA -> Stockroom until cutover | adjustment transaction ID | current owner wins | Phase 1 | Every adjustment needs source attribution |
| Cycle counts | Yes | Planned | IA -> Stockroom by wave | IA -> Stockroom, then Stockroom after cutover | SKU + location + count date | current owner wins | Phase 1 | Confirmed active in IA via Counting page / weekly list; Stockroom count sheet CSV exists but weekly routing parity is not yet confirmed |
| Reorder point / min-max settings | Yes | Planned | TBD -> Stockroom | TBD during evaluation | SKU + location | Manual review until owner chosen | Phase 0 | Strong candidate for early Stockroom ownership if recommendations are valuable |
| Purchase orders | Yes | Planned | IA initially -> Stockroom if validated | IA -> Stockroom or none until cutover | PO number | current owner wins | Phase 1 | Do not create POs independently in both systems |
| Replenishment recommendations | Yes | Planned | Shared evaluation -> Stockroom | Compare-only at first | SKU + location + run date | Manual review | Phase 2 | Good first bounded Stockroom pilot |
| Inventory reporting | Yes | Planned | Shared metric definition | Compare reports | metric ID + period | Manual review on variance | Phase 1 | Confirmed active in IA via Inventory Analysis export |
| Instinct-native downstream inventory workflows | No or limited | Planned | Stockroom-consumer side | IA -> Stockroom | mapped item ID | Stockroom consumes mirrored state only | Phase 1 | Define exactly which Instinct workflows require this |
| Historical lookup after cutover | Yes | Planned | IA read-only if migration happens | none | legacy IDs | IA retained for history | Phase 4 | Keep rollback path intact during stabilization |

## Recommended pilot candidates

Best first pilots:

1. Stockroom replenishment recommendations without final posting authority
2. Stockroom reporting and discrepancy review
3. one bounded category or location wave for Stockroom operational posting after parity is proven

Recommended EVH first-wave location set:

1. Treatment
2. Pharmacy
3. Reception
4. Lab
5. Kennel

Recommended EVH second-wave location set after first-wave stability:

1. Room 1
2. Room 2
3. Room 3
4. Room 4
5. Room 5
6. Autoclave
7. X-Ray / Dental

Avoid as first pilot:

- full on-hand ownership
- global purchase order ownership
- simultaneous posting of counts in both systems

## Reconciliation metrics

Track at minimum:

- unmatched item count
- on-hand quantity variance by SKU and location
- receiving variance
- adjustment variance
- open PO variance
- manual correction count
- sync lag

Recommended minimum tolerances should be defined by EVH operations before the pilot starts.

## Confirmed findings so far

- IA workflows confirmed active from available evidence:
  - vendor item mapping / PIMS mapping
  - unit of measure and pack size setup
  - on-hand quantity tracking via counts and estimated quantities
  - cycle counts via Counting page / weekly list
  - inventory reporting via Inventory Analysis export
- Stockroom capabilities confirmed from available evidence:
  - quantity on hand by room / inventory location
  - one item can exist in multiple rooms
  - room-only tracking is valid without bins or shelves
  - locations are managed by `Code` and `Label`
  - buying-unit to selling-unit conversion is supported
  - exports exist for cycle counts, inventory history, and analytics
- Open Instinct-human questions have been emailed and are pending response:
  - supported migration path from IA
  - practical shadow mode support
  - stable identifiers
  - API endpoint coverage
  - PIMS mapping import / migration support
  - exact cycle count data behavior
  - approval or review workflow for counts and adjustments
  - location code stability as integration keys
  - multi-room representation in exports and API responses

## Open decisions EVH still needs to make

- Which exact IA workflows are used today at EVH?
- Which Stockroom features are required in the first rollout wave beyond room-level counting?
- Confirm whether the first pilot location set is Treatment, Pharmacy, Reception, Lab, and Kennel
- Should reorder settings remain in IA or become a Stockroom-owned pilot area?
- Which reporting definitions will be treated as authoritative during shadow mode?

## Immediate next working session

Use this matrix to fill in:

1. confirm the first-wave location list
2. capture the human response from Instinct on IDs, APIs, migration path, and shadow mode
3. refine the room-level on-hand and cycle-count pilot scope
4. define variance tolerances and sign-off owners
5. decide whether reorder settings stay in IA for the first wave
