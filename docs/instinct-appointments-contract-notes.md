# Instinct appointment contract notes

Source docs reviewed:

- `https://docs.instinctvet.com/reference/instinct-partner-list-appointments`
- `https://docs.instinctvet.com/reference/instinct-partner-fetch-appointment`
- `https://docs.instinctvet.com/reference/instinct-partner-update-appointment`
- `https://docs.instinctvet.com/reference/instinct-partner-cancel-appointment`
- `https://docs.instinctvet.com/reference/instinct-partner-list-appointment-types`
- `https://docs.instinctvet.com/reference/instinct-partner-fetch-appointment-type`

## Appointment endpoints

### List Appointments

- Method: `GET`
- Path: `/v1/appointments`
- Query params:
  - `limit` integer `1..100`
  - `pageCursor` string
  - `pageDirection` enum `before|after`
  - `insertedSince` ISO 8601 date-time
  - `insertedBefore` ISO 8601 date-time
  - `updatedSince` ISO 8601 date-time
  - `updatedBefore` ISO 8601 date-time
  - `startsAfter` ISO 8601 date-time
  - `startsBefore` ISO 8601 date-time
- Response:
  - `200 Appointment List Response`

### Fetch Appointment

- Method: `GET`
- Path: `/v1/appointments/{id}`
- Path param:
  - `id` integer `>= 1`
- Response:
  - `200 Appointment Response`
  - `404 Appointment not found`

### Update Appointment

- Method: `PATCH`
- Path: `/v1/appointments/{appointment_id}`
- Path param:
  - `appointment_id` integer `>= 1`
- Body params:
  - `isConfirmed` boolean required
- Response:
  - `200 Appointment Response`
  - `422 Unprocessable Entity`

### Cancel Appointment

- Method: `POST`
- Path: `/v1/appointments/{appointment_id}/cancellation`
- Path param:
  - `appointment_id` integer `>= 1`
- Response:
  - `200 Appointment Response`
  - `422 Unprocessable Entity`

## Appointment type endpoints

### List Appointment Types

- Method: `GET`
- Path: `/v1/appointment-types`
- Query params:
  - `limit` integer `1..100`
  - `pageCursor` string
  - `pageDirection` enum `before|after`
  - `insertedSince` ISO 8601 date-time
  - `insertedBefore` ISO 8601 date-time
  - `updatedSince` ISO 8601 date-time
  - `updatedBefore` ISO 8601 date-time
  - `includeDeleted` boolean
  - `deletedSince` ISO 8601 date-time
  - `deletedBefore` ISO 8601 date-time
- Response:
  - `200 Appointment Type List Response`

### Fetch Appointment Type

- Method: `GET`
- Path: `/v1/appointment-types/{id}`
- Path param:
  - `id` integer `>= 1`
- Response:
  - `200 Appointment Type Response`
  - `404 Appointment Type not found`

## Current takeaways

- Instinct exposes a clean appointment lifecycle surface for list, fetch, confirm, and cancel.
- The update contract explicitly shows `isConfirmed` as the writable field in the docs.
- The docs do not include JSON examples in the rendered pages I checked, so request and response field-level mapping still needs a live API response or OpenAPI source if we want an exact schema.
