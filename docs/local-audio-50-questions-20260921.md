# Local audio: 50 questions and recorded answers

These are actual captured answers from the local simulation on 2026-09-21. Expected topics were prepared before execution and are used only for evaluation. They are never passed to the model or application as hints.

Recorded **50/50** planned turns; **48** transcripts match after ignoring punctuation and case; **42** selections match the expected topic set.

Manual review: cardiology matched **23/25** and respiratory **19/25**. The two word-level transcript differences were harmless: question 12 used `0 to 10` for `zero to ten`, and question 41 used American `traveled` for British `travelled`. Question 34 also gained an internal question mark after the deliberate pause (`What treatment? Have you tried for the cough?`); the punctuation-insensitive count does not flag this. Its possible effect on routing was not isolated in this run.

The eight incorrect answers concern associated symptoms (10, 11, 31, 32, 33), cough treatment (34), its contextual follow-up (35), and sleep disruption (38). Question 35 follows an already incorrect treatment answer, so it is not an independent clean test of medication-history recall. The failures remain recorded; none were replaced with expected answers. All 50 turns reached the UI's Complete state. No question-specific production rule, case answer, prompt or saved model setting was changed for this expanded run.

Models/settings: `{"answer_mode": "authored", "asr": "large-v3", "context_tokens": 2048, "device": "cuda", "history_messages": 2, "llm": "qwen3-4b-local"}`. Authored mode means Qwen selects topics and the application returns existing case text. The answer column does not claim freely generated Qwen prose. History is capped at one previous user/assistant pair with this profile; context fitting can reduce it further. Case selection resets history between categories.

Real local ASR, Qwen, listener, controller and hidden Tk UI; generated PCM replaces the microphone; fixture case publication and local metrics sink; no PMS writes or speaker playback. Physical microphone, room acoustics, speakers, cloud services and database persistence are outside this verification. The patient cases are fictional fixtures.

Audio conditions: 30% speech amplitude for quiet inputs; deterministic background noise at 180 PCM16 RMS for noisy inputs; an added 350 ms gap between two synthesized segments for paused inputs. All other questions use clean generated speech.

Post-capture transcription: 0.594-1.094 s; median 0.829 s.

Local answer stage: 0.985-3.329 s; median 1.320 s.

UI callback errors: 0; dropped audio blocks: 0; device status blocks: 0; idle-silence submissions: 0; input stream opens/closes: 1/1.

[Spreadsheet-friendly CSV with transcripts, expectations and timings](local-audio-50-questions-20260921.csv). A topic match is an interview-routing check, not a clinical approval. Repeated answers are preserved exactly; authored mode returns an entire topic answer even for a narrow question.

## Cardiology

