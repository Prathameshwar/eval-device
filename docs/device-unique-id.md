# Device unique IDs

Every newly created device requires a **Device unique ID** (`device_unique_id`),
containing 1–50 characters after trimming surrounding whitespace. Control
characters and blank values are rejected. Uniqueness is case-insensitive across
the entire platform, including inactive and retired devices. An ID cannot be
edited or reused for another device.

Platform registration, tenant device registration and the tenant onboarding
wizard all require this value. List/search responses expose it; edit and details
screens display it read-only. Duplicate registration returns HTTP 409 with code
`device_unique_id_exists`. Missing, invalid or attempted edit fields return 422.

The ID identifies the physical device. A tenant transfer preserves it while
retiring the old registration and issuing a new internal registration UUID that
requires fresh enrollment. Old credentials, configuration, media and history do
not move between tenants. API URLs, device credentials and existing wire fields
continue to use the internal UUID `id`; this change does not replace that key.

Migration **0040_device_unique_ids** backfills each existing registration with
its own existing UUID string (36 characters), as approved for existing data.
It records the backfill in the audit trail and preserves registration/history
references. The `device_identities` table permanently reserves each physical ID.
`devices.device_unique_id` references it, is immutable, and has at most one
non-retired registration platform-wide. Retired registrations may reference the
same physical identity after a transfer. Database constraints and the API's
administration lock protect concurrent creation and transfer.

Apply migration 0040 and the runtime grant bundle before starting this API
revision. Only the API runtime can read/insert identity reservations; no runtime
role can update/delete them. Fresh initialization/deployment includes the
migration. No default is supplied for new IDs: callers must provide one in
`POST /api/v1/platform/devices` and in the `kind: new` device choice submitted to
`POST /api/v1/platform/organizations/provision`. Existing-device transfers take
their ID from the source registration and reject an override.
