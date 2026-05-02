# Instinct Reminders Handoff

This is the final handoff note for the Instinct reminder import work.

## What We Proved

- The partner auth token flow works with the documented client-credentials request.
- `GET /v1/reminders` must be paged with `metadata.after` and `pageDirection=after`.
- The reminder smoke-test helper now extracts live `reminderLabelId` values from the paged response.
- `GET /v1/appointments` and `GET /v1/appointment-types` both return `200` with the same partner token.

## Final Export

Handoff CSV:

- `scripts/instinct_reminder_handoff.csv`

Current export size:

- `6,746` reminder rows
- `3,543` reminder groups

Resolution summary:

- `3,530` groups resolved by live Instinct lookup
- `13` groups unresolved in the final live pass

## Match Rule

The correct live match key is the patient PMS / PIMS code when present.

Example:

- `Jack Abner`
- patient PMS ID `23809`
- owner `Kindra Abner`
- owner phone `(352) 636-2110`

That live record resolves in Instinct, so the matching logic should prefer the live patient PMS ID over stale cached account slices.

## Final Exceptions

These are the unresolved groups from the final export that should be called out in the email to Nick:

1. `Harmon, Nancy` / `Pebbles` / `(407) 948 - 1583`
   - `Lyme Vaccine Annual` -> `Borrelia burgdorferi (Lyme) Vaccine` (`reminderLabelId` `41`)
   - `Bordetella Oral Vaccine` -> `Bordetella Oral Parainfluenza Vaccine` (`reminderLabelId` `40`)
   - `DA2PP + Leptospirosis 4 Annual` -> `DA2P + Leptospirosis 4` (`reminderLabelId` `69`)
   - reason: `ambiguous_patient_in_account`
2. `Jimenez, Providencia` / `Ms. Shadow` / `(407) 879 - 2313`
   - `Fvrcpc Annual` -> `FVRCP Vaccine` (`reminderLabelId` `48`)
   - `Feline Rabies 1 yr/Purevax` -> `Rabies Vaccine (Feline)` (`reminderLabelId` `52`)
   - reason: `ambiguous_patient_in_account`
3. `Hospital, Eustis Veterina` / `Kitten 5 - 30 - 25` / `(352) 357 - 6688`
   - `Antech CBC, CHEM25, T4, freeT4` -> `Comprehensive Bloodwork` (`reminderLabelId` `6`)
   - `Inject - Solensia` -> `Solensia Injection` (`reminderLabelId` `55`)
   - `Revolution Plus Cat 2.8 - 5.5#` -> `Flea / Tick / Heartworm Prevention` (`reminderLabelId` `14`)
   - `In House Imagyst Fecal/Oocysts` -> `Fecal Analysis` (`reminderLabelId` `11`)
   - `Feline Rabies 1 yr/Purevax` -> `Rabies Vaccine (Feline)` (`reminderLabelId` `52`)
   - `Rabies Canine 1 yr` -> `Rabies Vaccine (Canine)` (`reminderLabelId` `51`)
   - `General Senior Profile (IRL 78` -> `Senior Blood Work` (`reminderLabelId` `28`)
   - `Annual Wellness Exam` -> `Annual Exam` (`reminderLabelId` `3`)
   - `Credelio for Cats 2.0 - 4.0# C` -> `Flea / Tick Prevention` (`reminderLabelId` `13`)
   - reason: `no_patient`
4. `Sanders, Karen` / `G - Man` / `(713) 385 - 2388`
   - `Feline Leukemia Annual` -> `Feline Leukemia (FeLV) Vaccine` (`reminderLabelId` `47`)
   - `Fvrcpc Annual` -> `FVRCP Vaccine` (`reminderLabelId` `48`)
   - reason: `no_patient`
5. `Sanders - Foster Pets, Ka` / blank patient name / `(352) 343 - 2468`
   - `Antech Fecal & Giardia ELISA` -> `Fecal Analysis` (`reminderLabelId` `11`)
   - reason: `no_patient`

## Note

The CSV has now been backfilled with `instinct_label_id` values from the live reminder-label table, so we did not need to rerun the 22-hour export to fill that column.

The live lookup fix is still the authoritative path; if you regenerate later, keep the patient PMS ID-first resolution rule, the live paging fix, and the `reminderLabelId` capture intact.
