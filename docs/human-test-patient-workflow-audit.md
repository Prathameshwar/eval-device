# Alex patient workflow audit

Date: 2026-09-19. Scope: [approved phase plan](human-test-patient-workflow-plan.md), aligned `config.json` prompts within the 2,048-token model budget, and a centered skin-toned manikin with lip movement and blinking.

| Planned item | Implementation | Verification | Status / limitation |
|---|---|---|---|
| One patient, three categories, practical default cases | One Alex, nine bilingual templates, three/category; 22 answer topics and eight observations per case | Local PostgreSQL counts, repeated initialization, version-2 contract validation | Implemented; synthetic, requires educator approval |
| Safe upgrade and preservation | Forward migration 0013; 22 domain tables/383 columns; seed audits, runtime grants | Private backup; two initializer runs; prior non-audit rows unchanged | Applied to local demo; not hosted deployment |
| PMS-backed selection | Catalog, staff case preview, own saved setup, validated save and snapshot | Authentication/scope tests; revision/concurrent-write tests; runtime-grant checks | Implemented; organization-wide administrator permission required |
| Patient context on every turn | Saved ID/revision loaded server-side; visible topic facts only; ownership/lifecycle/hash checks | JSON/SSE/projection/in-flight change tests | Implemented; model routes scripted answers, does not invent new clinical facts |
| Prompt alignment and token budget | Short console default; PMS prompt replaces connection prompt; exact local count, 128-output reserve and 64 margin | Nine initial complaint questions used 641–675 prompt tokens; representative name question 643, matching provider usage | At most 867 of 2,048 tokens budgeted for these initial complaint probes; history/questions vary |
| Handle longer conversations | Trim oldest complete user/answer pairs; preserve mandatory facts/current question; reject oversize mandatory prompt | Budget and desktop history tests | Implemented; no silent loss of required patient context |
| Modern desktop workflow | Patient card/vector portrait, Setup → Conversation, save/restore, editable observations, English/Hindi/auto, explicit microphone, typed input | 20 desktop tests; native Windows fixture screenshots and minimum-size check | Implemented; camera and spoken reply remain separate |
| Centered virtual manikin | Warm skin tone, question left/answer right, controls above/input below; saved temperature/heart rate/SpO₂ and listening/reply status | Rendered Windows review, UI state/binding tests | Implemented; readings are saved initial observations, not live sensors |
| Lip and eye animation | Text-triggered lip movement and blinking, bounded duration, cleanup on cancel/next answer/setup change/close | Desktop timer/completion/cancellation regression; continuous listening preserves expression | Implemented; no capture delay, visual simulation without TTS/audio synchronization |
| Failure handling | No uncertain inference replay, durable request status, cancellation, invalid-routing clarification, actionable UI errors | Existing LLM/desktop checks and new routing/revision tests | Implemented; provider failures remain visible errors |
| OpenAI / compatible endpoints | Existing encrypted/scoped adapters remain; explicit remote context limit and conservative estimate for patient requests | Mock JSON/SSE provider tests, remote output reservations, legacy request compatibility | Implemented; no live cloud claim |
| Review 1 | Schema/security/context review and fixes | Detailed findings in `pms-api-reviews.md` | Complete |
| Review 2 | Native Hindi/English JSON/SSE, prerecorded audio pipeline, final static/full/package checks | Completed below; final code/data/package reinspection and fixes recorded in review evidence | Complete; audio quality/latency limitations remain |

## Actual verification

