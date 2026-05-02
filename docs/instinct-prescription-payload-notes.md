# Instinct Prescription Payload Notes

Captured from the live Instinct Partner API on April 22, 2026.

Purpose:

- inspect the real payload shapes for the four prescription endpoints
- identify which feed is more useful for a custom Instinct-to-Vetcove workflow
- avoid guessing field names from the docs alone

Reference docs:

- `GET /v1/external-prescriptions`
  - https://docs.instinctvet.com/reference/scriptswebpartnerprescriptioncontrollerindex
- `GET /v1/external-prescriptions/{id}`
  - https://docs.instinctvet.com/reference/scriptswebpartnerprescriptioncontrollershow
- `GET /v1/dispensed-prescriptions`
  - https://docs.instinctvet.com/reference/instinct-partner-list-dispensed-prescriptions
- `GET /v1/dispensed-prescriptions/{id}`
  - https://docs.instinctvet.com/reference/instinct-partner-fetch-dispensed-prescription

## Capture summary

The four endpoints returned real data from the EVH tenant on April 22, 2026.

Observed list counts at capture time:

- `external-prescriptions`: `31`
- `dispensed-prescriptions`: `352`

The list endpoints returned standard list wrappers with:

- `data`
- `metadata.after`
- `metadata.before`
- `metadata.limit`
- `metadata.totalCount`
- `object: "list"`

## 1. External prescriptions list

Endpoint:

- `GET /v1/external-prescriptions?limit=2`

Observed sample shape:

```json
{
  "data": [
    {
      "creatorId": "<string>",
      "deactivateReasonNote": null,
      "expiresAt": "2027-04-22T13:13:34.794000Z",
      "id": "<uuid>",
      "insertedAt": "2026-04-22T13:15:27.927083Z",
      "instructions": "Give 1/2 tablet by mouth every 12 hours for 7 days. Then reduce to 1/2 tablet every 24 hours thereafter.",
      "isPrn": false,
      "object": "prescription",
      "patientId": "<string>",
      "pharmacyNote": "chewy",
      "prescriberId": "<string>",
      "product": {
        "formulationUnit": {
          "abbreviation": "tab",
          "key": "tablet",
          "label": "Tablet"
        },
        "label": "Oclacitinib (Apoquel) 3.6mg Tablet",
        "strengthUnit": {
          "abbreviation": "mg",
          "key": "milligram",
          "label": "Milligram"
        }
      },
      "quantityPerFill": {
        "coef": 220,
        "exp": -1,
        "sign": 1
      },
      "status": "written",
      "totalFills": 7,
      "updatedAt": "2026-04-22T13:15:27.941664Z"
    }
  ],
  "metadata": {
    "after": "<cursor>",
    "before": null,
    "limit": 2,
    "totalCount": 31
  },
  "object": "list"
}
```

Observed fields on list items:

- `creatorId`
- `deactivateReasonNote`
- `expiresAt`
- `id`
- `insertedAt`
- `instructions`
- `isPrn`
- `object`
- `patientId`
- `pharmacyNote`
- `prescriberId`
- `product`
- `quantityPerFill`
- `status`
- `totalFills`
- `updatedAt`

Notable details:

- `id` is a UUID string.
- `patientId`, `creatorId`, and `prescriberId` were string-typed in the sample.
- `product` is embedded, not just an ID.
- `quantityPerFill` is not a plain decimal string; it is a structured numeric object with `coef`, `exp`, and `sign`.
- `pharmacyNote` appears useful for outside-fulfillment context.

## 2. External prescription detail

Endpoint:

- `GET /v1/external-prescriptions/{id}`

Observed sample shape:

```json
{
  "creatorId": "<string>",
  "deactivateReasonNote": null,
  "expiresAt": "2027-04-22T13:13:34.794000Z",
  "id": "<uuid>",
  "insertedAt": "2026-04-22T13:15:27.927083Z",
  "instructions": "Give 1/2 tablet by mouth every 12 hours for 7 days. Then reduce to 1/2 tablet every 24 hours thereafter.",
  "isPrn": false,
  "object": "prescription",
  "patientId": "<string>",
  "pharmacyNote": "chewy",
  "prescriberId": "<string>",
  "product": {
    "formulationUnit": {
      "abbreviation": "tab",
      "key": "tablet",
      "label": "Tablet"
    },
    "label": "Oclacitinib (Apoquel) 3.6mg Tablet",
    "strengthUnit": {
      "abbreviation": "mg",
      "key": "milligram",
      "label": "Milligram"
    }
  },
  "quantityPerFill": {
    "coef": 220,
    "exp": -1,
    "sign": 1
  },
  "status": "written",
  "totalFills": 7,
  "updatedAt": "2026-04-22T13:15:27.941664Z"
}
```

