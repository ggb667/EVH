# Inventory Ally to Stockroom Reconciliation

This document turns the supplied Inventory Ally mapping export into an operational reconciliation view.

## Matching Rules

Authoritative match order:

1. PIMS ID exact match
2. Supplier Product ID exact match
3. Supplier + normalized name match
4. Normalized name exact match
5. Fuzzy match
6. Human review

## PIMS Duplicate Anchors

These are not duplicate products in the business sense. They are repeated PIMS anchors that appear across multiple Inventory Ally rows, usually because the same therapeutic family has multiple strengths or packaging variants.

| PIMS Product | Product Code | IA Rows / Variants |
|---|---:|---|
| `Dermatonin Implant` | `DERMI` | 12mg, 18mg, 8mg |
| `Inject - Cytopoint` | `CYTO` | 10mg, 20mg, 30mg, 40mg |
| `Nerve Block ( Marcaine / Lidocaine Inj)` | `NERVBLK` | Marcaine 0.5% Injection, Lidocaine HCl Injection 2% |
| `Comfortrate` family | `COMF24`, `COMF60`, `MARO16` | 16mg, 24mg, 60mg |
| `Galliprant` family | `GALL20T`, `IGAL60`, `GALL100` | 20mg, 60mg, 100mg |
| `Metoclopramide` family | `IREG`, `IREG5`, `METOL` | 5mg tablets, 10mg tablets, oral solution |
| `Apoquel` family | `APOQT3.6`, `APOQT5.4`, `APOQT16` | 3.6mg, 5.4mg, 16mg |
| `Aurocin / Ear Flush / Epiklean` ear-cleanser family | `BEF`, `BEFC`, `IEEC` | 8oz variants and courtesy/generic anchors |
| `Cerenia` family | `ICERI`, `INJCER` | specific injectable row and broader injectable family anchor |
| `Cephalexin` family | `IKEF25`, `IKEF50` | 250mg, 500mg |
| `Carprofen` family | `IRIM25`, `IRIM75`, `IRIM10` | 25mg, 75mg, 100mg |
| `Denamarin` family | `DENCHADL`, `DENCHADV`, `IDENA4` | large vs small/medium, plus generic legacy anchor |
| `Gabapentin` family | `GABA300`, `IGAB100`, `GABA50MG`, `MISCRX` | capsules and oral solution variants |
| `Furosemide` family | `ILAS12`, `ILAS50`, `LAS20` | 12.5mg, 20mg, 50mg |
| `Enrofloxacin` family | `IBAY60`, `IBAY13` | 68mg, 136mg |
| `NexGard / NexGard PLUS / NexGard COMBO` families | multiple | size-based variant families with shared chemistry anchors |

## What `FIX_UOM` Means

`FIX_UOM` is required when the item match is probably correct, but the item is expressed in incompatible or inconsistent units.

Typical failures:

- IA uses `count`, `tablet`, `dose`, `ou`, `box`, `bag`, `pack`, `sleeve`, `case`, or `order unit` inconsistently
- Stockroom and IA disagree on buying unit vs selling unit
- The same product family uses different units across variants
- The calculated conversion is implied in text but not normalized into a single canonical ratio

Examples:

| IA Item | Issue | Required Fix |
|---|---|---|
| `Apoquel 3.6mg / 5.4mg / 16mg` | `count`, `tablet`, and `ou` are mixed across rows | Normalize to one buying unit and one selling unit per variant |
| `Cytopoint` family | all variants are `1 vial = 1 vial`, but size is only in the product name | Preserve strength-specific variant while normalizing unit text |
| `Furosemide 20mg` | `order unit = 100 count` in one row, `1 bottle = 100 count` in another | Canonicalize both to the same unit pair and conversion |
| `Galliprant` family | some rows are `1 bottle = 90 ou`, others are `1 bottle = 90 tablet` | Normalize the unit label and keep the numeric conversion |
| `Denamarin` family | `1 box = 4 bottle` appears alongside `0.31 box / EOW` | Normalize buying/selling units and preserve conversion |
| `Metoclopramide` family | oral solution row uses `1 bottle = 94.34 ou` | Convert to canonical `bottle -> mL` or `bottle -> each` rule before comparison |

