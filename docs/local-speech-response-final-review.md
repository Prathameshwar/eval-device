# Local speech and response review

Date: 2026-09-20. Scope: installed local speech models and Qwen through the actual
Human-test controller, authenticated audio WebSocket, PMS HTTP API and PostgreSQL.
Tests used fixed English/Hindi audio, fictional patient data and fresh isolated
database clusters. External model calls were disabled. Saved Cloud defaults,
credentials and application model configuration stayed unchanged.

## Finding and fix

Whisper turbo identified the short Hindi identity question as Urdu in Auto mode.
Its transcript used a different script, so the English/Hindi patient workflow
answered in English. Explicit Hindi already worked. Whole-clip and segmented
recognition gave the same result, ruling out lost input at the streaming boundary
for this fixture.

The Whisper adapter now checks automatic detection against its advertised
English/Hindi choices. If another language wins, it selects the supported language
with the highest model probability before consuming the lazy transcript generator.
It retains `task=transcribe`, model residency, input/output bounds and the existing
inference deadline. Explicit language selections are unchanged. Missing supported
probabilities fail explicitly. This does not add cloud calls or replay a submitted
LLM request. It does not extend the service to additional languages.

Four new regressions cover Hindi selection, English selection and two missing-
candidate cases. They also verify that unsupported-language output is never
decoded. A fresh real stack after the fix passed English and Hindi in Auto mode;
the Hindi transcript and patient answer both used Hindi.

## Real local calls

The initial matrix completed all 12 audio-to-response requests. Completion alone
does not establish correct recognition: two fixtures exposed the language issue
above and the Nemotron limitation below. The fixed turbo pair was then repeated
end to end in another fresh database, bringing the total to 14 audio turns.

| Speech model | Response model | English onset question | Hindi name question |
|---|---|---|---|
| Whisper small / CUDA | Qwen3 4B | Expected topic and answer | Hindi transcript and answer |
| Whisper medium / CUDA | Qwen3 4B | Expected topic and answer | Hindi transcript and answer |
| Whisper large-v3 / CUDA | Qwen3 4B | Expected topic and answer | Hindi transcript and answer |
| Whisper large-v3-turbo / CUDA | Qwen3 4B | Expected topic and answer | Passed after Auto-language fix |
| Nemotron 3.5 streaming / CPU | Qwen3 4B | Recognition failed; returned an acknowledgement | Hindi transcript and answer |
| Whisper large-v3 / CUDA | Qwen3 1.7B | Expected topic and answer | Hindi transcript and answer |

English used streaming PMS responses; Hindi used JSON. Checks verified response
events, two-entry conversation history, one speaker-dispatch event, saved-result
recovery and native-tokenizer budgets within the 2,048-token context. Generated
onset answers used the real routing and patient-wording calls. Name questions used
real routing followed by the authored patient identity answer.

On this RTX 500 Ada laptop, Qwen used 16 GPU layers alongside Whisper. Initial
successful Whisper/Qwen turns took 3.77-5.83 seconds including paced audio; corrected
turbo reruns took 8.06 seconds for English and 5.62 for Hindi. These are individual
functional observations during development, not a controlled speed comparison.
A separate real CPU-only Qwen 4B patient identity request succeeded in 33.70 seconds
with saved-result recovery; that full patient request is much slower than a short
direct-model probe.

Every selected model pair activated through the real authenticated desktop control
client and launcher. Replaced processes exited, unchanged models remained resident,
and reselecting the active pair kept the same processes. The isolated checks started
only on free model/API ports and stopped only their own services. All saved Cloud
configuration hashes matched before and after both runs.

## Remaining limits

Nemotron speech produced the same incomplete English result with whole-clip and
incremental decoding, in both Auto and explicit English. Incremental framing
preserved every PCM sample. Hindi succeeded in all four comparisons. Its language
option is set before samples, consistent with the
[upstream per-stream language contract](https://k2-fsa.github.io/sherpa/onnx/nemo/nemotron-streaming.html).
This fixture still fails recognition in the installed configuration; it must not
be counted as a correct patient response. No weights, decoder defaults or guards
were changed to conceal that result.

Qwen 1.7B passed these two questions, but its previously observed Hindi onset and
medication-routing failures remain documented in the
[smaller-model review](smaller-qwen-review.md). These narrow checks do not supersede
that evidence. Whisper large-v3 with Qwen 4B remains the established local pair.

Incomplete Vosk/medical installations were excluded from discovery and were not
tested natively. Physical microphones, acoustic conditions, audible playback,
Raspberry Pi hardware and long-running load were not tested. Speaker dispatch was
checked without playing audio. Automatic English/Hindi selection can still make
recognition mistakes within those two languages.

## Verification and final inspection

| Check | Result |
|---|---|
| Audio suite after the fix | 167 passed |
| Launcher and local-LLM suites | 139 passed, plus 39 subtests |
| Full Human-test suite | 138 passed; four opt-in installed-voice tests skipped |
| Full API suite | 175 passed; 136 database/opt-in tests skipped without a dedicated test DSN |
| Audio, desktop and API lint/format/types | Passed |
| Launcher/local-LLM lint/format | Passed |
| Native initial matrix | 12 completed requests; recognition limits distinguished above |
| Native corrected turbo flow | English and Hindi passed, including saved recovery |
| Native CPU Qwen | One patient request passed |

The skipped pytest database cases were not pointed at an application database.
Native checks separately exercised PostgreSQL in newly created private clusters.
Existing upstream deprecation warnings remain. Final source inspection confirmed
unchanged authentication, recording, queue limits, credentials, publication logic,
explicit-language behavior and protection against replaying uncertain submissions.
Documentation now distinguishes cloud speech retries from local streaming errors.

Run evidence is under `.test_artifacts/local-final-review`: `result.json` retains
the initial findings, `corrected-result.json` records the fixed native flow, and
`recognition-*.json` records the comparisons without transcripts or media. Temporary
operational state remains private. No cloud inference or model download was used.
