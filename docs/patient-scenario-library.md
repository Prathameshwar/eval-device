# Patient Scenario Library

Recorded: 2026-09-18.

Next delivery: [practical phase-wise implementation plan](patient-scenario-implementation-plan.md). It prioritizes fixed-state patient interviews; live state changes and new generated-answer behavior remain later work.

Status: agreed product direction and feature baseline for the next planning and implementation cycle. This document records requirements; it does not claim that the features below are implemented. The current executable scope and acceptance limits remain in the [patient interview pilot](patient-interview-pilot.md), [training runbook](../device/training/README.md), [TODO](pms-api-todo.md), and [review evidence](pms-api-reviews.md).

Current software update (2026-10-01): tenant-owned specialties, fictional profiles, cases, case-to-draft copying, separate clinical review, immutable scenario publication, rehearsal selection and instructor-scoped training are implemented in the API and web console. Reviewed bilingual version 3 cases can be converted into the signed version 1 device runtime while preserving the published source fingerprint. This remains software behavior; educator approval of facts/translations, physical device identity attestation, actual manikin execution and hosted rollout have separate evidence gates in the [tenant clinical plan](tenant-clinical-ownership-plan.md).

## Purpose

A Raspberry Pi installed inside a manikin represents a simulated patient for training and practice. The Pi receives microphone/camera input and provides speaker output, with display or physical effects only where suitable hardware exists. A Wi-Fi-connected laptop performs local processing. In cloud mode, the Pi requests processing directly through the platform API; the laptop is not required for that mode. Cloud conversation implementation and live verification remain deferred.

Assigning a **Patient Scenario**, also called a **Clinical Simulation Scenario**, determines who the patient is, their condition, their initial vital signs, what they know, and how they may respond. The same manikin can represent different patients in different sessions, such as a cardiac patient today and a kidney patient tomorrow.

Call the authoring and management feature the **Patient Scenario Library**. The exact answering logic, generation prompts, models, and clinical response behavior will be designed later. Capture the required facts and policies first.

## Terminology

| Term | Meaning |
|---|---|
| Patient profile | Fictional identity, demographics, language, background, and clinical history. |
| Clinical case | Presenting complaint, underlying condition, severity, associated problems, and relevant clinical findings. |
| Patient state | Current vital signs, symptoms, pain, consciousness, and emotional state; initially authored and later changeable through controlled events. |
| Patient scenario | A profile and clinical case, initial patient state, conversation/disclosure rules, and learning objectives. |
| Simulation session | One training attempt using a particular approved scenario version on a particular manikin. |
| Device configuration | Hardware, connectivity, processing models, voices, and supported capabilities; separate from the fictional patient's clinical facts. |

A disease label alone is insufficient. Patients with the same condition can differ in severity, symptoms, history, knowledge, and behavior. A reusable profile or template must resolve to a fixed snapshot in each approved scenario version so later edits cannot alter an existing session.

Implemented reference data (2026-09-19): three [clinical categories](../platform/db/scenario-categories.md) and one [fictional identity named Alex](../platform/db/patient-identities.md). Alex's demographics/background are stored separately for future reuse. Selecting an identity into a scenario, clinical presets and manikin assignment are subsequent work; the existing scenario snapshots remain unchanged.

## Feature requirements

