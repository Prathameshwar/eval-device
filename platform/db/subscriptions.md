# Organization subscriptions

Manual subscription fields were introduced in `0025_manual_subscriptions`; deploy the current Alembic head documented in [API setup](../api/README.md). The original capacity increment (`0005`/`0006`) established **13 domain tables and 241 columns** before later platform features. The twelve-table SQL baseline stays unchanged for verified adoption; migration 0005 adds one table and two organization columns; 0006 updates default capacity values.

| Plan | Price amount | Currency | Initial user limit | Initial device limit |
|---|---:|---|---:|---:|
| Standard | 350000.00 (3.5 lakh) | INR | 200 | 1 |
| Advanced | 500000.00 (5 lakh) | INR | 500 | 3 |

User/device limits are confirmed configurable defaults. The billing period starts as `unspecified`. Platform admins can change prices, currency (`INR` or `USD`), period, limits, name and active flag. Amounts use `numeric(14,2)` and are returned as exact decimal strings in currency major units. Changing currency retains the numeric amount unless price_amount is also supplied; configure the intended price explicitly. No exchange-rate conversion is performed. Prices remain informational: there are no invoices, charges or automatic renewals. Manual terms and derived expiry status are described below; they do not gate processing.

## `subscription_plans`

| Field | PostgreSQL type | Description |
|---|---|---|
| id | uuid, primary key | Stable seeded plan identifier |
| code | text, unique | Immutable `standard` or `advanced` |
| name | text | Display name |
| price_amount | numeric(14,2) | Nonnegative amount, excluding nonfinite values |
| currency | text | INR or USD |
| billing_period | text | unspecified, monthly, annual or one_time |
| max_users | integer | 1 to 1,000,000 occupied/reserved user seats per organization |
| max_devices | integer | 1 to 1,000,000 active devices per organization |
| is_active | boolean | Whether new organizations/assignments can select this plan |
| configuration_version | integer | Database-managed optimistic version |
| created_at | timestamptz | Plan creation time |
| updated_at | timestamptz | Last plan update time |

Every plan field is required. There is no plan-creation/deletion API; manage the two seeded plans. Price/limit edits apply to all attached organizations. Reducing a limit below current usage is rejected. Catalog deactivation prevents new selection and preserves existing assignments and their limits.

Organizations gain required `subscription_plan_id` (UUID FK, restricted deletion) and `subscription_assigned_at` (UTC timestamp maintained by the database on assignment changes). New organization requests must explicitly select an active plan; the creator immediately occupies one admin seat. Existing organizations adopt Standard, retaining every user/device and using organization creation time as the initial assignment time. Existing over-limit organizations remain intact and can release capacity or upgrade; they cannot add/reactivate capacity beyond the cap. Subscription summaries expose `over_limit` and remaining capacity.

## Capacity rules and concurrency

- User seats = active accepted organization memberships + unexpired pending invitations. All human organization roles, including administrators and trainees, count. A platform administrator without an organization membership does not count. Global user suspension alone does not release an assigned organization membership; deactivate that membership to release its seat.
- Invitations reserve a seat even before identity registration. Acceptance uses that reservation. Expired/revoked invitations release it; resending an expired invitation reserves again and checks capacity. Direct administrator assignments and membership reactivation obey the same cap.
- Device seats = active device records, including pending enrollment and revoked credentials. Deactivation or retirement releases a seat; revocation alone does not. Reactivation checks capacity again. Each organization's allowance is independent.
- Organization/department suspension does not discard seat assignments. Downgrades must fit occupied and reserved capacity. Plan-limit edits check every attached organization.
- Database triggers enforce these rules for API and direct SQL writes, reusing the administration singleton lock and READ COMMITTED requirement. Capacity-changing statements lock before rows; API paths take the same lock order. No extra usage-counter tables or scheduled counting job are needed.

## API and deployment

| Route | Access / purpose |
|---|---|
| GET /api/v1/subscription-plans | Registered human: selectable plans for organization creation |
| GET /api/v1/platform/subscription-plans | Platform admin: all plans, including inactive |
| PATCH /api/v1/platform/subscription-plans/{id} | Platform admin: edit fields with required expected_version |
| POST /api/v1/organizations | Existing creation permissions; required subscription_plan_id |
| GET /api/v1/organizations/{id}/subscription | Organization settings-read permission: plan, usage, remaining capacity |
| GET /api/v1/platform/organizations/{id}/subscription | Platform admin: subscription summary |
| PUT /api/v1/platform/organizations/{id}/subscription | Platform admin: assign subscription_plan_id; enforce capacity |

Organization administrators cannot upgrade plans through ordinary organization PATCH. Plan updates and assignment changes are audited atomically. Capacity conflicts return HTTP 409 with `subscription_user_limit` or `subscription_device_limit`; unavailable plans use `subscription_plan_unavailable`. Stale catalog updates return `version_conflict`.

