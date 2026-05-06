# Inventory Ally to PIMS Mapping Export

Eustis Veterinary Hospital

This file consolidates the 16-page Inventory Ally mapping export into a single working document for reconciliation.

## Source Notes

- Source: IA mapping report pages 1 through 16, pasted in-thread
- Purpose: PIMS mapping rules for Eustis Veterinary Hospital
- Use: deterministic reconciliation against Stockroom / Instinct
- Important: this is the mapping export, not the counts report

## Key Reconciliation Rules

1. PIMS ID exact match
2. Supplier Product ID exact match
3. Supplier + normalized name match
4. Normalized name exact match
5. Fuzzy match
6. Human review

## Consolidated Page Coverage

- Pages 1 through 16 were received
- The export includes the full alphabetical IA item mapping set shown in-thread
- Repeated history anchors and size variants are present and must be handled as family matches, not automatic duplicates

## Notable Code Families

- `IADQ` Adequan
- `APOQT3.6` / `APOQT5.4` / `APOQT16` Apoquel
- `CYTO` Cytopoint
- `DERMI` Dermatonin
- `NERVBLK` Marcaine / Lidocaine nerve block
- `COMF24` / `COMF60` / `MARO16` ComforTrate
- `GALL20T` / `IGAL60` / `GALL100` Galliprant
- `IREG` / `IREG5` / `METOL` Metoclopramide
- `IRIM25` / `IRIM75` / `IRIM10` Carprofen
- `DENCHADL` / `DENCHADV` Denamarin
- `FEL2.5` / `IMET5` Felimazole / Methimazole
- `IFAM10` / `IFAM20` Famotidine
- `ILAS12` / `ILAS50` / `LAS20` Furosemide
- `IBAY60` / `IBAY13` Enrofloxacin
- `ORAVCS` / `ORAVCM` / `ORAVCL` / `ORAVCXS` OraVet

## UoM Normalization Flags

- Mixed `count`, `tablet`, `dose`, `ou`, `box`, `bag`, `case`, `order unit`
- Mixed buying/selling unit labels
- Some rows embed conversion text in the item name

## Working Output

This file exists as the single consolidated source for the 16-page IA mapping export and should be used for the next round of row-by-row reconciliation.
