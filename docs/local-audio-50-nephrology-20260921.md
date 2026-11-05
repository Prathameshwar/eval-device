# Nephrology: 50 questions and recorded answers

These are actual captured answers from the local simulation on 2026-09-21. Expected topics were prepared before execution and are used only for evaluation. They are never passed to the model or application as hints.

Recorded **50/50** planned turns; **49** transcripts match after ignoring punctuation and case; **43** selections match the expected topic set.

This changes the category to **Nephrology** and the case topics to **flank pain** (questions 1-25) and **kidney-condition follow-up** (26-50). All 50 question phrasings differ from the preceding cardiology/respiratory set. The cases matched **22/25** and **21/25**, respectively. All 50 turns reached Complete; empty recognition and recovery also completed normally. The only word-level transcript difference was `0 to 10` instead of `zero to ten` in question 12, with the same meaning.

Manual review of the seven topic-check failures:

- **6, 9, 10:** pain-frequency and associated-symptom questions returned symptom-location details. Question 6 needed two model calls and ultimately produced a valid but incorrect topic selection.
- **32, 34:** symptom duration and foamy/bloody urine questions fell back to clarification with `routing_status=invalid` and `answer_source=routing_invalid`, after two calls each. The transcript was correct. These are routing-validation failures; this evidence does not identify the exact invalid response shape.
- **36:** a dialysis-history question was classified as a physical instruction and returned a movement acknowledgement.
- **39:** the expected fluid/salt answer was present, but the model also selected allergies and disclosed an unrelated allergy answer. Exact topic-set checking correctly counts this as a mismatch. This explains why 44 answers contain the expected text while only 43 topic sets match.

The medication follow-up in question 38 stayed on the medication topic and preserved the case's unknown tablet name/strength. Separately, question 11 matches its expected topic but its existing authored wording says `as I mentioned` before pink urine had actually been mentioned in this conversation. Topic matching therefore does not establish perfect conversational quality. All answers, including these defects, remain verbatim.

Integrity check: SHA-256 fingerprints of **37 monitored files** were unchanged across the run, covering desktop/local-model/shared-contract Python source, the seed case catalog, local-model configuration and the saved launcher profile. No question-specific production logic, answers or model settings were added. Only simulation/reporting files were extended. The before/after manifests and `integrity-verification.json` are retained beside the raw results. Both owned model ports, 8787 and 8773, were closed after completion.

Models/settings: `{"answer_mode": "authored", "asr": "large-v3", "context_tokens": 2048, "device": "cuda", "history_messages": 2, "llm": "qwen3-4b-local"}`. Authored mode means Qwen selects topics and the application returns existing case text. The answer column does not claim freely generated Qwen prose. History is capped at one previous user/assistant pair with this profile; context fitting can reduce it further. Case selection resets history between cases.

Real local ASR, Qwen, listener, controller and hidden Tk UI; generated PCM replaces the microphone; fixture case publication and local metrics sink; no PMS writes or speaker playback. Physical microphone, room acoustics, speakers, cloud services and database persistence are outside this verification. The patient cases are fictional fixtures.

Audio conditions: 30% speech amplitude for quiet inputs; deterministic background noise at 180 PCM16 RMS for noisy inputs; an added 350 ms gap between two synthesized segments for paused inputs. All other questions use clean generated speech.

Post-capture transcription: 0.625-1.250 s; median 0.883 s.

Local answer stage: 0.922-3.891 s; median 1.164 s.

UI callback errors: 0; dropped audio blocks: 0; device status blocks: 0; idle-silence submissions: 0; input stream opens/closes: 1/1.

[Spreadsheet-friendly CSV with transcripts, expectations and timings](local-audio-50-nephrology-20260921.csv). A topic match is an interview-routing check, not a clinical approval. Repeated answers are preserved exactly; authored mode returns an entire topic answer even for a narrow question.

## Nephrology: Flank pain interview

