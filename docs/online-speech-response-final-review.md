# Online speech and response final review - 2026-09-20

Scope: the saved Cloud profile in Human-test, Azure Whisper `whisper-audio-to-text`
with `2024-06-01` transcription, and compatible Nemotron `nemotron-3-super-120b`.
The user also requested bounded handling of busy speech/response models. Provider
keys were reused from encrypted PMS storage; no new credential entry or configuration
publication was required.

## Confirmed findings and fixes

1. **Hindi answers rejected by inconsistent optional usage.** A real Nemotron
   routing response reported 366 completion tokens but 394 reasoning tokens. Its
   prompt/completion/total counts were otherwise consistent. The old parser rejected
   the completed answer. Optional breakdowns exceeding their parent are now omitted;
   valid totals and text are retained. Invalid types, negative/unbounded counts,
   malformed objects and inconsistent top-level totals still fail. JSON and SSE
   regressions cover this behavior. Reasoning is never counted twice.
2. **Cached speech result crossed a changed department scope.** Reproduced for both
   staff and device callers: GET correctly denied the old recording after reassignment,
   but a duplicate POST returned the cached transcript. Duplicate submissions now use
   the same result-read authorization as GET. Restoring authorized scope still returns
   the original cached result, with exactly one provider submission.
3. **New conversation retained the old speech recovery key.** Reset now clears both
   speech and response references, preventing Check last request from recovering a
   previous conversation's transcript into the new one.
4. **Busy rejection immediately stopped microphone mode.** Human-test retains one
   bounded utterance in memory and retries only the rejected stage after 1, 2 and
   3 seconds, at most four total attempts. A busy LLM reuses the transcript. Each
   explicit rejection gets a new attempt key; an admitted failed request continues
   to retain its immutable failure. The window shows queued/retry progress and
   resumes its normal listening cycle after success. Persistent busy errors stop
   listening only after exhaustion; Pause cancels the wait immediately.

Retries are limited to `speech_busy`, `llm_busy` and `concurrency_limit`. There is
no automatic resubmission after partial response delivery, network interruption,
timeout, unknown submission outcome, credential/configuration error or exhausted
daily quota. Unknown speech and response outcomes retain recovery keys and direct
the operator to Check last request. A cloud readiness busy response permits capture;
the subsequent submission still checks the current identity, route, policy and
capacity. Local speech readiness is still required.

## Verification

- Full API run: 175 passed, 136 database-dependent cases skipped without a test DSN.
- Separate disposable PostgreSQL run: 125 passed across cloud speech, LLM providers,
  LLM API and provider API tests. All provider calls in these tests were mocked.
- Full Human-test run: 138 passed, four opt-in installed-voice checks skipped.
  API and affected desktop lint/format checks and both mypy runs passed.
- Live through the actual desktop controller: English and Hindi identity questions
  passed; English complaint transcription plus generated patient response passed.
  Streaming display, language preservation, saved-result recovery and authorized
  audio round trips were verified. The complaint response used both routing and
  generated wording calls.
- A rapid subsequent Hindi complaint hit a real Azure HTTP 429. The three busy
  retries exhausted and the final speech attempt was retained as failed. It was not
  an unknown submission. After this rejection, two separately submitted synthetic
  complaint checks passed: Hindi with SSE (7.11 s), and English with JSON (5.81 s).
  Both used routing plus generated wording, preserved the language, recovered the
  saved answer/transcript, and retrieved the matching private WAV with `no-store`.
- Earlier completed SSE checks took 1.70 s for English identity, 3.83 s for Hindi
  identity, and 4.16 s for English complaint. Timings start after synthetic frames
  become available and are single observations, not a latency benchmark.
- The final fresh launch selected Cloud with no local ASR/LLM engine. Saved profile
  hash and patient-selection revision were unchanged. Check-owned services stopped.

Tests used fixed synthesized questions, not microphone recordings. Physical
microphone/speaker quality, Raspberry Pi hardware and clinical accuracy are outside
this verification. TLS/hostname verification, exact endpoint allowlists, DNS pinning,
encrypted credentials, private recordings and bounded quotas remain enabled.

Redacted evidence is under `.test_artifacts/online-final-review/`: parser/usage
diagnostics, `client-first-three-complete.json`, `client-result.json`,
`live-result.json` and `db-tests-rerun.txt`. No transcripts, answer text, credentials
or signed media URLs were added to the review logs.

Final review covered bounded retry admission, cancellation, partial/unknown outcome
protection, conversation history, authorization on cached results, provider metadata
validation, credential handling and saved configuration. No unresolved implementation
findings remain in this scope. Provider rate limits can outlast the requested six
seconds of backoff; in that case the UI reports exhaustion and stops listening.
