# Web content and configuration management

Clinical specialties, fictional patient profiles, cases and scenario versions belong to one tenant. Q&A remains embedded in each case or scenario document. Global seed records are read-only historical examples; a tenant imports an inactive copy explicitly. Language options remain the platform settings array.

## Navigation and access

| Screen | Route | Access and behavior |
| --- | --- | --- |
| Clinical specialties | /catalog/categories | Tenant clinical readers see summaries; clinical authors edit and activate tenant copies |
| Patient profiles | /catalog/patients | Tenant-owned fictional profiles; author/reviewer views follow current capability |
| Cases & Q&A | /catalog/cases | Tenant-owned structured case and embedded Q&A; clinical authors edit and activate |
| Patient setup | /patient-setup | Organization-wide clinical authors save their own tenant-case rehearsal selection; processing access is checked when practice starts |
| Scenario library | /scenarios | Clinical authors edit/copy drafts; separate clinical reviewers record language review, publish and retire immutable versions |
| Provider connections | Settings > Provider connections | Tenant connection managers; credentials are write-only and remain encrypted by the API |
| Processing profiles | Settings > Processing profiles | Tenant profile managers; edit drafts, publish, view recent revisions and republish a historical revision |
| Platform options | Settings > Platform options | Platform language list, registration, providers and maintenance; English remains the device default |
| Departments | /departments | Real tenant API CRUD, archive and restore; replaces the former in-memory preview |
| Sessions / Reports | /sessions, /reports | Existing scoped session history, start/stop, educator feedback and personal practice summary |
| Recordings | /recordings | Existing scoped processing results and explicit, short-lived media access |
| Personal settings | /settings for tenant users | Existing /me profile fields; password/email flows remain in the account menu |

The server checks the selected context and effective capability on every tenant action; the API enforces current membership, capability and organization/department scope. Tenant administrators assign and revoke clinical author, reviewer, reader and instructor responsibilities in the member detail view. Those responsibilities are not inherited from the base role. Platform administrators receive no implicit clinical, history or media access. Archived records and published versions preserve history.

The fictional patient identity is distinct from the device/manikin registration name. The device name continues to be managed through Devices. Updating a template or patient identity does not rewrite an already-saved practice snapshot.

## Content rules

- Codes become immutable after creation. A case's clinical specialty and patient association remain fixed; create another case for a different association.
- Cases may be saved inactive while incomplete. Activation checks active parents, publication completeness and valid disclosure references.
- Topic IDs, example questions and localized answers are edited within the case. Other translations and server-owned review metadata are retained.
- The editor uses an explicit editing language and source language. Adding a platform language option does not install a conversation language pack or complete translations.
- Copying a tenant case creates a revision-pinned scenario draft. A later case edit requires an explicit draft refresh and another review. Publication requires a different reviewer from the draft content author. Reviewed English and Hindi version 3 content is compiled into the existing signed version 1 device runtime; the published version 3 fingerprint is unchanged.
- Feedback statistics now use the API's actual score values: met = 100, partial = 50, not_met = 0. Unobserved items are excluded from the assessed average.
- Forms report safe validation paths and stale versions, preserve edits on refusal and recover from transport interruption without automatically retrying a write.

## API and database

Forward migrations `0029_tenant_clinical_content`, `0030_clinical_capabilities` and `0031_case_draft_provenance` add tenant content, member responsibilities and case-to-draft provenance. Upgrade through the current Alembic head with the migration owner, run the resumable tenant catalog backfill while old writers are stopped, and reapply `platform/api/deploy/grant-runtime-access.sql`. Imported/backfilled cases stay inactive for tenant review. The API role can edit tenant content; global clinical records are read-only and worker/retention roles cannot read private tenant case drafts.

Tenant routes use `/api/v1/organizations/{id}/clinical-catalog/{specialties|patients|cases}` with scoped lists, details, create/edit, archive/restore and explicit starter import. The old `/platform/patient-catalog` routes are removed. Writes serialize tenant quota checks, recheck the actor under lock, enforce expected versions and commit audits atomically.

The existing configuration API adds scoped `GET /organizations/{id}/configuration-options` using its operation registry and profile defaults. Department/provider/profile archives accept observed versions; profile publication can also check the saved draft's management version.

Session history gains signed, scope-bound cursor pagination while retaining its existing items projection. GET `/organizations/{id}/runs/{run}/media` lists safe media metadata only. It requires media permission and unexpired completed results; object keys and URLs are excluded. Playback URLs are requested separately on explicit action and held briefly in component state.

## Verification and deployment limits

Automated checks cover isolated PostgreSQL upgrades, runtime grants, concurrent catalog writes, snapshot preservation, stale publication/archive, scoped media retention, session pagination, API authorization and UI validation. The opt-in `test_catalog_web.py` drives a tenant catalog and rehearsal journey through real Next.js, API and disposable PostgreSQL when a browser origin is supplied.

Browser artifacts are local under `.test_artifacts/catalog-web`. Actual pass counts and skipped checks are recorded in [review evidence](pms-api-reviews.md). Clinical educator review, hosted deployment and physical hardware checks remain separate gates.