| Check | Result | Evidence / boundary |
|---|---|---|
| Full PMS suite | **228 passed, zero skipped**, 792.02 seconds | Dedicated disposable PostgreSQL, native Qwen JSON/SSE; two existing Starlette/AnyIO deprecation warnings |
| Post-fix API regression | **85 passed**, 211.09 seconds | Patient practice, generic LLM, OpenAI/compatible protocols, legacy idempotency; cloud calls mocked |
| Desktop suite | **20 passed**, 6.52 seconds | Setup/save/restore, explicit microphone, cancellation, history/context binding, animation and continuous-listening state |
| Local LLM suite | **31 passed, 35 subtests** | Existing runtime/configuration checks in this increment |
| Static checks | Passed | API Ruff, formatting, mypy (49 source files); desktop Ruff and formatting |
| Distribution checks | Four archives passed | PMS/desktop wheel and sdist built; new modules/migration/template included; private runtime/media/model files excluded |
| Actual demo data | Head 0013; one Alex, three categories, nine templates | Private backup, repeat initialization, old rows preserved, runtime grants verified |
| Actual patient routing | All nine complaint questions, edited 37.9 °C, Hindi onset, name/age/temperature and unrelated-question clarification passed | Real resident Qwen3 4B; default English chest case restored afterward |
| Actual desktop integration | Passed | Native Windows window restored setup, saved next revision, received real PMS/Qwen answer and animated manikin; microphone never opened |
| Visual review | Passed | Setup/conversation at 1180×860 and controls at minimum 1080×800; fixture screenshots below |
| Cleanup | Verified | Owned test/demo PostgreSQL, audio, PMS and Qwen processes stopped; associated listening ports closed |

The 85-test run follows the full suite and covers the final compatibility fixes; these are overlapping test sets, not 313 distinct tests. Raw local evidence is under `.test_artifacts/patient-workflow/`: `full-tests.txt`, `regression-tests.txt`, `native-patient.json`, `local-database.json`, `audio-end-to-end.json`, `live-ui.txt` and `package-checks.json`. Both review passes were performed by the same agent; findings and fixes are recorded in [review evidence](pms-api-reviews.md).

## Measured audio quality and latency

Whisper large-v3 ran on CPU/int8 and Qwen3 4B on GPU, using the real audio WebSocket → controller → authenticated PMS → Qwen flow. Input was prerecorded synthetic audio, not a person speaking into the microphone. These two samples do not establish broad accuracy.

| Test | ASR finalization | PMS answer round trip | Observed result |
|---|---:|---:|---|
| English, JSON: “When did the chest pain start?” | 16.390 s | 1.203 s | Exact transcript; Alex answered that it began two days ago, about five minutes per episode |
| Hindi, SSE: “सीने में दर्द कब से है?” | 16.906 s | 0.797 s | **Recognition failed**: transcript was “सी ले में वाट काम से है”; PMS returned the stored clarification instead of inventing a response |
| Same Hindi question typed, SSE | Not applicable | 0.500 s | Correct duration topic and Hindi answer: “यह दो दिन पहले शुरू हुआ। हर बार लगभग पाँच मिनट रहता है।” |

The initial run exposed the Hindi quality failure. Inspection isolated the incorrect ASR transcript; no prompt change was used to force a match to garbled input. The final evidence retains that failed quality sample separately from successful transport/fallback and typed Hindi checks. Whisper large CPU latency and this Hindi recognition limitation remain unresolved; the installed model default was preserved. The lip/eye animation adds no wait to capture or inference and is visual only.

Live Raspberry Pi, camera, physical microphone, hosted deployment, live cloud and clinical validation are outside this verification. Manual observation edits do not clinically reconcile the history; cases remain synthetic staff rehearsal material. No speech synthesis, audio-synchronized lip movement or new video processing was introduced.

Reviewed screenshots use fictional test fixtures: [patient setup](images/human-test-patient-setup.png), [conversation with manikin](images/human-test-patient-conversation.png).

## Larger central manikin

The conversation layout now gives the center 40% of the interview width and the full interview height. Typed input/audio controls moved below the left question panel, while new-conversation/request-recovery controls sit below the right answer panel. Compact case/panel spacing provides additional vertical room. The vector figure fits between its heading and patient details without clipping its feet; skin tone and lip/eye animation are retained.

| Review check | Result |
|---|---|
| Standard 1180×860 window | Manikin drawing bounds increased from 217 px to 343 px tall (about 58%); full figure and observations visible |
| Minimum 1080×800 window | Drawing increased from 175 px to 283 px tall; question, answer and all controls remain visible |
| Desktop regressions | 20 passed, including setup/conversation and animation lifecycle coverage |
| Static checks | Human-test Ruff and format passed |
| Scope | Native Tk visual fixtures only; no microphone capture, service/model restart or API/database change |

Screenshots and geometry evidence: `.test_artifacts/manikin-size/`. The conversation screenshot linked above reflects the larger layout. Both window sizes were visually reviewed; no new runtime tests were added for this presentation change.
