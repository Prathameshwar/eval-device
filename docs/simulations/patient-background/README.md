# Patient background checks

The scenario editor's **Patient background** tab accepts five optional areas.
Supply everyday facts in the scenario's supported languages. To permit variation,
add up to three approved details in an area and enable its checkbox. One detail
is selected for the conversation; it does not change when older dialogue is
removed. These are author-supplied choices, not unrestricted model invention.

Clinical facts take priority. Put medications, allergies and symptoms in clinical
history/presentation. Keep background precise: “usually eats rice” does not establish
every meal yesterday. An explicit event can be written as ordinary background text;
no dedicated yesterday/today fields are required.

Saving background changes invalidates the existing language review hashes.
Submit the draft for independent language review and publication. Published cases
and older version 4 cases are preserved. Optional blank fields remain unknown.

`question-matrix.json` supplies 20 background questions plus clinical safety and
general-conversation probes. Expected behavior depends on the authored fixture;
an absent fact should remain uncertain. Repeat enabled-choice questions after
history trimming and recover the same conversation through its idempotent start.
The model must not invent diagnoses or personal events to avoid uncertainty.

Export restoration drafts from the frozen original starter source with:

```powershell
cd platform/api
uv run python ../../docs/simulations/patient-background/export_starters.py ../../.test_artifacts/patient-background-drafts.json
```

This writes two unreviewed version 5 documents. It neither updates the database
nor approves/publishes content. Review them through normal authoring. Customized
legacy background requires the tenant's original export or backup.

The runtime uses one generation, a default local 128-token output cap,
two recent dialogue pairs, and exact native chat-template token counting. Native
capacity is checked before generation; clinical facts and the current question
are never silently truncated. Large authored cases can require a larger model.

Compiler 34 qualifies new English version 4/5 sessions with a compact source-ID
response for personal and clinical questions. IDs must belong to both the fitted
view and pinned sources. The host speaks stored text, preserving quantities,
qualifiers and explicit negatives, and supplies uncertainty for missing subject,
actor or event details. It never makes a second generation to paraphrase or repair
an answer. Clear knowledge questions, greetings and unresolved references use
small separate prompts. Complete, unqualified measurement questions select only
the requested frozen measurements; mixed questions and references retain their
normal context. An unambiguous frequency follow-up can reuse the previously
spoken pinned facts when they contain an explicit frequency, retaining its
completed pair. Clinical references and unmatched speech keep their normal
scope. Missing blood-pressure components remain uncertain.
Unknown source IDs are rejected when evidence exists;
an empty evidence view remains unknown even if the model guesses an example ID.
Other languages and older pinned contexts retain their previous reply contract.

Authored sentences control the voice of personal answers. Keep each sentence
concise and self-contained; combined clauses may be spoken together. Clinical
facts belong in clinical fields. Blank background cannot establish a preference,
pet, past treatment or particular event. This does not add fixed date fields.

PMS stores the compiled background in the immutable conversation snapshot.
Desktop sync saves a scoped durable copy before a completed turn is queued.
This preserves recovery evidence; automatically resuming a GUI interview after
restart is not implemented. Old conversations remain subject to ownership,
permissions, expiry and model-reassignment checks.

Cloud/provider tests use mocks. Native English measurements apply only to the
tested local Qwen installation; Hindi, other models, audio playback and Raspberry
Pi timing require separate qualification.

Run the installed Qwen benchmark separately from tests/builds:

```powershell
cd human-test
uv run python ../docs/simulations/patient-background/benchmark_local.py --output ../.test_artifacts/background-benchmark --baseline-ref d0f0d8ba5e5fefb82de69eee1d2f5c544dacbe9b --rounds 4 --quality
```

Choose a new output directory for each run. It launches its own server on port
17887, at a 2,048-token context with 16 GPU layers, and stops it when finished.
It uses only the frozen fictional starter, makes no PMS/cloud calls, and writes
the private runtime key in the ignored output directory. The baseline receives
the same authored background for a fair policy comparison. Each block's first
request is excluded from warm percentiles; four blocks produce 36 warm samples
per policy. Exact timings are specific to the local hardware and load.

Run the original and additional 25-question native qualifications with:

```powershell
cd human-test
uv run python ../docs/simulations/patient-background/qualify_local.py --output ../.test_artifacts/local-qualification --history rolling --rounds 2 --additional-matrix ../docs/simulations/patient-background/qualification-heldout.json
```

For the positive supplied-fact and measurement/follow-up tests, use
`--matrix ../docs/simulations/patient-background/qualification-provided-facts.json`,
`--background-fixture ../docs/simulations/patient-background/qualification-rich-background.json`
and `--additional-matrix ../docs/simulations/patient-background/qualification-robustness.json`.
The CLI saves each answer incrementally, the exact fictional fixture, raw model
reply, fitted token budget, model timing and a readable answer table. It requires
a new output directory and never sends a request to PMS or a cloud provider.
See [native review evidence](../../patient-background-local-qualification-20261006.md).

The qualification CLI accepts `--gpu-layers 99` for a model-only full-GPU
comparison and `--threads N` for an explicit thread-count comparison. It records
the actual settings and leaves configuration unchanged. The native launcher
checks available VRAM and exact offloading; failures are not silently converted
to CPU runs. Full GPU may leave insufficient memory for Whisper/TTS; the default
20-layer qualification matches the Local Models default. Explicit layer counts remain supported; benchmark_local.py follows config.json/config.local.json.
