# Simplified scenario authoring

Scenarios now use schema version 4. The wizard and detail editor expose
Presentation & symptoms, History, and Vitals. Patient identity, specialty,
language review and publication controls remain.

Vitals are limited to temperature (°C), heart rate (bpm), pulse (bpm), systolic
and diastolic pressure (mmHg), respiratory rate, oxygen saturation (%) and pain
(0–10). Unknown history is distinct from an explicitly recorded absence.

Q&A, Instructor content and fact-disclosure configuration are removed. Both
draft and catalog request schemas reject these fields, including disclosure on
individual symptoms/history entries. The legacy direct scenario-create route
is removed; clients create drafts and use the reviewed publication workflow.
Published lists default to `schema_version=4` and also accept `all`.

Migration `0041_simple_clinical_cases` converts global starter templates, tenant
cases, drafts, published versions and private practice snapshots. It preserves
clinical fields, updates hashes and revisions, clears draft submissions and
retains only valid existing language approvals. Database constraints reject
removed sections and additional vital fields. All existing versions, including
historical published versions, receive this one-time cleanup.

Historical conversation prompts may contain compiled Q&A with no recoverable
source boundaries. The migration removes those prompts and closes their
conversation contexts. Transcripts, session results, feedback and audit events
remain. An audit event records the structural cleanup. No table exists solely
for the removed sections; shared case/session tables remain necessary.

New device sessions receive runtime version 2 containing the clinical case.
The companion answers from these facts through its configured local model;
it no longer requires an authored question bank. Response, timeout and speech
budgets remain bounded. Incomplete translations still block execution. Old
format parsers remain only for migration and compatibility with previously
issued device payloads; they are not accepted by current authoring APIs.

Deploy the API, UI, shared contracts and device companion together. Stop local
services and run `platform/db/sync.py --apply` with the existing migration-owner
configuration; this creates and verifies a backup before upgrading. Restart
services and start fresh practice/training sessions. Downgrade cannot recreate
deleted sections; recovery requires the backup. Frozen migration seed files
remain unchanged so fresh installations can replay the complete migration chain.

Validation uses disposable PostgreSQL, mocked local inference and isolated
browser previews. Live model quality, cloud providers and Raspberry Pi hardware
are not covered by these checks.

Follow-up review: migration `0042_clinical_source_references` repairs source revision references left behind by the format conversion. It updates only references that were current before 0041 and whose source/copy were untouched afterward; it preserves custom draft content and genuine staleness. New training sessions use the current local model selector (Whisper, local conversation model and eSpeak), and leases recheck configuration changes. Blank symptoms can be saved in drafts, but publication requires their descriptions. Device replies use the shared output validator before speech.


Tenant onboarding uses these v4 documents for two inactive editable cases and two active published system starters. Three specialties start active; the fictional Alex profile starts inactive. Published starters are selectable in the desktop app independently of catalog-case activation, with chest discomfort in English as the tenant default. Each user saves a private selection. See [tenant starter behavior](default-tenant-case-drafts.md).


Practice is desktop-only. The web `/practice` and `/patient-setup` routes, components, server actions, navigation and Settings card have been removed. The desktop app loads published scenarios and the tenant default directly through `/patient-practice/scenario-options`, lets the user choose an available language and starting vitals, and saves the private selection only on explicit Save. Practice APIs, tenant defaults, private selections and conversation storage remain necessary for desktop use; no removal migration is applied. Scenario authoring, publication and device training remain available in the web platform.
