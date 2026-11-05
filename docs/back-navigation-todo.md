# Unified console back navigation - 2026-10-03

Scope: console page navigation. Preserve unrelated changes, permissions, list state,
editor discard guards and wizard-step controls. Authentication flows and Home (the
root destination) retain their existing behavior.

- [x] Inventory current routes, return controls and editor guards; capture baseline.
- [x] Add one accessible, responsive control for route links and guarded callbacks.
- [x] Standardize primary pages and Settings destinations.
- [x] Standardize detail/create/editor views, remove duplicated returns, and fix the model catalog destination.
- [x] Cover unavailable/error views and import history.
- [x] Verify destinations, guard behavior, list-state retention, keyboard focus and responsive layouts.
- [x] Run tests/typecheck/build, review final changes and record results.

## Destination rules

- Primary console pages return to Home; Settings destinations return to Settings.
- Record details and creation pages return to their corresponding list.
- Model details return to `/models?tab=catalog`.
- Editors opened inside a page return through their existing state/confirmation callbacks.
- Tenant subscription details return to Settings; platform subscription details return to the subscription list.
- Import history returns to Members; the import wizard keeps its existing Members destination.
- Render one return control above each page heading. Nested Models lists do not repeat the outer Settings return.
- Use explicit destinations rather than browser history so direct links behave predictably.

## Verification

- Shared UI: 1,577 tests passed; web: 547 tests across 80 files passed.
- UI type checking and production build passed. The build retains the existing
  TenantProvisionWizard CSS warning about `align-items: end`.
- Browser verification: 57 rendered component states, 1,081 checks, no failures.
  Covered 320/390/768/1024/1440px widths, short windows, doubled root text size,
  light/dark/ledger themes, 44px targets, heading overlap, list-table height,
  explicit link destinations and visible keyboard focus. Mobile Devices and
  desktop Models screenshots visually inspected.
- Regression checks cover catalog/scenario/connection discard confirmation,
  connection search/filter retention, a single Settings return in Models, and
  the model detail Catalog destination. Authentication and authorization tests pass.
- Final diff and whitespace checks passed. Existing concurrent work preserved.
- Evidence: `.test_artifacts/back-navigation-20261003/`. Browser checks use actual
  component HTML captured from mocked tests with shared/application CSS; this is
  local verification, not an authenticated live-server or cloud/hardware test.

## Route coverage

37 console route files reviewed: 32 non-root page routes use the shared control,
Home is the root, and four legacy routes redirect to their current destinations.

| Pages | Return destination |
| --- | --- |
| Tenants, Devices, Logs, Members | Home |
| Scenarios, Practice, Sessions, Reports, Recordings | Home; opened records return to their list |
| Clinical specialties, Patients, Cases | Home |
| Settings hub / personal settings | Home |
| Models, Users, Subscriptions, Departments, Platform options | Settings |
| Tenant details / creation | Tenants |
| Device details | Devices |
| Model details | Models, Catalog tab |
| Log details | Logs |
| User / member details | Users / Members |
| Subscription details | Subscriptions (platform), Settings (tenant) |
| Department details / creation | Departments |
| Specialty / patient / case editor | Corresponding catalog list, retaining discard confirmation |
| Member import / import history | Members |

Models' nested connection/profile editors use the shared callback button with their
existing discard checks. Wizard step navigation remains separate from page returns.
The legacy Connections, Profiles, LLM Connections and Patient Setup routes redirect;
inactive legacy components are outside this change.