| # | Question | Actual answer | Audio | Topic check |
| --- | --- | --- | --- | --- |
| 1 | May I have your full name? | My name is Alex. | clean | Match |
| 2 | How many years old are you? | I am 35 years old. | clean | Match |
| 3 | What is your occupation? | I work as a schoolteacher. | clean | Match |
| 4 | Why have you come to see the doctor today? | I have pain on the right side of my back. | clean | Match |
| 5 | When did the pain first appear? | It started suddenly about six hours ago and comes in waves. | clean | Match |
| 6 | Is it constant, or does it come and go? | The pain moves towards my groin. I cannot find a comfortable position. | clean | MISMATCH: symptom_details (expected duration) |
| 7 | Does the pain travel anywhere else? | The pain moves towards my groin. I cannot find a comfortable position. | quiet | Match |
| 8 | Can you get comfortable in any position? | The pain moves towards my groin. I cannot find a comfortable position. | noise | Match |
| 9 | Have you felt sick or noticed any other symptoms? | The pain moves towards my groin. I cannot find a comfortable position. | clean | MISMATCH: symptom_details (expected associated) |
| 10 | Have you experienced fever or chills with the pain? | The pain moves towards my groin. I cannot find a comfortable position. | clean | MISMATCH: symptom_details (expected associated) |
| 11 | Have your bowel movements or urine changed? | My bowels are regular. I noticed pink urine once, as I mentioned. | clean | Match |
| 12 | On a scale of zero to ten, what is your pain now? | My pain right now is 7.0 out of ten. | clean | Match |
| 13 | Have you been diagnosed with any illnesses before? | I have no known previous medical conditions. | clean | Match |
| 14 | Have you needed surgery in the past? | I have not had any operations. | clean | Match |
| 15 | Are you taking any regular tablets? | I am not taking any medicines. | pause | Match |
| 16 | Are you allergic to any medicines or foods? | I have no known allergies. | clean | Match |
| 17 | Does anyone in your close family have health problems? | My father has high blood pressure. | clean | Match |
| 18 | Have you ever smoked, and how often do you drink alcohol? | I do not smoke. I rarely drink alcohol and live with my family. | clean | Match |
| 19 | What are your usual meals like? | I eat home-cooked meals three times a day, mostly rice, dal and vegetables. Yesterday I ate the same as usual. | clean | Match |
| 20 | How many hours do you normally sleep? | I usually sleep about seven hours, from around eleven at night until six in the morning. | clean | Match |
| 21 | Are you eating less or losing weight? | My appetite is normal and my weight has not changed. | clean | Match |
| 22 | How physically active are you in a typical week? | I walk to the market most days. I do not do any other regular exercise. | clean | Match |
| 23 | Can you tell me the blood pressure that was measured? | I was told my blood pressure is 140.0 over 88.0 mmHg. | clean | Match |
| 24 | Do you know the temperature measured today? | I was told my temperature is 37.0 degrees Celsius. | clean | Match |
| 25 | What is the largest planet in the solar system? | Sorry, doctor, I'm not sure. Please ask about my symptoms or medical history. | clean | Match |

## Nephrology: Kidney-condition follow-up

