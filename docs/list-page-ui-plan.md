# List-page UI standardization — 2026-10-03

Scope: list search/filter layouts only. Preserve current search timing, query limits,
sorting, pagination, Apply/Clear behavior, permissions and unrelated in-progress work.
No API/database changes or external-service verification.

## Phase checklist

- [x] 1. Recheck active routes and capture the current working-tree baseline.
- [x] 2. Standardize shared list-filter dimensions, label layout, spacing and responsive widths.
- [x] 3. Apply to existing filter bars and tenant Users/Devices panels.
- [x] 4. Migrate Users/Members/Subscriptions custom rows and Logs advanced filters.
- [x] 5. Verify responsive layouts, themes, long values, errors, keyboard interaction and table/pager usability; fix findings.
- [x] 6. Run UI tests, typecheck and build; review the final task diff and record evidence.

## Layout contract

- Controls use 2.75rem (44px at default root size); labels sit above inputs.
- Use 0.75rem (12px) row/column gaps with no inherited stacked-form margins.
- Search grows from a 16rem basis up to 26rem. Other fields grow from 12rem up to 15rem.
- Fields shrink safely within their container. Narrow filter containers stack controls at full width.
- Actions align with input boxes and wrap without clipping. Applied-filter chips stay compact.
- Help/errors remain below their fields; ordinary forms and non-filter controls retain existing styles.
- Filter bars, tables and pagination remain usable in short/narrow windows.

## Screen checklist

- [x] Tenants
- [x] Devices (platform and tenant filter variants)
- [x] Users and Members
- [x] Subscriptions
- [x] Activity logs (primary and date/ID filters)
- [x] Departments
- [x] Categories, Patient profiles and Cases
- [x] Scenarios
- [x] Models: Catalog, Audio/video connections, Processing profiles
- [x] Tenant administration: Users and Devices panels
- [x] Regression inspection: Sessions, Reports, Recordings and Member import history

The original inventory counted 16 list routes and 12 requiring corrections, with
two additional tenant panels. Redirects and inactive legacy components are not
separate pages. Route/navigation work in progress may change which lists are reachable.

## Verification

- Shared UI suite: 46 files / 1,577 tests passed.
- Full web suite: 538 tests passed (`web-reviewed.json`). Earlier failures in concurrently changing navigation/scenario tests cleared on the later run.
- Added 16 focused regressions across list queries, Models tabs, device department/profile filters, date Apply/Clear and platform tenant filtering. The last affected Logs/Subscriptions run passed all 14 tests (`actions-final.json`); integrated list coverage passed all 13 (`regression-models.json`). These runs overlap the full suite and are not additive totals.
- Workspace typecheck and final production build passed (`typecheck.txt`, `build-reviewed.txt`, build exit 0). The build retains an unrelated existing autoprefixer warning in TenantProvisionWizard.module.css.
- Final browser review: 69 rendered list states / 1,449 viewport, theme, scaling, long-option, keyboard and pager checks passed with zero failures (`browser-results.json`).
- Final task review found no remaining confirmed list-filter defects. CRLF-aware diff whitespace checks passed.
- Browser fixtures are DOM snapshots rendered from actual list components with mocked data, then measured in headless Microsoft Edge with current production CSS. They cover 320/390/768/1024/1440px, short windows, 200% text scaling, light/dark/ledger themes, long option names, focus/Tab and pager reachability. These are not live authenticated API journeys or cross-browser certification.
- Recordings and import history received source regression inspection; Recordings also has an explicit test for the absent empty filter strip.
- Database tests were not run: this task changes no API, schema or database behavior.

## Review findings resolved

1. Normal search fields were about 43px while inline selects were about 33px. Active list selectors now use stacked labels and all filter inputs use the same 2.75rem height.
2. Form sibling margins and two competing search-width policies caused inconsistent spacing and wrapping. FilterBar now owns dimensions and spacing; ordinary forms keep their existing styles.
3. Narrow or text-enlarged desktop layouts could shrink the table to a 2px border. List table scrollports now retain a readable minimum height and the main page can scroll to pagination.
4. The platform log Clear action could wrap alone with an empty label-sized gap. Apply/Clear now wrap as a group in the shared action slot; Subscriptions uses that slot too.
5. Recordings rendered an empty filter strip. It now renders the strip only for modes with a scope selector.

Review checked unchanged query handlers, limits, role-dependent options, tenant scopes, pagination resets, native form submission and retained permission gates. Search timing/trimming was preserved by retaining the immediate TextField handlers on Users/Members/Subscriptions. Changes were reviewed against a snapshot of the working tree to preserve concurrent work.

Artifacts: `.test_artifacts/list-ui-standardization-20261003/` contains the working-tree baseline, task diff, test reports, build logs, browser measurements and screenshots. Original measurements are in `.test_artifacts/list-ui-audit-20261003/`.
