# Local audio and patient interview verification - 2026-09-21

Ran 12 spoken questions in each of two fictional cases: cardiology/chest discomfort and respiratory/persistent dry cough. The saved local profile selected Whisper `large-v3` on CUDA and Qwen3 4B with a 2,048-token context, 75 routing tokens, and one previous question/answer pair. Its answer mode was authored: the real local model selected a case topic, and the application returned that topic's authored answer.

## Confirmed display and input defects

- Empty or punctuation-only recognition emits no answer-request duration. The desktop divided that missing value by 1,000, raising `TypeError` inside its event pump before rearming it. Fixed the timing display to say `Answer: not requested`; subsequent status updates and questions continue.
- A transcription failure updated the warning text but left the patient badge in `Transcribing`. It now returns to `Listening` while that session is still open.
- A microphone-reader exception left an active audio iterator open and could lose its failure notification when the pending-question queue was full. It now refuses the incomplete question, discards pending work from the failed session, and wakes the worker with the device failure.

Four focused reproductions failed before the fixes (two empty-recognition variants, a stale badge, and a device failure). All pass after the fixes. The full desktop suite passed **326 tests**, with six optional native-model/installed-voice checks skipped. Ruff lint/format and mypy passed.

## Native audio results

- **24/24** normalized transcripts exactly matched the questions; every input produced one completed turn.
- **0** dropped or overrun audio blocks; one input stream opened and closed for the entire interview.
- **0** native Tk callback errors; no pending UI events after empty recognition or the following recovery question.
- Two seconds of idle silence produced no submission. A separate all-zero audio request returned empty recognition, displayed the repeat request, and a following local-model question succeeded.
- Whisper finalization after capture: **0.594-0.844 seconds**, median **0.734 seconds**.
- Local answer stage: **0.922-2.906 seconds**, median **1.125 seconds**.
- Original routing: **22/24** expected topics. Both misses were question 6, accurately transcribed but routed to `symptom_details` instead of `associated`.

## Inputs and actual answers

Question 2 used 30% speech amplitude. Question 5 added deterministic background noise (RMS 180 in PCM16 units). Question 8 joined separately synthesized phrases with 350 ms of extra silence. Other inputs used clean generated speech. These conditions are controlled fixtures, not measured acoustic-room conditions.

| # | Question | Cardiology answer | Respiratory answer |
|---|---|---|---|
| 1 | What is your name? | My name is Alex. | My name is Alex. |
| 2 | How old are you? | I am 35 years old. | I am 35 years old. |
| 3 | What brings you here today? | I get tightness in my chest when I walk uphill. | I have a dry cough that is not going away. |
| 4 | When did your symptoms begin? | It began two days ago. Each episode lasts about five minutes. | The cough has lasted three weeks. It began after a cold. |
| 5 | What makes your symptoms worse or better? | The tightness is in the centre of my chest. Rest usually helps. | My throat feels tickly. The cough is worse when I talk for a long time. |
| 6 | What other symptoms have you noticed? | The tightness is in the centre of my chest. Rest usually helps. | My throat feels tickly. The cough is worse when I talk for a long time. |
| 7 | Have you had any previous medical conditions? | I have no known previous medical conditions. | I have no known previous medical conditions. |
| 8 | What medicines are you taking? | I am not taking any medicines. | I tried an over-the-counter cough syrup for two nights without much benefit. I do not remember the name. |
| 9 | Do you have any allergies? | I have no known allergies. | I have no known allergies. |
| 10 | Do you smoke or drink alcohol? | I do not smoke. I rarely drink alcohol and live with my family. | I do not smoke. I rarely drink alcohol and live with my family. |
| 11 | What is your temperature? | I was told my temperature is 36.8 degrees Celsius. | I was told my temperature is 36.7 degrees Celsius. |
| 12 | What is the capital of France? | Sorry, doctor, I'm not sure. Please ask about my symptoms or medical history. | Sorry, doctor, I'm not sure. Please ask about my symptoms or medical history. |

For question 6, the expected cardiology answer was "I get a little breathless during an episode. I have not fainted or had a fever." The expected respiratory answer was "I do not bring up phlegm or blood. I have no fever or breathlessness."

## Scope and evidence

The simulation exercised the production callback queue, adaptive speech gate, continuous Listener, authenticated local ASR websocket, Controller, native Qwen routing and hidden Tk display. Generated Piper PCM replaced physical microphone input. Saved case documents were loaded from the fictional seed fixtures; PMS publication and the metrics destination were fixture boundaries. No application database writes, cloud calls, speaker playback, camera capture or Raspberry Pi checks occurred. Physical microphone quality, acoustic echo and playback interruption remain unverified.

Private generated WAVs, per-turn events, transcripts, answers and timings: `.test_artifacts/local-audio-20260921/baseline/`. The reusable runner is [run.py](simulations/local-audio/run.py). Raw artifacts are intentionally ignored by Git.

## Additional routing investigation

A direct-text replay reproduced the two original errors without audio. Compared the original prompt and a general instruction distinguishing other symptoms from symptom details on 40 native calls each (the two 12-question interviews plus eight additional questions per case). The original matched 34/40 expectations; the general instruction matched 32/40 and was rejected. Four contrasting examples matched 39/40, still missing the respiratory interview's question 6. A refined example set, tested with previous symptom-detail answers and ten additional phrasings per case, matched 41/44: it corrected the original 24 questions but still misrouted "Any fever or breathlessness?" in both cases and "What additional symptoms do you have?" in the respiratory case. These batches have different contexts; their percentages are not a controlled ranking against each other.

No experimental prompt was applied to production. The saved model profile and one-pair history setting are unchanged. These findings demonstrate that accurate audio does not guarantee correct case-topic selection. Routing reliability remains open; passing a small set of example questions would not establish general correctness. The direct-text evidence is in `routing-comparison.json`, `routing-fewshot.json` and `routing-contrast-examples.json` under the same ignored artifact directory.

The native startup helper's account-specific ACLs briefly prevented a subsequent model restart when the run identity changed. Owner/SYSTEM-only access was restored on the four model state entries, without changing credential contents or model configuration. Subsequent comparisons ran successfully under the owning Windows account. All simulation-owned model processes were stopped afterwards.