| # | Question | Actual answer | Audio | Topic check |
| --- | --- | --- | --- | --- |
| 26 | How should I address you? | My name is Alex. | clean | Match |
| 27 | Could you confirm your age for me? | I am 35 years old. | quiet | Match |
| 28 | Are you male or female? | I am male. | clean | Match |
| 29 | Could you give me your height and weight? | I am 175.0 cm tall and weigh 75.0 kg. | clean | Match |
| 30 | What kind of job do you have? | I work as a schoolteacher. | clean | Match |
| 31 | What has been troubling you recently? | I feel more tired, and my ankles have been swelling. | clean | Match |
| 32 | Over what period have these symptoms become worse? | Sorry, doctor, I'm not sure. Please ask about my symptoms or medical history. | clean | MISMATCH: unknown (expected duration) |
| 33 | When during the day is the ankle swelling most noticeable? | Both ankles swell towards evening. I was told my kidney function was reduced six months ago. | noise | Match |
| 34 | Have you noticed foamy urine or blood in it? | Sorry, doctor, I'm not sure. Please ask about my symptoms or medical history. | clean | MISMATCH: unknown (expected associated) |
| 35 | Which conditions have you previously been diagnosed with? | I was told about reduced kidney function six months ago and high blood pressure two years ago. I have not had dialysis. | clean | Match |
| 36 | Have you ever needed dialysis? | I will try to do that, doctor. Please tell me exactly how you would like me to move. | clean | MISMATCH: command (expected past_history) |
| 37 | Which tablets do you take every day? | I take a prescribed blood-pressure tablet daily, but I do not remember the name or strength. | pause | Match |
| 38 | What is its name and strength? | I take a prescribed blood-pressure tablet daily, but I do not remember the name or strength. | clean | Match |
| 39 | How much water do you drink, and have you been advised to cut down on salt? | I eat home-cooked meals three times a day. I was advised to reduce salt and I drink about two litres of water daily. I have no known allergies. | clean | MISMATCH: diet_meals, allergies (expected diet_meals) |
| 40 | How does a normal working day go for you? | I leave for school at eight in the morning, teach until four, and spend the evening at home with my family. | clean | Match |
| 41 | How are you coping emotionally with these health problems? | I feel a little worried about this problem, but otherwise my mood is normal. | clean | Match |
| 42 | Who can support you at home when you feel unwell? | I live with my family in a rented flat. They help me when I am unwell. | clean | Match |
| 43 | Have you taken any trips away from home lately? | I have not travelled anywhere recently. | clean | Match |
| 44 | Do you remember having any recent vaccinations? | I had my childhood vaccinations. I do not remember having any vaccine in the last few years. | clean | Match |
| 45 | What heart rate did they measure today? | I was told my heart rate is 84.0 beats per minute. | clean | Match |
| 46 | Do you know your measured pulse? | I was told my pulse is 84.0 per minute. | clean | Match |
| 47 | How many breaths per minute were recorded? | I was told I am breathing 18.0 times per minute. | clean | Match |
| 48 | What percentage was your oxygen level? | I was told my oxygen saturation is 98.0 percent. | clean | Match |
| 49 | What were your blood pressure and current pain score? | I was told my blood pressure is 146.0 over 92.0 mmHg. My pain right now is 0.0 out of ten. | clean | Match |
| 50 | What is the capital city of Japan? | Sorry, doctor, I'm not sure. Please ask about my symptoms or medical history. | clean | Match |

## Items requiring review

- **Question 6**: Selected topic differs from the prepared expectation; Answer does not contain the expected authored response. Transcript: 'Is it constant, or does it come and go?'. Expected case answer: It started suddenly about six hours ago and comes in waves.
- **Question 9**: Selected topic differs from the prepared expectation; Answer does not contain the expected authored response. Transcript: 'Have you felt sick or noticed any other symptoms?'. Expected case answer: I feel nauseated and noticed pink urine once. I have not had a fever or chills.
- **Question 10**: Selected topic differs from the prepared expectation; Answer does not contain the expected authored response. Transcript: 'Have you experienced fever or chills with the pain?'. Expected case answer: I feel nauseated and noticed pink urine once. I have not had a fever or chills.
- **Question 12**: Transcript differs; inspect intended and recognized question. Transcript: 'On a scale of 0 to 10, what is your pain now?'. Expected case answer: My pain right now is 7.0 out of ten.
- **Question 32**: Selected topic differs from the prepared expectation; Answer does not contain the expected authored response. Transcript: 'Over what period have these symptoms become worse?'. Expected case answer: The tiredness and swelling have increased over the past two weeks.
- **Question 34**: Selected topic differs from the prepared expectation; Answer does not contain the expected authored response. Transcript: 'Have you noticed foamy urine or blood in it?'. Expected case answer: My urine sometimes looks foamy. I have no pain when passing urine and no visible blood.
- **Question 36**: Selected topic differs from the prepared expectation; Answer does not contain the expected authored response. Transcript: 'Have you ever needed dialysis?'. Expected case answer: I was told about reduced kidney function six months ago and high blood pressure two years ago. I have not had dialysis.
- **Question 39**: Selected topic differs from the prepared expectation. Transcript: 'How much water do you drink, and have you been advised to cut down on salt?'. Expected case answer: I eat home-cooked meals three times a day. I was advised to reduce salt and I drink about two litres of water daily.

## Empty recognition and recovery

- `empty_asr`: Sorry doctor, I could not hear that properly. Could you say it again? UI: Nothing recognized; asked the learner to repeat; queued UI events: 0.
- `after_empty_asr`: My name is Alex. UI: Complete; queued UI events: 0.

Raw evidence: `.test_artifacts/local-audio-50-nephrology-20260921/result.json`; the same directory contains prepared questions, generated WAV inputs and service logs. Raw evidence stays in the ignored artifact directory.
