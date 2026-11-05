# Corrected tenant starter scenarios

Migration `0047_compact_starters` updates the two fictional Alex starter cases,
Chest discomfort interview and Wheeze interview, to document schema 5. Fresh tenants
receive these cases automatically through every tenant creation route. The other
seven global draft examples remain at revision 4.

The forward refinement `0048_refined_starters` advances these two sources to revision
6. It separates smoking, alcohol and household facts and states the existing sleep
total (eight hours) and work total (five days) explicitly. Clinical facts and vitals
are unchanged. Drafts have no publication stamps; English/Hindi publications carry
server-issued `system_starter` stamps. This distinction is checked during provisioning.

The starters separate onset, duration and severity; identify resting measurement
timing; retain the known family history and explicitly leave similar family symptoms
unknown. The wheeze example records that a doctor prescribed the reliever inhaler,
while its exact name, dose and frequency remain unknown. Both English and Hindi
documents include concise, fixed food preferences, sleep hours, education, school
days and teaching hours. A usual meal does not establish yesterday's meal.

These are authored fictional examples labeled `system_starter`, with no attribution
of clinical approval to a tenant reviewer. Catalog copies remain reviewable drafts.
New tenants receive publication version 1 of the corrected content; existing unchanged
starter publications receive version 2 after migration 0047 and version 3 after 0048.
Publication versions and document schema
versions are separate numbers.

The forward upgrade matches the previous bundled content and source provenance.
Customized platform sources, tenant cases and parent profiles, archived copies,
tenant-authored publications, and newer versions are preserved. A tenant at the
100-publication capacity keeps its existing publication and gets an audit entry
explaining the skipped publication. Private idle choices upgrade with their vital
overrides intact. Queued/live assignments and their private choices retain their
original version. Defaults move only if they pointed to the replaced starter.
Old publication documents, conversations, recordings and archive snapshots are
never rewritten. Alembic prevents duplicate upgrades.

Compiler 38 separates family medical questions from household questions and limits
qualification answers to explicit education facts. Missing qualifications cannot
select an occupation. Event-specific meal questions require a recorded event.
Explicit combined questions are checked separately on the host, then their evidence
is merged into one prompt. An unknown part cannot borrow facts from another part.
Pain intensity questions cannot select an educational degree. Clear current-symptom,
measurement and qualification questions omit unrelated evidence and previous turns;
ambiguous follow-ups retain their bounded recent reference.
Independent authored sentences become separate selectable sources; dependent
qualifications and pronoun references stay together. Current wellbeing and occupation
questions avoid unrelated facts. Relief questions retain explicit relief evidence;
similar-family questions exclude unrelated conditions. A known fever denial does not
establish an unrecorded cough status.
The contract still uses one model generation and validates every selected source ID
against its frozen prompt. Exact native token fitting reserves 128 output tokens and
128 safety tokens inside the local model's total 2,048-token context. Complete recent
dialogue pairs are removed as needed; question and case evidence are retained.

Only the English conversation pack is currently installed. Hindi case translations
are preserved and validated, but this update does not enable Hindi conversations.
Update the local Human-test application on other machines to receive compiler 38
and its host-side source filtering. Server provisioning and database improvements
apply independently; existing desktop installations do not update themselves.
The October 9 VM update includes API/UI only; its Human-test portable downloads are
unchanged at the user's request. Live validation uses the updated source application.

Before applying the migration to an existing installation, back up PostgreSQL and
apply the current runtime grants. The managed VM deployment helper performs the
backup, traffic isolation and compatible rollback checks. Do not rewrite older
migrations or modify historical scenario documents directly.