| # | Question | Actual answer | Audio | Topic check |
| --- | --- | --- | --- | --- |
| 1 | What is your name? | My name is Alex. | clean | Match |
| 2 | How old are you? | I am 35 years old. | quiet | Match |
| 3 | What do you do for work? | I work as a schoolteacher. | clean | Match |
| 4 | How tall are you and how much do you weigh? | I am 175.0 cm tall and weigh 75.0 kg. | clean | Match |
| 5 | What brings you here today? | I get tightness in my chest when I walk uphill. | clean | Match |
| 6 | When did it start? | It began two days ago. Each episode lasts about five minutes. | clean | Match |
| 7 | How long does each episode last? | It began two days ago. Each episode lasts about five minutes. | clean | Match |
| 8 | Where exactly is the tightness? | The tightness is in the centre of my chest. Rest usually helps. | clean | Match |
| 9 | What makes your symptoms worse or better? | The tightness is in the centre of my chest. Rest usually helps. | noise | Match |
| 10 | What other symptoms have you noticed? | The tightness is in the centre of my chest. Rest usually helps. | clean | MISMATCH: symptom_details (expected associated) |
| 11 | Do you get breathless or have you fainted? | The tightness is in the centre of my chest. Rest usually helps. | clean | MISMATCH: symptom_details (expected associated) |
| 12 | How bad is your pain right now, from zero to ten? | My pain right now is 0.0 out of ten. | clean | Match |
| 13 | Have you had any previous medical conditions? | I have no known previous medical conditions. | clean | Match |
| 14 | Have you ever had an operation? | I have not had any operations. | clean | Match |
| 15 | What medicines are you taking? | I am not taking any medicines. | pause | Match |
| 16 | Do you have any allergies? | I have no known allergies. | clean | Match |
| 17 | Do any illnesses run in your family? | My father has high blood pressure. | clean | Match |
| 18 | Do you smoke or drink alcohol? | I do not smoke. I rarely drink alcohol and live with my family. | clean | Match |
| 19 | What did you eat yesterday? | I eat home-cooked meals three times a day, mostly rice, dal and vegetables. Yesterday I ate the same as usual. | clean | Match |
| 20 | What exercise do you usually do? | I walk to the market most days. I do not do any other regular exercise. | clean | Match |
| 21 | What was your blood pressure reading? | I was told my blood pressure is 128.0 over 82.0 mmHg. | clean | Match |
| 22 | What is your pulse rate? | I was told my pulse is 84.0 per minute. | clean | Match |
| 23 | Are you feeling worried or stressed? | I feel a little worried about this problem, but otherwise my mood is normal. | clean | Match |
| 24 | Who lives with you and helps when you are unwell? | I live with my family in a rented flat. They help me when I am unwell. | clean | Match |
| 25 | What is the capital of France? | Sorry, doctor, I'm not sure. Please ask about my symptoms or medical history. | clean | Match |

## Respiratory

| # | Question | Actual answer | Audio | Topic check |
| --- | --- | --- | --- | --- |
| 26 | Could you tell me your name, please? | My name is Alex. | clean | Match |
| 27 | What is your age? | I am 35 years old. | clean | Match |
| 28 | What problem brought you to the clinic? | I have a dry cough that is not going away. | clean | Match |
| 29 | How long have you had this cough? | The cough has lasted three weeks. It began after a cold. | clean | Match |
| 30 | What makes the cough worse? | My throat feels tickly. The cough is worse when I talk for a long time. | noise | Match |
| 31 | What other symptoms have you noticed? | My throat feels tickly. The cough is worse when I talk for a long time. | clean | MISMATCH: symptom_details (expected associated) |
| 32 | Are you coughing up phlegm or blood? | My throat feels tickly. The cough is worse when I talk for a long time. | clean | MISMATCH: symptom_details (expected associated) |
| 33 | Have you had any fever or breathlessness? | I was told my temperature is 36.7 degrees Celsius. I was told I am breathing 16.0 times per minute. | clean | MISMATCH: temperature, breathing_rate (expected associated) |
| 34 | What treatment have you tried for the cough? | My throat feels tickly. The cough is worse when I talk for a long time. | pause | MISMATCH: symptom_details (expected medications) |
| 35 | Did it help? | Yes, doctor, I am listening. | clean | MISMATCH: backchannel (expected medications) |
| 36 | Have you ever had an allergic reaction? | I have no known allergies. | quiet | Match |
| 37 | Do you have any long-standing illnesses? | I have no known previous medical conditions. | clean | Match |
| 38 | Does the cough wake you up at night? | My throat feels tickly. The cough is worse when I talk for a long time. | clean | MISMATCH: symptom_details (expected sleep) |
| 39 | Has your appetite or weight changed? | My appetite is normal and my weight has not changed. | clean | Match |
| 40 | Can you describe your usual daily routine? | I leave for school at eight in the morning, teach until four, and spend the evening at home with my family. | clean | Match |
| 41 | Have you travelled anywhere recently? | I have not travelled anywhere recently. | clean | Match |
| 42 | Which vaccinations have you had? | I had my childhood vaccinations. I do not remember having any vaccine in the last few years. | clean | Match |
| 43 | Any changes in your bowels or passing urine? | My bowels are regular and passing urine is normal for me. | clean | Match |
| 44 | What temperature was recorded? | I was told my temperature is 36.7 degrees Celsius. | clean | Match |
| 45 | What is your measured breathing rate? | I was told I am breathing 16.0 times per minute. | clean | Match |
| 46 | What is your oxygen saturation? | I was told my oxygen saturation is 98.0 percent. | clean | Match |
| 47 | What was your heart rate? | I was told my heart rate is 80.0 beats per minute. | clean | Match |
| 48 | What sex is recorded for you? | I am male. | clean | Match |
| 49 | What do you usually eat, and do you smoke? | I eat home-cooked meals three times a day, mostly rice, dal and vegetables. Yesterday I ate the same as usual. I do not smoke. I rarely drink alcohol and live with my family. | clean | Match |
| 50 | What is my bank account balance? | Sorry, doctor, I'm not sure. Please ask about my symptoms or medical history. | clean | Match |

