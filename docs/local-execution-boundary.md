# Local execution boundary

Human-test and a future Raspberry Pi consumer use the services managed by
`local-models/`. Human-test currently connects over authenticated loopback;
authenticated LAN/TLS Pi transport is deferred. The platform remains authoritative
for tenant/department/device lifecycle, model assignments, Practice selection,
immutable case/context revisions, language packs, quotas and audit records.

A local LLM route retains `mode=local`, `execution=caller`, the approved alias,
context cap and output budget. Human-test sends its completion to the central
local manager rather than asking the platform to infer. Published native ports
cannot change the client endpoint. Cloud routes execute through the platform API.
Local inference keys never come from PMS: the app uses the manager's private
inference-only `client-key.txt`, not its operator or native worker key.

Platform completion admission still rejects a local connection with
`llm_local_execution_required`; platform readiness declares its configuration
without claiming live inference. Remote provider transport still refuses private
or loopback endpoints. This migration does not modify those platform boundaries.

For local training, Human-test gets its authorized immutable scenario and
conversation context from PMS. The shared conversation compiler fits the prompt
using the running model's exact template/tokenizer through whitelisted manager
inspection calls. One bounded completion selects approved fact IDs when applicable;
evidence, language, snapshot and context guards still validate the answer.
Only successful reviewed results enter dialogue history and pass the durable
speaker gate. Neither provider nor transport repair an uncertain completion by
replaying it. Metadata and explicitly enabled recording/history reporting retain
their existing scoped platform APIs and private bounded journals.

The manager owns resident LLM/recognition/synthesis engines, assets, native
runtimes and CPU/GPU policy. Human-test owns physical microphone/camera capture,
speaker playback and clinical orchestration. Startup/reload only checks model IDs
and readiness. Exiting either desktop leaves the detached manager running;
Windows service registration and reboot startup remain queued.

See [client routes, migration and limits](local-model-client-migration.md),
[platform/client ownership](human-test-api-boundary.md), and
[the queued service design](local-model-service-plan.md). Historical launcher
and latency audits describe earlier implementations; their findings are retained.