| Feature | Required capability |
|---|---|
| Scenario library and templates | Create, copy, search, and organize scenarios by specialty, condition, difficulty, language, and learning objective. Allow multiple conditions in one patient. |
| Patient identity and demographics | Fictional name, age, relevant sex information, occupation, preferred language, height, weight, and background. Distinguish simulated attributes from the physical manikin. |
| Presenting complaint and symptoms | Main complaint; onset, duration, location, severity, triggers, and relief. Record symptoms present and relevant symptoms absent. |
| Initial vital signs | Temperature, heart rate, pulse rate/rhythm/strength, blood pressure, respiratory rate, oxygen saturation, and pain score. Record units and validate values. Heart rate and peripheral pulse may differ when explicitly authored. |
| Clinical history | Previous illnesses, surgeries, admissions, medications, allergies and reactions, family history, and social history. Distinguish absent, unknown, and not remembered facts; whether a learner asked about a fact is session state. |
| Patient knowledge and disclosure | Define what the patient knows, volunteers immediately, reveals only when asked, or cannot answer. Keep instructor-only diagnosis, scoring criteria, and answer keys outside patient-facing model context unless a fact is explicitly patient-known. |
| Approved answer bank | Fixed answers for important questions, approved alternative phrasing, answers assembled from structured facts, and clarification/out-of-case responses. |
| Future LLM response policy | Define where generation is permitted and where wording must remain exact. Generated responses must remain grounded in approved facts and must not invent history, alter vital signs, or expose instructor-only information. Enforcement and evaluation require a later design. |
| Patient behavior | Authored emotional state, cooperation, medical understanding, and response length. Examples include calm, anxious, distressed, confused, or reluctant. Do not infer behavior from demographic stereotypes. |
| Language and voice | Hindi, English, and mixed-language expectations; voice, speed, tone, and pronunciation. Preserve clinical facts across languages. Optional recorded speech, coughs, or other sounds can follow later. |
| Examination findings and investigations | Authored examination observations, heart/lung sounds, laboratory results, ECGs, images, and reports, with explicit rules for when the learner can access them. |
| Patient monitor and disclosure | Display configured vitals on the laptop or another supported screen. Distinguish patient-reported symptoms from measurements and examination findings; reveal information according to the scenario. |
| Scenario progression | Begin with instructor-controlled state changes. Later support timed events and validated rules for deterioration, improvement, and intervention effects. An LLM must not independently generate physiological changes. |
| Instructor controls | Preview, assign, start, stop, and reset. Plan explicit pause/resume semantics and controlled overrides, with all changes recorded. A conversational pause must not bypass authorization expiry. |
| Learning objectives and assessment | Expected history questions, communication skills, observations, and educator-authored rubrics. Use manual assessment first; automated assessment remains a later addition. |
| Session record and debrief | Associate audio, video, transcript, responses, patient-state changes, playback acknowledgments, and feedback with the session. Identify whether responses came from approved scripts, generation, or an instructor. |
| Approval, versioning, and access | Draft, review, approve, and retire scenarios. Apply organization/department scope and role permissions. Preserve the exact scenario version used for every session. |
| Runtime readiness and failure handling | Validate required capabilities and prepare approved scenario resources and resident models before starting. Use explicit approved clarification or visible failure behavior; do not silently change clinical facts, switch providers, or repeat uncertain speech playback. |

## Scenario assignment and session behavior

The intended instructor workflow is:

1. Select a manikin and an approved scenario version.
2. Choose an available language and preview the initial patient state, learning objectives, and required capabilities.
3. Load the scenario and obtain confirmation from the responsible device/laptop runtime that the correct version and resources are ready.
4. Start an authorized session with fresh conversation memory.
5. Record responses, state changes, instructor actions, and media against that session.
6. Finish or stop, preserve permitted review evidence, and clear patient context before another session.

Do not silently replace the scenario during an active session. Edits create a new approved version for future sessions. Retirement and authorization expiry must continue to enforce the existing session lease rules; pinning a version does not allow a revoked session to continue. An instructor state override is a recorded session event, not a mutation of the published scenario.

Treat retries according to the operation: reuse stable identifiers for safe repeat submissions, expose unknown outcomes, and never automatically replay speech whose playback outcome is uncertain. Device assignment acknowledgments should identify the intended version so stale readiness cannot start the wrong patient.

## Software state versus physical manikin effects

Configuring a value does not physically reproduce it. With the planned microphone, camera, speaker, Pi, and laptop, software can support conversation and display a simulated patient state. Other physical effects require suitable hardware and control interfaces.

| Configured feature | Physical requirement or limitation |
|---|---|
| Temperature | Warm skin requires heating hardware, sensors, calibrated control, and safeguards. Pi board temperature is device telemetry, not patient body temperature. |
| Palpable pulse | Requires pulse actuators and suitable manikin construction. |
| Heart/lung sounds at examination points | Requires suitable sound hardware or a compatible examination system. |
| Chest movement | Requires mechanical breathing hardware. |
| Height and weight | Remain simulated patient attributes unless the physical manikin matches them. |