## Items requiring review

- **Question 10**: Selected topic differs from the prepared expectation; Answer does not contain the expected authored response. Transcript: 'What other symptoms have you noticed?'. Expected case answer: I get a little breathless during an episode. I have not fainted or had a fever.
- **Question 11**: Selected topic differs from the prepared expectation; Answer does not contain the expected authored response. Transcript: 'Do you get breathless or have you fainted?'. Expected case answer: I get a little breathless during an episode. I have not fainted or had a fever.
- **Question 12**: Transcript differs; inspect intended and recognized question. Transcript: 'How bad is your pain right now, from 0 to 10?'. Expected case answer: My pain right now is 0.0 out of ten.
- **Question 31**: Selected topic differs from the prepared expectation; Answer does not contain the expected authored response. Transcript: 'What other symptoms have you noticed?'. Expected case answer: I do not bring up phlegm or blood. I have no fever or breathlessness.
- **Question 32**: Selected topic differs from the prepared expectation; Answer does not contain the expected authored response. Transcript: 'Are you coughing up phlegm or blood?'. Expected case answer: I do not bring up phlegm or blood. I have no fever or breathlessness.
- **Question 33**: Selected topic differs from the prepared expectation; Answer does not contain the expected authored response. Transcript: 'Have you had any fever or breathlessness?'. Expected case answer: I do not bring up phlegm or blood. I have no fever or breathlessness.
- **Question 34**: Selected topic differs from the prepared expectation; Answer does not contain the expected authored response. Transcript: 'What treatment? Have you tried for the cough?'. Expected case answer: I tried an over-the-counter cough syrup for two nights without much benefit. I do not remember the name.
- **Question 35**: Selected topic differs from the prepared expectation; Answer does not contain the expected authored response. Transcript: 'Did it help?'. Expected case answer: I tried an over-the-counter cough syrup for two nights without much benefit. I do not remember the name.
- **Question 38**: Selected topic differs from the prepared expectation; Answer does not contain the expected authored response. Transcript: 'Does the cough wake you up at night?'. Expected case answer: I sleep about seven hours, but the cough wakes me a few times most nights.
- **Question 41**: Transcript differs; inspect intended and recognized question. Transcript: 'Have you traveled anywhere recently?'. Expected case answer: I have not travelled anywhere recently.

## Empty recognition and recovery

- `empty_asr`: Sorry doctor, I could not hear that properly. Could you say it again? UI: Nothing recognized; asked the learner to repeat; queued UI events: 0.
- `after_empty_asr`: My name is Alex. UI: Complete; queued UI events: 0.

Raw evidence: `.test_artifacts/local-audio-50-20260921/result.json`; the same directory contains prepared questions, generated WAV inputs and service logs. Raw evidence stays in the ignored artifact directory.
