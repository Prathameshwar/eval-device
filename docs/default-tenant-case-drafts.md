# Default tenant clinical starters

All three tenant creation routes use the same transaction-scoped starter helper:
the provisioning wizard, platform tenant creation, and self-service organization
creation. Clinical copies belong to the new tenant and have independent IDs,
source revision references, and audit records.

| Created record | Count | Initial state |
|---|---:|---|
| Clinical specialties: Cardiology, Nephrology, Respiratory Medicine | 3 | Active |
| Fictional Alex patient profile | 1 | Inactive, for tenant review and activation |
| Editable cases: Chest discomfort interview and Wheeze interview | 2 | Inactive, for tenant review and activation |
| Published scenarios from those cases | 2 | Active, marked `system_starter`; no tenant clinician approval |
| Published-scenario Practice default | 1 | Chest discomfort, English |
| Catalog-based patient setup default | 1 | Chest discomfort case, English; activation required before adoption |

The two case codes are `alex_chest_discomfort` and `alex_wheeze`. They use
Cardiology and Respiratory Medicine respectively, and both reference the tenant's
Alex profile. No separate training authoring draft or private user Practice
selection is created automatically.

## Clinical content

Both editable cases and published snapshots use document schema version 4:
Presentation & symptoms, History, and eight Vitals. Patient identity, specialty,
language metadata, and publication controls remain. Published English and Hindi
starter localizations are labelled as system-provided examples.

Vitals contain temperature, heart rate, pulse, systolic pressure, diastolic
pressure, respiratory rate, oxygen saturation, and pain. Q&A topics, scripted
answer banks, instructor content, assessment rubrics, and fact-disclosure
configuration are not copied into current records. Runtime replies use the
recorded clinical facts. Facts that existed only in removed dialogue are not
part of the new scenario.

The current presentation editor uses maximum input lengths of 150 characters
for chief complaint and 100 each for onset, duration, and severity, per language.
Symptom descriptions remain at 600. These are UI limits; the API contract is
unchanged, and existing longer content is not silently truncated.

## Practice and training

Published starters appear in the desktop app's scenario choices without activating
the editable catalog cases. The default suggests chest discomfort in English;
each user saves a private scenario/language/vitals selection. Selecting a starter
does not install models or start a conversation. Running practice still requires
the appropriate access and configured runtime.

The compatibility catalog-based setup separately requires an active specialty,
patient profile, and case. Since specialties start active, tenants normally
review and activate the profile and cases before adopting this setup. These
activation requirements do not apply to selection of the already-published
starter snapshots.

Device training requires device enrollment, supported agent capabilities, model
configuration, and existing tenant/session permission checks. The wizard creates
or transfers one device and associates the first administrator atomically; it
does not assign or install models. The platform model catalog defaults are
maintained separately.

Published starters are immutable snapshots with publication version 1 and
document schema version 4. They are explicitly system-provisioned examples,
not tenant clinician approvals. Editing a catalog case does not update a
published snapshot. For revised training content, create a scenario draft and
complete submission, independent clinical review, and publication.

Source records must match the expected starter revisions. Missing or modified
sources cause tenant creation to roll back rather than provision partial data.
Platform administrator status does not grant access to the tenant's clinical
documents. Ordinary provisioning does not modify existing tenants.

Implementation: [starter helper](../platform/api/src/pms_api/modules/patient_catalog.py)
and [provisioning integration tests](../platform/api/tests/test_tenant_provisioning.py).
See [scenario simplification](scenario-simplification.md) for the forward migration
that removed legacy sections from existing data. Frozen migration seeds remain
historical inputs to that migration chain.
