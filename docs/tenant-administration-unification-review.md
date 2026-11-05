# Tenant administration unification review (2026-10-01)

## Finding and change

The tenant list and tenant detail page opened two different dialogs with the
same "Tenant administration" title. The list offered Users and Devices; the
detail page offered Subscription and Administrators. Both entries now render
the same administration dialog with all four sections. The list opens on Users
when permitted, and the detail page opens on Subscription. Device-only readers
open on Devices. The list action is labeled "Tenant administration" to match
the detail action.

The existing server actions and API endpoints still enforce account, tenant,
administrator, device, subscription, lifecycle and version checks. Association
confirmations and permission-gated controls remain in their existing panels.
The subscription and administrator summary loads when its tab is opened and
refreshes after a user association. The list keeps the open dialog bound to the
latest tenant record after a restore or plan change.

## Verification

- Focused tenant and LLM UI tests: 33 passed, including both entry points, role and
  device associations, permission-gated tabs, administrator refresh and a
  changed tenant record while the dialog is open. The final focused run covered
  the read-only tenant administration entry and the LLM disabled state.
- Full web suite: 490 passed across 70 files before the final read-only entry
  adjustment; all affected tests passed afterward. The production Next.js build,
  TypeScript check, nine Ubuntu deployment tests and Bash syntax check passed.
- Local transfer archive `start/dist/pms-platform-20261001-131950-5428cf.zip`
  has SHA-256 `0709369e41c25c7d641dbabca645bf585bf574e7159a1fe0ad7ac2bf0c8b0d8a`.
  All 739 manifest entries verified; all changed packaged source matches the
  reviewed workspace.
- Final review found no API, database or permission grant changes. The Ubuntu
  VM and hosted application were deliberately left unchanged.

## LLM page follow-up

The tenant administrator's LLM page returned two 503 errors because the API's
`PMS_LLM_ENABLED` default is false and the Ubuntu script had omitted the flag
from newly generated configuration. New VM-local configurations now enable LLM
connection management explicitly; external model calls remain off. Existing
root-owned configuration is preserved, so an operator must set the flag there
before a later deployment. The page now gives one clear unavailable state when
the API still has the gate disabled. No VM change was made during this review.
