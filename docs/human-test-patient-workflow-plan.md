# Alex patient practice: implementation plan

Recorded 2026-09-19. The user requested a plan first and then authorized implementation and final review. This increment retains one fictional identity, Alex, and the three existing categories. It extends the desktop practice preview, not the Pi training-session runtime or clinical approval workflow.

## 1. Complete the starter data

Create three reusable case templates per category (nine total):

| Category | Cases |
|---|---|
| Cardiology | Chest discomfort interview; palpitations interview; raised blood-pressure follow-up |
| Nephrology | Flank pain interview; painful urination interview; kidney-condition follow-up |
| Respiratory Medicine | Wheeze interview; persistent dry cough interview; fever and productive cough interview |

Every template references Alex. Use the existing version-2 scenario document contract for patient facts, complaints, symptoms, history, vitals, disclosure, bilingual dialogue and instructor content. Records are explicitly synthetic practice examples, not institutionally approved cases. Use forward migrations, atomic seed audits and idempotent initialization; do not alter existing published scenarios or seeds.

## 2. PMS catalog and saved setup

Add authenticated organization routes for listing active categories/identities/case summaries, reading a case for staff preview, retrieving the caller's saved setup, and saving a selection with expected-revision checks. Reuse organization-wide authoring permission plus processing permission; platform administration alone grants no tenant access. One saved setup per organization/user bounds storage. Persist selected IDs, an immutable-for-the-request scenario snapshot, language, revision and timestamps. Validate category/identity/template relationships and vital-sign inputs server-side. Save and audit in one transaction. No new patient identities are created by selection.

## 3. Grounded patient conversation and token handling

Extend the existing PMS completion request with optional saved-setup ID/revision; general LLM calls remain compatible. Reload/recheck the selection and its active catalog records on admission and before returning a response. Bind the reference into request idempotency and durable provenance; a stale revision or lifecycle change cancels the practice response.

> **Superseded on 2026-09-19 for the answering step only.** Single-call routing that returned stored text verbatim made every unanticipated utterance — including "hmm" and "turn to your left side" — emit the clarification line. The current design is the two-call routing/speaking turn in [pms-api-architecture.md](pms-api-architecture.md#patient-practice-turn-routing-then-speaking-2026-09-19); displayed text may now be a guarded rephrasing of authored text. Everything else in this section still holds.

Use the LLM to select relevant scripted answer topics from patient-visible context, then return the stored bilingual answer text. Never display raw routing output; invalid/unknown topics use the case clarification. Instructor-only diagnosis/rubric and `never` disclosures are excluded. This first implementation does not ask a model to invent medical facts or prescriptions. Each request includes the current question, essential context and as much recent history as fits. Trim only oldest complete user/assistant pairs; reject a question that cannot fit with mandatory context. Reserve output capacity and a safety margin.

For the installed llama.cpp service, use its authenticated chat-template and tokenizer endpoints plus the actual context limit; the [pinned server API documentation](https://github.com/ggml-org/llama.cpp/blob/b11046/tools/server/README.md) specifies these read-only operations. Compatible/cloud adapters retain their protocol, with a documented conservative configured budget when exact tokenization is unavailable. Count and label model routing usage accurately; displayed scripted text is not provider-generated output. Preserve JSON/SSE, cancellation, leases, token quotas and no uncertain-generation replay.

## 4. Desktop setup and visual redesign

Open on Setup with patient identity, category/case choices, case summary, language and editable initial vitals. Load/save through PMS; unlock Conversation only after save acknowledgment. Restoring a previous setup still requires explicit Continue/Start before microphone capture. Keep microphone and manual typed input, streaming/non-streaming output, pause, send now, cancel and reset. Changing setup cancels/finishes the current turn and clears history before new context is used.

Use a consistent navy/teal palette, clear typography/spacing, two-step navigation, a patient card, vector medical/category icons and visible listening state. Keep technical identifiers out of the main flow. Use code-native graphics; no external image downloads are required. Retain Qwen3 4B and Whisper large-v3 defaults.

User refinement: center a virtual manikin in the conversation screen, with the question on the left and patient answer on the right, controls above and typed input below. Use a warm skin tone, selected observations and event-driven listening/reply status. This is a visual representation; it adds no camera, physical sensor or speech-output dependency.

Further refinement: animate lips and blink while displaying an answer, using a bounded text-based duration. Stop timers on cancellation, setup change, preparation of the next answer and window close. Continuous capture can resume while the expression finishes, without delaying transcription. This is visual speech simulation, not audio-synchronized lip movement.

## 5. Verification and two review passes

Review 1: data/schema compatibility, atomicity, access and tenant boundaries, snapshot isolation, disclosure filtering, token capacity and failure behavior. Add regression tests and fix findings.

Review 2: rerun affected checks, inspect the rendered desktop, exercise native selected-case JSON/SSE and prerecorded audio through Whisper → PMS → Qwen → scripted Alex answer, verify persistence and setup changes, and check package/private-data boundaries. Run the full disposable-PostgreSQL PMS suite and desktop checks. Hardware microphone/Pi verification, educator approval and live cloud checks are reported separately from local/mock evidence.

Deliver a final audit table mapping requirements to implementation, verification, status and remaining limitations. Maintain the existing TODO and review evidence throughout.