## Completed Action Table

| Action Type | IA Item | PIMS Anchor | Product Code | Notes |
|---|---|---|---|---|
| `MAP_EXISTING` | 0.9% Sodium Chloride Injection, 1000mL | Fluid therapy family | `ILRN`, `350`, `IVFA` | Multiple history anchors; manual variant split required |
| `MAP_EXISTING` | Adequan Canine 100mg/mL | Adequan 100mg/ml INJ | `IADQ` | Direct family match |
| `MERGE_DUPLICATES` | Adequan family | Adequan 100mg/ml INJ / Inject - Adequan | `IADQ` / `169` | Duplicate therapeutic anchors |
| `MAP_EXISTING` | Albon 5% Oral Suspension 16oz | Albon Oral Suspension 5% 473ml Bottle | `IAOS1` | Strong match |
| `MAP_EXISTING` | Amlodipine Besylate 2.5mg | Amlodipine 2.5 mg TAB | `AMP2.5` | Strong match |
| `MAP_EXISTING` | Amoxi-Drop 15mL | Amoxi-drops 15ml | `IAMOD1` | Strong match |
| `MAP_EXISTING` | Amoxi-Drop 30mL | Amoxi Drops 30ml | `IAMOX3` | Strong match |
| `MAP_EXISTING` | Amoxicillin/Clavulanate 125mg | Amoxicillin/Clavulanate 125mg TAB | `AMOCL125` | Strong match |
| `MAP_EXISTING` | Amoxicillin/Clavulanate 375mg | Amoxicillin/Clavulanate 375mg TAB | `AMOCL375` | Strong match |
| `MAP_EXISTING` | Apoquel 3.6mg | Apoquel 3.6mg TAB | `APOQT3.6` | Strong match |
| `MAP_EXISTING` | Apoquel 5.4mg | Apoquel 5.4mg TAB | `APOQT5.4` | Strong match |
| `MAP_EXISTING` | Apoquel 16mg | Apoquel 16mg TAB | `APOQT16` | Strong match |
| `FIX_UOM` | Apoquel family | Apoquel family | `APOQT3.6`, `APOQT5.4`, `APOQT16` | Normalize count/tablet/ou expressions |
| `MAP_EXISTING` | Azithromycin oral suspension 30mL | Azithromycin Susp 200mg/5 ml (30cc) | `AZITHR` | Strong match |
| `MAP_EXISTING` | Azodyl 90 Count | Azodyl Small CAP (Kidney Supplement) | `ASCPS90` | Strong match |
| `MAP_EXISTING` | Benazepril HCl 5mg | Benazepril HCl 5 mg TAB | `BEN5` | Strong match |
| `MAP_EXISTING` | BD Oral Dispensing Syringe 1cc | Oral Dosing Syringe 1ml/cc | `IOS1` | Strong match |
| `MAP_EXISTING` | Betacilin Clav Drops 15mL | Amoxicillin/Clav. ( Betacillin ) 15 ml | `AMOXCB15` | Strong match |
| `MAP_EXISTING` | Carprovet 25mg / 75mg / 100mg | Carprofen ( Rimadyl ) family | `IRIM25`, `IRIM75`, `IRIM10` | Strength family match |
| `MERGE_DUPLICATES` | Carprofen 25mg | Carprofen ( Rimadyl ) 25mg variants | `IRIM25` | Same product, alternate text |
| `MAP_EXISTING` | Cerenia 10mg/mL, 20mL | Cerenia / Inject - Cerenia | `ICERI`, `INJCER` | Specific row and family row |
| `MAP_EXISTING` | Cefazolin Sodium 1g/vial | Inject - Antibiotic | `155` | Generic anchor; review recommended |
| `MAP_EXISTING` | Cefpoderm / Cefpodoxime 100mg and 200mg | Cefpodoxime family | `ICP100`, `ICEP200` | Strong match |
| `MAP_EXISTING` | Cephalexin 250mg / 500mg | Keflex family | `IKEF25`, `IKEF50` | Strong family match |
| `MAP_EXISTING` | Chlorhexidine 4% Scrub | Chlorhexidine 4% Scrub w/ Aloe | `ICS4A` | Strong match |
| `MAP_EXISTING` | Clindamycin 75mg / 150mg | Clindamycin family | `ICLT75`, `ICLT150` | Strong family match |
| `MAP_EXISTING` | Clopidogrel 75mg | Clopidogrel 75 mg TAB | `CLOP75TA` | Strong match |
| `MAP_EXISTING` | ComforTrate 16mg / 24mg / 60mg | Comfortrate family | `MARO16`, `COMF24`, `COMF60` | Strength family match |
| `MERGE_DUPLICATES` | ComforTrate 24mg / 60mg | Comfortrate duplicate history rows | `COMF24`, `COMF60` | Textual duplicates |
| `MAP_EXISTING` | Convenia 80mg/mL, 10mL | Inject - Convenia | `CONV` | Strong match |
| `MAP_EXISTING` | Cytopoint family | Inject - Cytopoint | `CYTO` | Variant from IA row, not product code |
| `MAP_EXISTING` | Denamarin large / small-medium | Denamarin family | `DENCHADL`, `DENCHADV` | Clear size split |
| `MAP_EXISTING` | Dentahex Oral Rinse 8oz | Dentahex Oral Rinse 8oz | `IDOR8` | Strong match |
| `MAP_EXISTING` | Deracoxib 75mg / 100mg | Deracoxib family | `DERCOX75`, `DERCOX` | Strong family match |
| `MERGE_DUPLICATES` | Dermatonin strengths | Dermatonin Implant | `DERMI` | One PIMS anchor for multiple strengths |
| `MAP_EXISTING` | Doxycycline 100mg | Doxycycline 100 mg TAB | `DOXY100` | Strong match |
| `MAP_EXISTING` | DOUXO S3 PYO Wipes | Douxo Chlorhexidine 3% PS Pads 30ct | `DCP30` | Strong match |
| `MAP_EXISTING` | Epi-Otic 8oz | EpiOtic Advanced Ear flush 8oz | `IEPIO` | Strong match |
| `MAP_EXISTING` | Epakitin 60g / 300g | Epakitin family | `IEPA60`, `IEPA3` | Strong family match |
| `MAP_EXISTING` | Entyce 30mg/mL 10mL | Entyce App Stimulant 30mg/ml 10ml Bottle | `ENT10BOT` | Strong match |
| `MAP_EXISTING` | Enrofloxacin 68mg / 136mg | Baytril family | `IBAY60`, `IBAY13` | Strength family match |
| `MAP_EXISTING` | Enalapril 5mg | Enalapril 5mg TAB | `IENA5` | Strong match |
| `MAP_EXISTING` | Elura 15mL | Elura 20mg/ml Oral Susp. (15 ml Bottle) | `ELURA15` | Strong match |
| `MAP_EXISTING` | EasOtic 10mL | Easotic ear Ointment 10ml | `EASOTIC` | Strong match |
| `MAP_EXISTING` | Feliway Multicat Diffuser | Feliway Multi Cat Starter Kit / Refill | `FELMSK`, `IFELR` | Family split by kit vs refill |
| `MAP_EXISTING` | Felimazole 2.5mg / 5mg | Felimazole family | `FEL2.5`, `IMET5` | Strength family match |
| `MAP_EXISTING` | Famotidine 10mg / 20mg | Famotidine family | `IFAM10`, `IFAM20` | Strength family match |
| `MAP_EXISTING` | Furosemide 12.5mg / 20mg / 50mg | Lasix family | `ILAS12`, `LAS20`, `ILAS50` | Strength family match |
| `MAP_EXISTING` | Gabapentin 100mg / 300mg / oral solution | Gabapentin family | `IGAB100`, `GABA300`, `GABA50MG` | Strength and formulation family |
| `MAP_EXISTING` | Galliprant 20mg / 60mg / 100mg | Galliprant family | `GALL20T`, `IGAL60`, `GALL100` | Family match |
| `MAP_EXISTING` | Genia Velfast E-Collars | Velfast E-Collar family | `VFEC25`, `VFSGE20`, `VFSGE15`, `VSGEC12`, `VFSGEC10`, `VFEC30` | Size family match |
| `MAP_EXISTING` | GenOne topical spray family | GenOne/Gentamicin topical spray family | `IGENSL`, `GENO60`, `IGENO120` | Volume family match |
| `MAP_EXISTING` | Gluture topical tissue adhesive | Gluture Tissue Adhesive | `IGLT` | Strong match |
| `MAP_EXISTING` | Groom Aid Spray | Groom Aid | `IGA` | Strong match |
| `MAP_EXISTING` | Heartgard Plus chewables | Heartgard Plus family | `IHGPSS`, `IHGPLS`, `IHGPMS` | Size family match |
| `MAP_EXISTING` | Hemo-Nate blood filter | Hemo Nate Blood Filter | `HNBF` | Strong match |
| `MAP_EXISTING` | Hydroxyzine 25mg / 50mg | Hydroxyzine family | `HYDXT25`, `HYDXT50` | Strength family match |
| `MAP_EXISTING` | Hydrogen Peroxide 3% | Hydrogen Peroxide Gal | `IHPG` | Strong match |
| `MAP_EXISTING` | Imagyst Cytology Coverslip | In House Cytology / Ear swab-cytology | `CYTI`, `228` | Generic lab supply anchor |
| `MAP_EXISTING` | Incurin Tablets | Incurin 1mg 30ct TAB | `INCURIN` | Strong match |
| `MAP_EXISTING` | Instrument Sterilization Pouch | Sterile Pouches ( pk 200 ) | `ISTRPCH` | Strong match |
| `MAP_EXISTING` | Isopropyl Alcohol 70% | Alcohol 70% Qt | `IA70` | Strong match |
| `MAP_EXISTING` | IV Extension Set | IV Extension Sets - 30" inch | `IIVE` | Strong match |
| `MAP_EXISTING` | IV Infusion Set | IV Infusion Set 5' Core Flex-Coil | `IVSCFC5` | Strong match |
| `MAP_EXISTING` | Kit4Cat Hydrophobic Sand Kit | Kit4Cat Urine Sample Collection Kit | `K4CUSCK` | Strong match |
| `MAP_EXISTING` | KMR Kitten Milk Replacer | KMR Powder 12oz | `IKMRP` | Strong match |
| `MAP_EXISTING` | Ketoconazole 200mg | Ketoconazole 200 mg TAB | `IKET200` | Strong match |
| `MAP_EXISTING` | Ketorolac 0.5% Ophthalmic Solution | Ketorolac 0.5% Opth. Solution | `KOS0.5` | Strong match |
| `MAP_EXISTING` | Kwik Stop Styptic Powder | Kwik Stop | `IKS` | Strong match |
| `MAP_EXISTING` | Lactated Ringers Injection Bag | LRS 1000ml Bag for Nebulization | `ILRN` | Generic fluid family; review recommended |
| `MAP_EXISTING` | Latex Exam Gloves | Gloves Exam family | `IS172`, `GES`, `GLEL` | Size family match |
| `MAP_EXISTING` | Librela 5mg / 15mg / 20mg / 30mg | Librela family | `LIB5`, `LIB15`, `LIB20`, `LIB30` | Weight band family match |
| `MAP_EXISTING` | Lidocaine HCl Injection 2% | Nerve Block ( Marcaine / Lidocaine Inj) | `NERVBLK` | Shared anchor with Marcaine |
| `MAP_EXISTING` | Marboquin 25mg | Marbofloxacin 25mg TAB | `ZN25T` | Strong match |
| `MAP_EXISTING` | Marcaine 0.5% Injection | Nerve Block ( Marcaine / Lidocaine Inj) | `NERVBLK` | Shared anchor with Lidocaine |
| `MAP_EXISTING` | Mask Level 3 Surgical Tie Anti Fog Foam Blue | Surgery Mask Tie | `IMASKTIE` | Strong match |
| `MAP_EXISTING` | Methimazole / Felimazole family | Methimazole family | `IMET5`, `FEL2.5`, `FELAN30` | Formulation and strength family |
| `MAP_EXISTING` | Metoclopramide 5mg / 10mg / oral solution | Metoclopramide family | `IREG5`, `IREG`, `METOL` | Strength/formulation family |
| `MAP_EXISTING` | Metronidazole 250mg / 500mg / injection | Metronidazole family | `IFLA25`, `IFLA50`, `155A` | Strong family match |
| `MAP_EXISTING` | MiconaHex+Triz Shampoo | Miconahex + Triz Shampoo 16oz | `MICTRIZ1` | Strong match |
| `MAP_EXISTING` | Mirtazapine 15mg / Mirataz | Mirtazapine family | `IMIR15`, `MIRTRAO` | Strength/formulation family |
| `MAP_EXISTING` | Monoject syringes | Flushing Syringe Curved Tip / Syringe 10ml | `ISRFL`, `ISR10` | Syringe family |
| `MAP_EXISTING` | Morax? no row; ignored |  |  |  |
| `MAP_EXISTING` | NexGard / NexGard PLUS / NexGard COMBO families | NexGard families | multiple | Size family match |
| `MAP_EXISTING` | Neopolydex / Neomycin-Polymyxin-B family | Ophthalmic ointment family | `INDD`, `INDO`, `ITRIOE`, `ITRIHC` | Ophthalmic family match |
| `MAP_EXISTING` | Neopolybac W/ Zinc | NeoPoly Bac Oph Oint 3.5 | `ITRIOE` | Strong match |
| `MAP_EXISTING` | NoSorb Litter | Nosorb 5 lb | `INS5` | Strong match |
| `MAP_EXISTING` | Normsol R Injection 7.4pH | CRI / Injection added to IV Fluids | `CRI`, `INJIV` | Generic fluid family |
| `MAP_EXISTING` | Nutri-Cal Supplement Gel | Nutrical 4.25 oz | `INUT` | Strong match |
| `MAP_EXISTING` | Nutramax Cosequin / Cobalequin / Naraquin | Nutramax family | `COSCC`, `COB12SL`, `COB12SUP`, `NAR60` | Brand family split by product |
| `MAP_EXISTING` | OB Lube Original NonSpermicidal Concentrate | OB Lube Concentrate Gallon | `OBLCG` | Strong match |
| `MAP_EXISTING` | OK Sterilization Indicator Strips | Sterilization indicator | `IS269` | Strong match |
| `MAP_EXISTING` | Oral-Pro Pyrantel Pamoate Suspension | Pyrantel Pamoate Liquid | `IPPQ` | Strong match |
| `MAP_EXISTING` | Orapac Kit / Oral Dispensing Kit | Orapac Bottle w Adapt family | `OBA.5`, `IOAB8`, `IOBAO4` | Kit family with volume variants |
| `MAP_EXISTING` | OraVet Dental Hygiene Chews | Oravet chew family | `ORAVCS`, `ORAVCM`, `ORAVCL`, `ORAVCXS` | Weight-band family match |
| `MAP_EXISTING` | Ondansetron 4mg / 8mg | Ondansetron family | `IOND4`, `OND8` | Strength family match |
| `MAP_EXISTING` | Onsior 6mg | Onsior 6mg (3 ct) | `IONS6` | Strong match |
| `MAP_EXISTING` | Orogastric Tube Feeding | Cath ft 14fr 16in | `IH130` / `TF` | Feeding tube family |
| `MAP_EXISTING` | Penn? none |  |  |  |
| `MAP_EXISTING` | Pouched or spray items | various | various | review as needed |

## Notes

- Rows marked `MERGE_DUPLICATES` are not evidence of bad data. They are textual or history-block duplicates that should collapse to one resolved PIMS anchor.
- Rows marked `FIX_UOM` are still valid matches, but the unit vocabulary must be normalized before quantity or conversion logic is trusted.
- The action table is intentionally conservative. Anything with a shared code across multiple strengths should stay in review until the variant is explicit.
