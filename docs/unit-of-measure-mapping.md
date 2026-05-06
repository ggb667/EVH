# Unit of Measure Mapping

This file records the unit mappings the AJ worker was asked to remember.

## Inventory Ally units that need normalization

| Inventory Ally | Normalized value |
| --- | --- |
| Ampoule | ampoule |
| Applicator | applicator |
| Blister | blister |
| Bucket | bucket |
| Caplet | caplet |
| Cassette | cassette |
| Catheter | catheter |
| Chew | chew |
| Count | count |
| Cover | cover |
| Envelope | envelope |
| Gloves | gloves |
| Jar | jar |
| Mask | mask |
| Needle | needle |
| Pouch | pouch |
| Roll | roll |
| Rx Vial | rx vial |
| Sachet | sachet |
| Sleeve | sleeve |
| Slide | slide |
| Stick | stick |
| Strip | strip |
| Supplement | sup |
| Suture | suture |
| Syringe | syringe |
| Tray | tray |
| Wipe | wipe |
| Yard | yd |

## Stockroom and EMR units that need normalization

| Source | Unit | Mapping | Target |
| --- | --- | --- | --- |
| STOCKROOM | 9 Point Score | /9 | EMR |
| EMR | Bag | bag | EMR |
| EMR | Bottle | btl | EMR |
| EMR | Box | box | EMR |
| EMR | Capsule | cap | EMR |
| EMR | Dose | dose | EMR |
| EMR | Drop | drop | EMR |
| EMR | Each | ea | EMR |
| EMR | Microgram per Kilogram per Hour | mcg/kg/hr | EMR |
| EMR | Microgram per Kilogram per Minute | mcg/kg/min | EMR |
| EMR | Milliequivalent per Kilogram per Hour | mEq/kg/hr | EMR |
| EMR | Milliequivalent per Liter | mEq/L | EMR |
| EMR | Milligram per Kilogram per Hour | mg/kg/hr | EMR |
| EMR | Milligram per Kilogram per Minute | mg/kg/min | EMR |
| EMR | Milliliter | mL | EMR |
| EMR | Milliliter per Hour | mL/hr | EMR |
| EMR | Milliliter per Kilogram per Hour | mL/kg/hr | EMR |
| EMR | Milliliter per Liter | mL/L | EMR |
| EMR | Millimole per Kilogram per Hour | mmol/kg/hr | EMR |
| EMR | Millimole per Liter | mmol/L | EMR |
| EMR | Packet | pkt | EMR |
| EMR | patch | PATCH | EMR |
| EMR | Percent | % | EMR |
| EMR | Tablet | tab | EMR |
| EMR | Tube | tube | EMR |
| EMR | Unit per Kilogram per Hour | Unit/kg/hr | EMR |
| EMR | Vial | vial | EMR |

## Notes

- `Unit` was treated as a straight 1:1 match and is not listed above.
- The source labels reflect the user-provided lists, including case differences where they appeared.