Migration 0006 updates a plan only when its user/device pair still matches the old provisional defaults (Standard 25/10, Advanced 100/50). Customized capacity pairs, prices, currency, billing period and active flags are preserved. Changed plans advance their configuration version. Existing records remain active even above the new cap; subsequent additions/reactivations enforce the confirmed limit. The migration serializes capacity changes and transactionally suspends only the plan-edit guard, restoring it before commit. Normal administrator edits still cannot reduce limits below usage.

Run `pms-admin migrate`. For a fresh installation or an upgrade from before 0005, then apply [the API runtime grant bundle](../api/deploy/grant-runtime-access.sql) as schema owner before restarting this API/worker version. The bundle grants API SELECT/UPDATE for plans and EXECUTE for the usage function, with no plan INSERT/DELETE; workers only receive plan SELECT through existing schema-wide reads. Trigger functions remain non-executable by PUBLIC. Keep the previous database backup for a reviewed restore if rollback is required.


## Manual subscription terms (0025)

The user confirmed **tracking only**. Subscription dates, suspension, cancellation
and derived expiry do not change tenant/device activation, authentication,
processing, offline authorization or access to historical results. Existing plan
seat quotas remain enforced. Subscription suspension is separate from tenant
suspension. Payment gateways, payment processing, invoices and automatic renewal
are deferred.

Migration `0025_manual_subscriptions` adds six organization columns:

| Column | Contract |
| --- | --- |
| `subscription_status` | Required `active`, `suspended` or `cancelled`; defaults to active. |
| `subscription_starts_at` | Optional finite UTC instant; inclusive start. |
| `subscription_ends_at` | Optional finite UTC instant; exclusive end, strictly after a supplied start. Null means no recorded expiry. |
| `subscription_reference` | Optional platform-private reference, up to 256 characters. |
| `subscription_notes` | Optional platform-private notes, up to 2,000 characters. Never record payment credentials. |
| `subscription_version` | Required positive integer, starts at one and is incremented by a database trigger when terms or plan change. |

Existing tenants retain every plan, commercial value, device, lifecycle flag and
assignment timestamp. Their new dates/reference/notes are null. No existing data
is backdated, disabled or expired. The frozen SQL baseline and earlier migrations
are unchanged. The forward upgrade and baseline adoption are tested with existing
data; destructive downgrades are refused.

The API derives `state`: suspended/cancelled take precedence; otherwise an end at
or before the current time is expired, a future start is scheduled, and all other
records are active. It uses the same rule for directory filters and details.
Expiry is evaluated on reads; no scheduler changes state or processing access.
`enforcement=tracking_only` makes this explicit to clients.

New APIs (under `/api/v1`):

- `GET /platform/subscriptions`: requires `platform.organizations.read`; unarchived
  tenant directory with literal name/ID `q` (up to 128 characters), `state`,
  `plan_id`, `limit=1..100`, signed `cursor`, totals and stable name/ID ordering.
- `PATCH /platform/organizations/{id}/subscription`: requires
  `platform.organizations.manage`, required positive `expected_version` from the
  subscription response, and one or more manual columns above (except version),
  optionally `subscription_plan_id`. Omitted fields remain unchanged; optional
  dates/reference/notes can be explicitly cleared. Archived tenants cannot change.
- `GET /platform/organizations/{id}/subscription/history`: platform organization
  readers receive retained manual changes and plan assignments with paged audit
  metadata. This is limited subscription history, not general audit/media access.
- `GET /organizations/{id}/subscription/history`: tenant-wide accepted active
  members with `org.settings.read` can read their own retained subscription history.
  Existing organization subscription GET uses the same privacy boundary. Platform
  administration alone does not grant these tenant routes.

Summary responses include name/availability, manual status, derived state, dates,
subscription `version`, the current plan and capacity. Only platform responses
include private notes/reference; generic organization projections and all audit
payloads omit their values. Audit records describe safe before/after changes and
which private fields changed. History follows the existing audit retention policy.

The old PUT plan-assignment endpoint remains compatible: its `expected_version`
refers to organization management version, while new PATCH uses subscription
version. Both invalidate stale subscription editors. Plan catalog PATCH keeps its
own required configuration version. Changes and audits commit atomically under
existing administration/organization locks; quota failure rolls back the entire
manual update. Catalog deactivation still prevents new selection while allowing
existing subscriptions to keep their plan and maintain dates/notes.

Apply `uv run pms-admin migrate` from `platform/api` using the configured deployment
owner before starting this API version. Apply the entire migration chain through the current head in [API setup](../api/README.md); `0025` alone does not satisfy current readiness. Existing
table-level API grants cover the new columns; the new trigger is owner-attached
and has no PUBLIC execution privilege, so no new runtime grant is required.
