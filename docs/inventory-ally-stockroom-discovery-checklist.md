# Inventory Ally + Stockroom discovery checklist

## Purpose

Use this checklist to gather the missing facts needed to move EVH from planning into a safe Instinct / Stockroom rollout.

This is designed for situations where the operator does not know every workflow detail offhand, but Inventory Ally (IA), Instinct, or their admins can provide the answers.

## Current planning assumptions

- Instinct / Stockroom is the target system of record
- IA is the incumbent system used during transition
- cutover should happen by workflow or location wave
- room-only tracking is the current planning assumption for EVH
- manual location creation in Stockroom is acceptable because the location count is small
- EVH locations identified so far:
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

## What to collect first

Get whichever of these is easiest:

- screenshots of IA workflows actually used at EVH
- screenshots of Instinct Stockroom workflows available to EVH
- item export from IA
- item export from Stockroom
- any report showing on-hand by location
- any report showing receiving, adjustments, purchase orders, or reorder settings
- names of the staff members who use each system most heavily

Do not wait for perfect documentation. A few exports and screenshots are enough to complete the first real ownership pass.

## IA discovery questions

Confirm which of these IA workflows exist and are actively used:

- item master creation and editing
- vendor item mapping
- unit of measure and pack size setup
- on-hand quantity tracking
- receiving
- adjustments
- waste or expired item handling
- cycle counts
- transfers between locations
- reorder points or min-max settings
- purchase order creation
- purchase order receiving / closing
- invoice matching
- inventory reporting

Already confirmed active from current evidence:

- vendor item mapping, used as PIMS mapping
- unit of measure and pack size setup
- on-hand quantity tracking via counts and estimated quantities
- cycle counts via the Counting page / weekly list
- inventory reporting via Inventory Analysis export

For each active IA workflow, collect:

- workflow name as shown in IA
- who uses it
- which EVH locations use it
- whether it changes quantity
- whether it changes item master data
- whether it produces a report or export
- whether it has a stable transaction ID or record ID

## Stockroom discovery questions

Confirm which of these Stockroom workflows exist and are available in your tenant:

- item master creation and editing
- location setup
- quantity tracking by location
- receiving
- adjustments
- waste handling
- counts
- transfers
- reorder settings
- replenishment recommendations
- purchase orders
- reporting
- audit history

Already confirmed from current evidence:

- quantity tracking by location / room
- one item can exist in multiple rooms
- room-only tracking is valid without bins or shelves
- locations are created in Admin with `Code` and `Label`
- buying-unit to selling-unit conversion exists
- cycle count and inventory history exports exist
- analytics exports exist

For each available Stockroom workflow, collect:

- workflow name as shown in Stockroom
- whether EVH has access today
- whether it is ready for operational use or still exploratory
- which locations it supports
- what identifiers it uses for items and transactions
- what export or API access exists
- whether it can be read-only during rollout

## Data model checklist

For both IA and Stockroom, identify the real fields for:

- item ID
- SKU
- item name
- vendor item code
- category
- unit of measure
- pack size
- location code
- on-hand quantity
- reorder point
- min-max values
- cost
- active / inactive flag
- transaction ID for receiving
- transaction ID for adjustments
- purchase order number

If the field names differ, capture the actual label used by each system.

## Location checklist

For each EVH location or stock area, confirm:

- exact location name in IA
- exact location name in Stockroom
- whether the location exists in both systems today
- whether inventory is actively tracked there today
- whether it should be in first wave or later wave

Use this table during discovery:

| EVH stock area | IA location name | Stockroom location name | Exists in IA | Exists in Stockroom | First wave | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| Treatment | | | | | | |
| Pharmacy | | | | | | |
| Reception | | | | | | |
| Lab | | | | | | |
| Kennel | | | | | | |
| Room 1 | | | | | | |
| Room 2 | | | | | | |
| Room 3 | | | | | | |
| Room 4 | | | | | | |
| Room 5 | | | | | | |
| Autoclave | | | | | | |
| X-Ray / Dental | | | | | | |

## Reports and exports to request

Request these from IA and Stockroom if available:

- item master export
- on-hand by location export
- receiving history export
- adjustment history export
- purchase order export
- reorder setting export
- inactive item export

Preferred format:

- CSV first
- XLSX if CSV is not available

## Pending Instinct-human questions

These have already been emailed and are awaiting response:

- supported migration path from Inventory Ally into Stockroom
- whether Stockroom can be used in practical shadow mode before cutover
- stable IDs for item, location, location-level inventory, cycle count events, and adjustment/history events
- supported import or mapping path for existing PIMS/vendor item mappings
- API endpoints for item master, location list, on-hand by location, count history, and inventory history / adjustments
- exact data model behavior when a cycle count is entered
- approval or review workflow for counts or adjustments
- whether location codes are stable integration keys
- how multi-room items are represented in exports and API responses

## Evidence that matters most

The most valuable evidence for finishing the ownership matrix is:

1. on-hand by room/location export from IA
2. item master export from IA
3. Stockroom screen or export showing room-based quantity support
4. human confirmation of Stockroom API endpoint coverage and stable IDs
5. any IA or Stockroom transaction export with stable IDs

## Decision questions to answer from discovery

Discovery should let EVH answer:

- Which workflows are real versus assumed?
- Which workflows exist in both systems?
- Which workflows can move to Stockroom first without dual-write risk?
- Which locations are best for first-wave cutover?
- Which fields need mapping tables before sync starts?
- Which workflows should remain in IA temporarily during transition?

## Minimum discovery package for next planning step

You do not need everything. The next planning pass can proceed once EVH has at least:

- one IA item export
- one IA on-hand by location export
- confirmation of which first-wave locations exist in Stockroom
- one Stockroom workflow list or screenshot set

## Recommended next action

Have IA and Instinct provide screenshots, exports, or a short walkthrough covering:

- item setup
- quantity by location
- receiving
- adjustments
- reorder / replenishment
- purchase orders

Once that is collected, update:

- `docs/inventory-ally-stockroom-ownership-matrix.md`
- `docs/inventory-ally-stockroom-rollout-plan.md`
