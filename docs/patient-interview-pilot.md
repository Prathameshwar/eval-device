# Patient interview pilot

Scope: one Pi, one laptop, one learner, one fictional educator-reviewed patient scenario. Hindi and English. Audio and video stay independent private services; the coordinator adds session context, dialogue, speech output and replay. No live video analysis or implicit cloud fallback.

Future product direction: the [Patient Scenario Library](patient-scenario-library.md) defines configurable manikin patient profiles, clinical cases, vital signs, history, disclosure rules, and assignment. It is the feature baseline for the next plan; its broader requirements are not claims about this pilot's implemented scope.

## Ownership and authorization

The platform owns identities, organization/department scope, immutable approved scenarios and training session authorizations. The laptop owns one active local session and bounded local media. The Pi owns the device credential, capture and physical playback. The instructor controls sessions; trainees do not acquire operator permissions. Local pairing credentials never impersonate platform roles. Every turn and recording belongs to a server-generated session and versioned scenario. The coordinator uses a separately scoped, expiring session grant relayed by the Pi, not the Pi platform credential.

## Lifecycle and evidence

Server sessions: authorized -> active -> completed/failed/cancelled/expired. Authorization expires, stopping capture/playback and suppressing stale replies. Local turns: captured -> transcribed -> generated -> playback-ready -> playing -> played/failed/unknown. A returned audio file is not proof of playback. Duplicate event IDs must retain their original content and never replay a response automatically. The instructor can stop at any point. Recording and result synchronization failures remain visible independently of speech generation.

Use relative Pi monotonic capture timestamps with an explicit session clock anchor; wall-clock time is metadata, not playback timing. Save raw microphone audio, returned transcript, patient response text/audio and actual playback acknowledgments. Video remains compressed JPEG -> existing Matroska recorder. No media content goes into platform audit logs.

## Scenario and assessment

A scenario contains stable identity/history, bilingual approved answers, topic intents and an instructor rubric. Local model output selects approved facts/answers; it does not invent patient facts. Unknown or ambiguous questions elicit an approved clarification. Conversation context supports follow-up questions; model output never changes the case. Rubric content is not sent to the dialogue model. The synthetic sample is explicitly not clinically approved; an educator must approve a version before learner use. Development fixture mode is separate and cannot mint platform authorization.

## Pilot gates

Measure CPU/RAM, response latency and answer selection on Hindi, English and mixed speech. Report end-of-input to first audible response separately from generation and recording times. The proposed response target is 2-3 seconds, subject to measurement. Existing large-v3 CPU results fail conversational latency; selecting the interactive ASR profile requires smaller-model measurements. A mock or canned classifier never counts as a measured language model. eSpeak may serve as an explicit intelligibility-first local TTS baseline, not a claim of natural patient speech.

## Delivery

Follow phases and review checklists in pms-api-todo.md. Add focused tests with each implementation phase, then integration/fault checks and two final review passes. Hardware, real target RAM, live identity/provider deployment and clinical approval are separately reported. Scenario authoring UI, automated grading, remote viewing, durable offline resume and cloud conversation are deferred.
