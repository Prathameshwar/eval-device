# Local LLM follow-up review

Completed 2026-09-19. Scope: the standalone `local-llm` installation, configuration, API client, model residency, Windows launchers, credentials and cleanup. Existing audio/video/platform code and model selection were not changed.

**Confirmed findings were fixed. All 25 unit/regression tests, static checks and native validation passed. No remaining blocking finding was identified for the standalone local runner.** This is a local development capability, not patient-simulation acceptance or a tenant platform API.

## Findings and fixes

| Finding | Fix and evidence |
|---|---|
| The socket timeout did not enforce an overall request deadline. Slow headers or an unterminated SSE event could keep extending a blocked read. | A per-request deadline shuts down the owned loopback socket, interrupting blocked header/body reads. Regression servers deliberately drip bytes; both now stop within the deadline tolerance. Inference POSTs are still sent only once. |
| Simultaneous first launches could collide while creating or reading a partially written API key. | A bounded Windows lock serializes credential creation and reuse. Eight simultaneous callers now obtain the same complete key. Existing keys are preserved. |
| Two installers could write the same download chunks/staging paths concurrently. | An installation lock rejects the second setup before any download or extraction. Cached verified installation remains reusable. |
| Unknown keys in the base configuration were accepted, and non-object JSON could crash with an attribute error. | Both configuration files now use the same explicit key schema and existing type/range bounds. Invalid input fails before model startup. |
| A process termination exception skipped the job and instance-lock cleanup. | Job cleanup is in `finally`, instance-lock release is independently protected, and native exit is confirmed. Cleanup avoids closing a buffered pipe while its reader remains blocked. Failure injection and native normal/abrupt exit checks passed. |
| Malformed stream structures and chunked disconnects could escape the console's controlled error handling. | Message/event types and finish reasons are checked; interrupted HTTP responses become controlled failures. Incomplete replies are not committed to history. Redirects are rejected without forwarding credentials or retrying the request. |
| GPU readiness only checked that some layers were offloaded. | Full and partial GPU readiness now require the exact requested layer count, capped by model layers. Native 37/37 and 17/37 configurations both passed; CPU reports zero offloaded layers. |
| Previously installed runtime directories retained restrictive temporary-directory permissions, and the sandbox account differed from the interactive Windows account. | Restored inherited workspace permissions for the public CPU/CUDA binaries. Restored protected private-state/key ACLs to the interactive account and SYSTEM only. Verified the ACLs and ran setup/start batches under the interactive account successfully. Credentials were not printed or regenerated. New runtime staging already restores public binary inheritance before publication. |

CPU-only setup now explicitly tells the operator to launch with `--cpu`. Attaching with `chat.bat --cpu` is rejected because it cannot change a resident server's device. Documentation distinguishes console generation limits from defaults that trusted direct API clients can override, and explains recovery from corrupt cached files without disabling integrity checks.

## Verification

- **25 tests passed**, including real loopback slow-response/redirect tests, Windows lock conflicts, concurrent key creation, malformed data, cleanup failures, bounded retries, integrity checks and CPU-only installation.
- Ruff check, Ruff formatting and Python compilation passed for `local-llm`. Runtime Python dependencies remain standard-library only.
- The actual `setup.bat`, `start-llm.bat`, `chat.bat` and `start-server.bat` were invoked from outside their folder. Setup reused verified cached assets. GPU/CPU runtimes and the model passed checksum validation before use.
- Missing/wrong API keys were rejected for both model listing and completions. Duplicate starts preserved the resident process. Oversized context was rejected.
- Three sequential English/Hindi/fictional-patient prompts used one resident GPU process. The attached batch client reused it. Full GPU, CPU and explicit partial GPU each produced real replies.
- `/quit` and normal owner cleanup released the process. Force-terminating an owned launcher released its exact native child. The server batch was stopped using a test-owned Windows job and its API port closed. Manual GUI double-click/Ctrl+C interaction was not separately automated.
- A separate run under the interactive Windows account inspected the state/key DACLs and exercised setup, interactive launch and server launch. Only that account and SYSTEM were present in the credential ACLs. This resolves the earlier ACL-inspection limitation for the repaired installation.

## Fresh timing observations

The three warm full-GPU requests, without audio/TTS, measured:

| Synthetic fixture | First content token | Complete reply |
|---|---:|---:|
| english | 0.060 s | 0.119 s |
| hindi | 0.058 s | 0.867 s |
| fictional_patient | 0.069 s | 0.540 s |

GPU startup including integrity checks and warmup: **8.08 s**. Sampled device-wide GPU memory peaked at **2,769 MiB**. The same configured model was loaded once per server, not once per request.

CPU arithmetic smoke test: **0.90 s** complete reply. Explicit 17-layer GPU arithmetic smoke test: **2.74 s**. These use different short prompts and are single-run functionality checks, not a fair comparative performance benchmark. Partial offloading is not assumed to be faster than CPU.

Hindi output is functional but previous awkward phrasing remains a quality concern. Natural Hindi/Hinglish conversations, sustained concurrent load, simultaneous Whisper/TTS on the 4 GB GPU, clinical scenario adherence and Raspberry Pi/Wi-Fi integration remain unverified. No cloud calls, platform/database changes or application database access occurred. Platform/database/audio test suites were not rerun for this isolated scope.

## Review passes and evidence

The first pass inspected source and reproduced failures with new regression tests before fixes. Native validation then exposed the existing on-disk permission problem. The final pass reviewed the finished source, failure-path tests, native results, launcher behavior and account-specific ACL evidence after repairs. Both passes were performed by the same agent.

Repository-root evidence: `.test_artifacts/local-llm-review/` contains `before-fixes.txt`, `verify.py`, `results.json`, `user-account.json`, `checks.json`, the initial setup failure and the host-specific private-account repair script. Only synthetic prompts/replies are recorded. The API key value is absent from reports.
