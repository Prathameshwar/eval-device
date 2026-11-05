# Local audio simulation

Run from the repository root using the normal Windows account that owns the installed local model:

```powershell
human-test/.venv/Scripts/python.exe docs/simulations/local-audio/run.py --output .test_artifacts/local-audio-check
```

Start the assigned LLM, Whisper large-v3 and synthesis services in Manage Local Models first. The runner connects through the shared inference client on port 8790; it never downloads, starts or stops model services and makes no cloud calls. Use the Windows account that owns the manager state, or configure the central state directory. Model services remain running when the simulation exits.

Twelve questions are asked for each of two seeded cases (cardiology and respiratory), with quiet speech, background noise and an internal pause. Generated 16 kHz PCM replaces the PortAudio device, while the real callback queue, endpointer, continuous listener, central recognition client, controller and hidden desktop UI execute normally. There is no physical recording or audible playback. Case publication is a local fixture, and metrics go to an in-memory observer; the app database is unchanged.

`result.json` contains actual transcripts, answers, selected topics, capture quality, stage timings and UI errors. `questions.json` and `inputs/` retain the prepared fixtures. A `topic_match` is a topic-selection check, not an independent clinical-validity assessment. Read the actual answers as well.

The fixture's answer mode is preserved. An optional `--answer-mode generated` tests guarded paraphrasing for this simulation alone. It does not change the saved profile. The original verification used the saved authored mode: Qwen selected topics and the application returned authored answers.

See [measured results and confirmed fixes](../../local-audio-verification-20260921.md).

For the expanded interview, `questions-50.json` assigns 25 questions to each case, covering all 32 available topics across the two cases. Expected topics are evaluation metadata only: the controller receives the captured audio and normal case selection, never an expected topic or answer. The file includes short contextual follow-ups, an explicit two-topic question and the previously failing associated-symptom wording. The model prompt, production routing and saved configuration remain unchanged.

```powershell
human-test/.venv/Scripts/python.exe docs/simulations/local-audio/run.py --questions docs/simulations/local-audio/questions-50.json --output .test_artifacts/local-audio-50-20260921
human-test/.venv/Scripts/python.exe docs/simulations/local-audio/report.py .test_artifacts/local-audio-50-20260921/result.json docs/local-audio-50-questions-20260921.md
```

Use a new output directory for each run; the runner refuses to overwrite an existing result. The report exports actual transcripts and answers into Markdown and CSV, including failures, expected case answers, selected topics, UI state and stage timings. Topic matching requires the exact expected topic set; the CSV also checks whether the expected authored answer is present. Neither is a substitute for reviewing whether the answer responds appropriately to the question.

The next set, `questions-50-nephrology.json`, changes to Nephrology: 25 flank-pain questions and 25 kidney-condition follow-up questions. All 50 phrasings differ from the preceding set. Case selection is read from the question file and validated against the existing seed catalog; expected topics must exist in the selected case. History resets on each case change, including two cases in the same specialty. The exporter groups answers by case and retains the case code/title in the CSV.

```powershell
human-test/.venv/Scripts/python.exe docs/simulations/local-audio/run.py --questions docs/simulations/local-audio/questions-50-nephrology.json --output .test_artifacts/local-audio-50-nephrology-20260921
human-test/.venv/Scripts/python.exe docs/simulations/local-audio/report.py .test_artifacts/local-audio-50-nephrology-20260921/result.json docs/local-audio-50-nephrology-20260921.md
```

The original questions, raw results and reports remain separate. Question-file expectations are never passed to the production controller or model.