The capability model should distinguish configured simulation values, values displayed to learners, and effects physically reproduced. Unsupported physical requirements must be visible before a session starts; a monitor-only version of a scenario must be an explicit choice.

The video service continues to receive, record, and save only. Optional frame extraction remains an offline bulk operation. Recording does not establish that an examination or treatment occurred; use instructor confirmation initially. No video model or live detection is introduced by this feature direction.

## Responsibility boundaries

| Component | Responsibility |
|---|---|
| Raspberry Pi / manikin | Microphone/camera capture, speaker and supported output, device identity, capture/playback acknowledgments, and physical capability reporting. |
| Laptop in local mode | Resident local ASR/dialogue/TTS, authorized scenario execution through the training coordinator, bounded private media storage, and instructor interaction/review. |
| Server platform | Scenario library, authoring/approval/versioning, tenant permissions, session authorization, assignment, learning objectives, feedback, and policy. In cloud mode, mediate Pi requests to configured provider services. |

The existing standalone audio and video APIs retain their separate media responsibilities; they do not gain direct PMS coupling through this document. Scenario orchestration belongs in the training layer. Preserve independent audio/video transport and existing WebSocket-over-TCP support; a new raw TCP protocol is not part of this feature.

Keep runtime/model configuration separate from clinical facts. Keep media private and bounded, enforce organization/department and role scope on each operation, and keep assessment answers inaccessible to learners. Platform administrator status alone must not grant tenant media access. Apply configured retention, avoid sensitive media in logs, and preserve atomic business/audit changes during later implementation.

## Illustrative scenarios

These are catalog examples, not clinically approved case content or prescribed vital values:

- **Adult patient with chest pain - history-taking - Hindi - beginner:** defined background, symptoms, medications, allergies, initial vitals, disclosure rules, approved answers, and interview checklist. An instructor-only diagnosis is not automatically patient-known.
- **Patient with chronic kidney disease - follow-up interview - English - intermediate:** a different clinical history and complaint, with explicitly authored patient knowledge, investigations, and learning objectives.

The same manikin can receive either approved scenario between sessions. Vital signs and responses must come from the authored case; selecting a disease category must not automatically invent them.

## Priorities for the next plan

The next implementation plan should extend the existing pilot rather than build a second scenario/session system. Inspect and reuse current contracts, immutable scenario versions, authorization, and media integration before defining schema or endpoints.

Prioritize:

1. Structured patient profile, clinical case, initial vitals, history, and unit/value validation.
2. Patient-known facts, disclosure rules, approved answer bank, and future generation-policy fields. Defer the new answering algorithm until separately designed.
3. Library authoring, templates, search, educator approval, and versioning.
4. Explicit device assignment/readiness, capability checks, patient-state preview, and separation between session memory and reusable case content.
5. Instructor-controlled state changes, manual assessment, and debrief evidence integrated with the current pilot.
6. Review 1: correctness, tenant/role boundaries, clinical-fact consistency, lifecycle behavior, data integrity, and failure handling; fix confirmed issues and rerun affected checks.
7. Review 2: review the final changes again, verify documentation and acceptance evidence, and report remaining limitations.

Later scope: natural generated conversation, richer voices and sounds, dynamic physiology, physical actuators, intervention-response models, and assisted/automated grading. These require their own designs and validation. No new implementation, model download, deployment, or live cloud call is authorized merely by recording this feature baseline.

Carry forward existing acceptance gaps: representative human Hindi/English/mixed speech, latency and resource use on the actual 16 GB CPU laptop, Pi/Wi-Fi/acoustics, and clinical educator approval. Published product capabilities, local mocks, and synthetic tests do not verify those gates.

## Product reference

PCS describes scenario-specific patient conversation, vital-sign monitoring, instructor controls, recordings, and scenario authoring. Its scenario material also describes configurable states, vitals, sounds, and supporting resources. These are feature references for this proposal, not claims about our implementation or hardware and not permission to copy proprietary clinical cases. See [PCS Alex](https://www.pcs.ai/alex/) and [PCS healthcare simulation scenarios](https://www.pcs.ai/healthcare-ai-simulation-scenarios).
