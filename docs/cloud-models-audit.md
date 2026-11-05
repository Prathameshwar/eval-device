# Local/cloud model audit

Implementation and review evidence for the eight phases in [the plan](cloud-models-plan.md).
This work uses the current `0014_patient_dialogue` changes as its baseline and adds
`0015_cloud_models`; it does not alter the earlier migrations or SQL baseline.
Existing application services and the application database are not restarted or
migrated beneath the user's parallel session.

## Review 1 — correctness and security

First review findings and fixes:

| Finding | Fix | Verification |
|---|---|---|
| Two remote patient calls could reserve 4,096 while allowing 8,192 output tokens | Reserve both budgets; raise the database bound; authored mode reserves only routing | PostgreSQL API test with 4,096 per call and 8,192 reservation |
| Turn usage represented one completion | Aggregate both calls, retain routing/voice usage and provider call count; missing usage remains unknown | Provider usage and two-call API tests |
| New speech path initially awaited recording completion | Tracked concurrent recording task, fenced status update and bounded shutdown; response reports pending/saved/failed | Slow-storage regression verifies transcript arrives before recording completion |
| A separate speech allowance could bypass organization processing quotas | Combine speech, processing and training daily audio/concurrency counts under the organization lock | Admission tests and full processing/training regressions |
| Speech could complete after profile/connection/scope changes | Check route revision/hash and active identity near dispatch and before result publication | In-flight configuration-change test; scoped reads |
| An unknown cloud submission could be replayed with the same key | Persist unknown outcome and return existing status; no provider retry | Timeout and duplicate-race tests |
| Main client status only recovered LLM requests | Track speech request identity separately and recover its transcript without resubmitting | Client unknown-outcome tests |
| Model settings dialog could try to recreate a just-saved profile | Refresh its selected profile identity/revision after saving | Selection workflow review |
| Repeated microphone readiness checks added cloud round trips | Short bounded readiness cache; server still checks configuration on every request | Client readiness/revision regression |
| New optional request fields changed a legacy fingerprint test's expected shape | Exclude absent profile fields, preserving the previous stored fingerprint | Legacy idempotency regression |
| Parallel launcher styling changed exact output formatting | Preserve the styling and make the existing assertion verify reuse semantics | Launcher regression suite |

First review checks are in `.test_artifacts/cloud-models`. Initial cloud tests:
11 passed, including isolated PostgreSQL, two-call accounting, cloud recordings,
scope denial, profile fencing and concurrent LLM requests. Subsequent tests extend
this coverage; final counts are recorded after the second pass.

## Review 2 — final behavior and compatibility

Second review findings and fixes:

| Finding | Fix | Verification |
|---|---|---|
| A first recording failed when the storage root did not exist | Validate existing path components, create the private speech directory, then save | Real temporary storage and authenticated audio-download regression |
| Windows ACL preparation could block the async loop | Perform filesystem/permission preparation in a worker thread | Slow-storage test returns the transcript in under 600 ms while a 600 ms write remains pending |
| A restart could leave completed requests with pending recordings consuming capacity | Recover expired recording leases independently of transcription status; preserve completed text | Both running and completed stale-lease regressions |
| Short media retention could reset daily speech allowance | Charge durable, atomic audit duration metadata, retained for at least one full day | Quota remains charged with no speech media rows |
| A stale identity could pass a long speech access check | Reload identity after the external readiness check; require a live lease before accepting a transcript | Lifecycle and configuration-fencing checks |
| Model access checks did not retry transient 429/502/504 responses | Five read-only access attempts with bounded backoff and a clear final error | Retry-count and transient-status launcher tests; inference remains single-submission |
| Launcher reuse could verify the default local alias instead of the published choice | Resolve the selected installed local alias for both startup and reuse | QwenMedic selection regression |
| Silence could incur a cloud request; interrupted uploads showed generic errors | Skip unvoiced utterances; retain request identity and direct recovery through Check last request | Client silence, timeout and Hindi pipeline tests |
| Model switches did not refresh language choices | Refresh the setup selector and require English before using Whisper Medical | Client model-switch regression |
| Invalid Whisper header credentials could fail only during dispatch | Reject non-ASCII, whitespace and control characters during configuration | Three invalid-key regressions |
| The parent launch environment could pass bootstrap keys to the desktop | Strip PMS and provider environment variables before launching Human-test | Credential-inheritance regression |
| Migration/grant expectations predated the new columns and table | Preserve existing-column assertions, compare complete ORM/schema mappings, and include least-privilege speech grants | Adoption and deployment-contract reruns |

## Verification record

| Check | Actual result |
|---|---|
| Full PMS suite on disposable PostgreSQL 17 | 246 passed, 2 skipped, 2 failed initially (664.89 s); both failures were stale migration/grant expectations, corrected in affected reruns |
| Cloud speech, routing, accounting, concurrency and migration rerun | 19 passed (84.09 s) |
| Final header-credential validation | 3 passed |
| Shared database, processing and training rerun | 20 passed (137.42 s), including corrected deployment grants |
| Human-test cloud and existing client tests | 30 passed; new parallel speech-output test file excluded from this focused run |
| Launcher tests | 60 passed (6.64 s); public launch entry point also accepts the documented options |
| PMS static checks | Ruff check and format check pass; mypy passes for 55 source files |
| Human-test static checks | Ruff check and format check pass for source, tests and scripts |
| Native Tk Models dialog | Initialized with hidden windows; populated choices and reused saved profile identity successfully |
| Distribution checks | API and desktop wheel/sdist builds pass; new modules/migration included and private runtime state excluded |

The full desktop run also included newly arriving parallel speech-output tests:
37 passed, 1 opt-in skip and 2 Tk initialization failures loading installed Tcl
theme files. A focused repeat passed one and failed one, with a different Tcl
file-loading error. Those in-progress speech-output files were not rewritten by
this work; the cloud Models dialog smoke passed independently. This is an explicit
remaining desktop-environment/parallel-work limitation, not a green full-desktop claim.

The two PMS skips are opt-in native Qwen inference/routing checks, not database
tests. PostgreSQL integration tests were enabled throughout. Evidence is stored
privately under `.test_artifacts/cloud-models`; failed initial runs are retained
alongside successful affected reruns. The full suite was not repeated after every
small fix; final affected suites and static checks provide the follow-up evidence.
The owned disposable PostgreSQL cluster was stopped after verification. Snapshot
comparison found zero changes to existing migrations or frozen baseline files.
Final API/desktop distribution contents were rechecked after the last fixes.

## Verification boundaries

Cloud transport uses mocks, not account credentials or paid inference. Azure
readiness checks verify API access, not the deployed model's inference quality.
Native Whisper/Qwen benchmarks are not repeated against the user's active parallel
services. Raspberry Pi hardware capture/playback and live cloud latency/accuracy
remain explicitly unverified. Both review passes are performed by the same agent.