Observed behavior:

- the detail endpoint returned the same field set as the sampled list item
- no additional embedded account or patient object was present in the sampled detail response

## 3. Dispensed prescriptions list

Endpoint:

- `GET /v1/dispensed-prescriptions?limit=2`

Observed sample shape:

```json
{
  "data": [
    {
      "accountId": "<uuid>",
      "daysSupply": null,
      "expiresAt": "2027-03-19T16:56:51.697000Z",
      "id": 1,
      "insertedAt": "2026-03-19T16:57:50.912922Z",
      "instructions": "Place one pump in the left ear every 24 hrs for 7 days",
      "isControlledSubstance": false,
      "note": "test",
      "object": "dispensed_prescription",
      "patientId": 67,
      "prescribedAt": "2026-03-19T16:57:50.908644Z",
      "productId": 2920,
      "quantity": "1.0",
      "remainingFills": 1,
      "status": "voided",
      "totalFills": 0,
      "type": "default",
      "updatedAt": "2026-03-28T16:11:21.656990Z"
    }
  ],
  "metadata": {
    "after": "<cursor>",
    "before": null,
    "limit": 2,
    "totalCount": 352
  },
  "object": "list"
}
```

Observed fields on list items:

- `accountId`
- `daysSupply`
- `expiresAt`
- `id`
- `insertedAt`
- `instructions`
- `isControlledSubstance`
- `note`
- `object`
- `patientId`
- `prescribedAt`
- `productId`
- `quantity`
- `remainingFills`
- `status`
- `totalFills`
- `type`
- `updatedAt`

Notable details:

- `id` is an integer.
- `patientId` is an integer in the sample.
- `accountId` is present here but not in the sampled external-prescription response.
- `productId` is present, but there is no embedded product object in the sample.
- `quantity` is a string-typed decimal in the sample.
- `remainingFills` exists here and was not present in the sampled external-prescription payload.

## 4. Dispensed prescription detail

Endpoint:

- `GET /v1/dispensed-prescriptions/{id}`

Observed sample shape:

```json
{
  "accountId": "<uuid>",
  "daysSupply": null,
  "expiresAt": "2027-03-19T16:56:51.697000Z",
  "id": 1,
  "insertedAt": "2026-03-19T16:57:50.912922Z",
  "instructions": "Place one pump in the left ear every 24 hrs for 7 days",
  "isControlledSubstance": false,
  "note": "test",
  "object": "dispensed_prescription",
  "patientId": 67,
  "prescribedAt": "2026-03-19T16:57:50.908644Z",
  "productId": 2920,
  "quantity": "1.0",
  "remainingFills": 1,
  "status": "voided",
  "totalFills": 0,
  "type": "default",
  "updatedAt": "2026-03-28T16:11:21.656990Z"
}
```

Observed behavior:

- the detail endpoint returned the same field set as the sampled list item
- no embedded account, patient, or product object was present in the sampled detail response

## Comparison

### External prescriptions

Strengths:

- includes an embedded `product` object with human-readable label and unit metadata
- includes `pharmacyNote`
- includes `quantityPerFill`
- status in the sample was `written`

Limitations:

- no `accountId` in the sampled payload
- no embedded patient/account details
- `remainingFills` was not present in the sample

### Dispensed prescriptions

Strengths:

- includes `accountId`
- includes `remainingFills`
- includes `prescribedAt`
- has simpler `quantity` formatting in the sample

Limitations:

- product is only `productId` in the sampled payload
- no embedded product label in the sample
- sample status was `voided`, which may be more historical/dispense-state oriented than external-fulfillment oriented

## Working interpretation

This is an inference from the live payloads, not something the docs explicitly stated.

- `external-prescriptions` currently looks more useful for a Vetcove-facing workflow when we need medication name, formulation hints, instructions, fills, and outside-pharmacy context.
- `dispensed-prescriptions` currently looks more useful for account linkage and internal dispense-state tracking.

That suggests the likely EVH approach is:

1. use Instinct account and patient feeds for identity
2. inspect `external-prescriptions` first as the likely export driver for Vetcove Rx creation/import prep
3. use `dispensed-prescriptions` as a secondary reconciliation/history feed if needed

## Open follow-up items

- confirm whether `external-prescriptions` also supports filtering by date, patient, account, or status
- inspect more than one detail record from each collection to see whether optional fields vary materially
- determine how to resolve `productId` from `dispensed-prescriptions` into a human-readable product label
- determine whether EVH needs both feeds or only `external-prescriptions`
- map these fields against Vetcove's client/patient template and any Rx onboarding process they support
