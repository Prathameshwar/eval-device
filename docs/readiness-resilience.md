# Readiness resilience: `PMS: llm_unavailable` on Start microphone

Completed 2026-09-20. Pressing **Start microphone** could refuse a question with the bare code `PMS: llm_unavailable`, intermittently, before any audio was recorded. This records the cause and the fix. No provider credentials, quotas, model choices or retry rules for submissions were changed.

## What was happening

`Start microphone` calls `Controller.preflight()`, which checks speech and response readiness concurrently. For a cloud response model the second check is `GET /connections/{id}/status` on PMS, and PMS then probes the provider itself with `GET {provider}/models` inside `LLMClient.health()`. That probe had a hardcoded five-second budget and no retry, so a timeout, a transport fault or an unmapped non-200 became `llm_unavailable`.

Three separate decisions turned one missed window into a refused question:

1. **The probe gave up after one attempt.** Five seconds is enough for a slow DNS resolution, a TLS handshake through a proxy, or a provider cold start to miss it.
2. **The desktop treated the failure as fatal.** `readiness()` tolerated only the busy codes, so every other code aborted the turn before recording.
3. **Nothing named the error.** `pms_client` had no message for `llm_unavailable`, so it fell back to printing `"PMS: " + code`.

It looked intermittent because a successful preflight is cached for fifteen seconds. The next press usually skipped the probe entirely, which is exactly what [the simulation run](simulations/alex-cardiology/findings-2026-09-20.md) recorded as finding 3: question 1 failed after about 5.1 seconds, question 2 proceeded normally.

## The fix

**The probe retries what a second attempt can change.** `LLMClient.health()` now makes up to `PMS_HEALTH_ATTEMPTS` attempts, each bounded by `PMS_HEALTH_TIMEOUT_SECONDS`, with 0.25 s then 0.75 s of backoff and the whole probe bounded by `health_deadline`. Only `llm_unavailable` is retried, which is precisely the code meaning "no usable answer arrived". Rejected credentials, a missing deployment, a model the catalogue does not list, a malformed body and an explicit busy signal are decided answers, raised on the first attempt. Retrying a 401 repeatedly can lock a provider account, so that distinction is load-bearing rather than cosmetic. The local model server in `local_llm.py` gets the same treatment.

This is safe here and nowhere else in that client: the probe is a credentialed GET of the model catalogue, with no side effect and no inference billing. **A submission whose outcome is unknown is still never resent.** `test_non_busy_errors_never_retry` continues to assert that `llm_unavailable` during an actual turn produces exactly one call.

**An unanswered probe warns instead of refusing.** A new, deliberately narrow `SOFT_READINESS_CODES` (`llm_unavailable`, `llm_timeout`) marks the leg unproven and lets capture proceed. The health line reads:

> Unverified: the response model did not answer a readiness check after 10.2 s. The question will still be sent and will report its own result.

Each leg is timed and named separately, because the original failure could not be attributed to a provider at all. That closes the diagnostic half of item 3 in [the fix plan](simulations/alex-cardiology/fix-plan-2026-09-20.md), which asked for readiness probes tagged separately with safe status and timing, bounded retry on read-only checks, a short freshness cache, and authentication or configuration failures preserved as actionable errors. A successful model-list probe is still never treated as proof that inference works.

The reasoning is that a probe is not the turn. It has already been retried at the source, the submission reports its own outcome through the existing error and busy-retry paths, and discarding a question the operator is about to ask is the worse failure. Codes that cannot change still stop the turn before audio is recorded, because capturing a question against a rejected key or an exhausted quota only wastes it.

**A degraded check is not cached.** A proven pair is still cached for fifteen seconds; an unproven one is not, so a provider that comes back is noticed on the next question instead of being assumed bad.

**The error reads as a sentence.** `llm_unavailable` now says that PMS could not reach the provider and to check the connection in PMS if it persists.

## Settings

```dotenv
PMS_HEALTH_TIMEOUT_SECONDS=5   # per attempt
PMS_HEALTH_ATTEMPTS=2          # 1 restores the previous single-attempt behaviour
```

Two attempts is the default rather than three. Because an unanswered probe now degrades to a warning, giving up slowly buys nothing: one retry fixes the single missed window this was reported for and keeps the wait before recording near ten seconds. A healthy provider answers on the first attempt, so nothing was added to the normal path. Raise it for a genuinely flaky link.

The local model server uses three attempts, set as constants in `local_llm.py`. Loopback refuses instantly, so extra attempts there cost only the backoff rather than a network timeout each.

## Deliberately not changed

The local speech service readiness in `audio_client.preflight` keeps one attempt inside one deadline. Retries were written there and then reverted: they broke two invariants the existing tests enforce on purpose, a single attempt and a bounded total deadline, and that service is on loopback where a stall is a real local fault the operator should hear about promptly rather than a network blip worth re-asking. There is also no measurement showing that path is flaky; the reported failure was the cloud provider leg.

`asyncio.gather` in `preflight` still does not cancel the sibling check when one leg fails hard. That is pre-existing and was left alone.

## Verification

| Package | Tests | New |
| --- | --- | --- |
| `platform/api` | 217 passed, 163 skipped | 13 in `tests/test_llm_providers.py` |
| `human-test` | 246 passed, 6 skipped | 17 in `tests/test_readiness_resilience.py` |

Ruff, Ruff format and mypy pass in both (58 and 18 source files). Every one of the 163 platform skips is a PostgreSQL integration test requiring `PMS_TEST_ADMIN_DSN`, which was not configured for this run; the 6 desktop skips are the opt-in resident-Qwen and installed-voice checks.

The new tests cover a transient failure retried until the provider answers, a provider 502 treated as transient, exhausted retries reporting the transient code, seven decided answers each asked exactly once, the whole probe staying inside its deadline when every attempt hangs, the default attempt count and deadline, a local server still loading its weights being given another chance, degradation warning without raising for each soft code, the warning naming the leg and its wait, both legs named together, a degraded check not being cached, a proven pair being cached, and five decided codes still refusing before any audio is recorded.

## Limits

No live provider or live PMS deployment was called; every test drives a mock transport, so per the repository rule these are local tests and not live verification. The attempt counts and backoff are reasoned defaults, not values tuned against a measured failure rate, because the underlying network cause of the original failure was never isolated and is still unverified. Whether a warned-but-unverified turn is preferable to a refusal in a given deployment is a policy choice; `PMS_HEALTH_ATTEMPTS=1` plus removing the code from `SOFT_READINESS_CODES` restores the old behaviour exactly.

One unrelated flake surfaced during these runs and was left alone: `human-test/tests/test_video.py::test_recording_dates_unique_names_private_playable_and_preview` compares a filename minute against a timestamp captured before recording, so it fails when the two straddle a minute boundary.
