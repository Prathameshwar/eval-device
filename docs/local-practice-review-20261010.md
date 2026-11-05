# Local patient-practice verification - 2026-10-10

The local API, Manage Local Models and Human-test were exercised together against real installed models and a new local tenant. Both desktop apps are left open, and all three inference services are Ready.

## Local setup

- Platform API: `http://127.0.0.1:8000`; web UI: `http://127.0.0.1:3000`.
- Tenant: `Local Models QA 20261010-101017`.
- Device: `GPU Laptop - Local Models QA`, enrolled through the normal device enrollment API and assigned local Qwen 3.5 and Whisper large-v3 through Platform Admin operations.
- Real resident services: Qwen 3.5 4B on CUDA with **20 GPU layers**, Whisper large-v3 on CUDA, Piper English male on CPU. Existing installed weights were reused; no model download or paid cloud call was needed.
- Human-test's private environment now uses the local API with speaker output enabled. Its previous hosted enrollment and environment were backed up privately before switching. Tenant administrator credentials, enrollment responses and the database backup remain in the protected, ignored `.test_artifacts/local-practice-20261010/private/` directory; credentials are not included in this report.
- The application database was behind the checkout at migration 0046. A private PostgreSQL custom-format backup was verified before applying existing forward migrations through 0048 and the existing runtime grant script. No API source, migration definition or database baseline was changed.

## Actual desktop and inference checks

Two published fictional starter scenarios were used: **Chest discomfort interview** and **Wheeze interview**. The final run completed nine typed questions and one synthesized-speech question through actual Whisper recognition and patient inference. The final ten exchanges are available from the authenticated local history endpoint; the API returned ten completed records.

| Check | Observed result |
| --- | --- |
| Chest: reason for visit | Chest tightness when walking uphill, matching the case |
| Chest: onset and aggravating factor | Two days; walking uphill |
| Patient background: job and household | Schoolteacher; lives with family |
| General knowledge | Capital of France answered as Paris |
| Request to reveal hidden instructions | No instructions disclosed; clarification reply |
| Wheeze: reason for visit | Wheezing and tight breathing |
| Wheeze: trigger and relief | Dust; temporary help from reliever inhaler |
| Wheeze: previous episodes | Asthma since teenage years |
| Feelings about the visit | Missing emotional detail now produces uncertainty, without substituting a pain score |
| Synthesized question through real ASR | Recognized the breathing-onset question and answered two days |
| Speaker output | Actual audio writes completed; the user confirmed hearing the answers |
| Physical microphone check | Digital silence reported; Windows microphone consent is Allow. Live spoken microphone conversation remains unverified and needs the input unmuted/checked |
| Manager navigation | Overview, Models, Services, Logs and Settings opened |
| Actual service controls | Stop TTS, observe client not_running, Start TTS, live status, Configure service and View Logs passed |
| Desktop lifetime | Closing each desktop window left all three inference services Ready |
| Canonical Human-test startup | Saved device reconnect, readiness/inventory checks and real desktop child launch passed without the reported TypeError |
| Access boundaries | Inference credential rejected for management (403), anonymous capabilities rejected (401), device access to another organization rejected (404) |

Automation operated the real Tk windows and real API/manager clients. The confirmation for the intentional TTS stop was accepted automatically. Unit/mock results below are separate from this native run. No microphone conversation, camera/video quality, cloud provider, Raspberry Pi, VM deployment or reboot/SCM behavior is claimed as verified.

## Findings and fixes

1. A question about feelings selected an unrelated measured pain score. Shared evidence selection now requires emotional evidence for emotional questions and keeps an unknown answer when it is absent. Known emotional background remains available in mixed clinical questions. Generic questions about current physical feelings still retain current symptoms.
2. The intake wording “What has brought you in today?” did not use the existing narrow presentation scope. Equivalent intake wording now selects presenting facts, removing the unrelated uncertainty sentence observed during the first run.
3. Shared compiler version is 39 so updated clients cannot silently reuse a conversation compiled with older behavior. Start a new conversation after updating the shared package. No API endpoint or persistence implementation was edited.
4. Manage Local Models Settings now describes Human-test's completed central-inference migration accurately and keeps Raspberry Pi LAN access queued.
5. Speaker output was intentionally disabled during the initial typed-only pass. It was enabled for the subsequent native runs and the private launch environment; the user confirmed audible speech. One failed test-only TTS request used a catalog model ID instead of the voice key; the automation was corrected, with no production transport change needed.

Review 1 compared answers with the published fictional case snapshots, checked actual model identity/GPU layers and found the response-selection issues. Review 2 checked known/missing/mixed emotional facts, current-symptom compatibility, immutable evidence acceptance, compiler compatibility, permissions, private artifacts and service ownership. It found and fixed mixed clinical questions dropping recorded emotional background. The affected tests and full native question run were repeated after fixes. Final window-only captures were inspected for the running Human-test setup and manager service layout.

## Verification

- API suite: **614 passed, 406 skipped**. Database/opt-in tests were skipped without a dedicated test DSN; the application database was never supplied as a destructive test target.
- Affected shared conversation/parity tests after the final scope fix: **165 passed, 2 skipped**.
- Human-test broad suite: **572 passed, 2 skipped**; final affected Human-test regression suite: **62 passed, 2 skipped**, including all ten new source-selection checks. Opt-in resident model tests were skipped in these unit runs; real inference is covered separately above.
- Local Models: **132 passed, 50 subtests passed**.
- API Ruff lint/format and mypy passed. Touched desktop/shared/regression Python lint/format passed; Git whitespace checks passed. Existing dependency/workbook deprecation warnings remain.
- Evidence is ignored under `.test_artifacts/local-practice-20261010/`: `desktop-results.json`, `manager-controls.json`, `final-state.json`, test logs and window-only PNGs. Private snapshots and recovery files are excluded from publication.

Windows SCM/reboot auto-start, authenticated LAN/Pi support and separate Local Models packaging remain queued. Existing portable archives were not rebuilt. No VM update was performed. Verification was completed before the subsequent request to commit and publish all pending source changes; private runtime data remains excluded from publication.
