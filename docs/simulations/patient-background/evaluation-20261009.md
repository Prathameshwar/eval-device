# Actual two-scenario evaluation — 9 October 2026

Actual typed questions were entered through the enrolled Human-test application's Tk handlers against the hosted VM. Qwen3.5-4B-Q4_K_M ran through the native CUDA runtime with 20 GPU layers, remaining layers on CPU, total context 2,048 and one generation per answer. The assigned sessions began and completed through the real device workflow; no inference answers or session status were mocked.

The baseline contains 44 questions (22 per case). The completed final run repeats those questions unchanged and adds eight probes. Those probes are additional coverage, not an independent blinded holdout. The first final chest run was interrupted when the user manually completed it during question 22; its private evidence is preserved and excluded from completion/accuracy totals. The unstarted wheeze assignment and a fresh chest assignment were then tested silently, with Speaker out disabled. Microphone and camera were off. No final speech recognition, audio playback or physical camera verification is claimed.

## Assessment

Manual review compares each actual response with the version-pinned fictional case. Complete means the requested parts are answered from recorded facts, or a sole unsupported fact is explicitly unknown. Partial means a requested part is missing or compound-question uncertainty is ambiguous. Wrong scope means evidence answers a different clinical question. Minor extra supported detail and repetition are recorded separately from factual correctness. Numerical sleep/work totals implied unambiguously by the baseline schedule are accepted; the refinement makes them explicit. These are limited test results, not a claim of general or clinical accuracy.

| Run | Complete | Partial | Wrong scope | Execution failures |
|---|---:|---:|---:|---:|
| Baseline, 44 | 36 | 6 | 2 | 0 |
| Final, 52 | 49 | 3 | 0 | 0 |

Both baseline scope failures are fixed: chest relief now answers “Rest usually helps”; family wheeze now states that similar-family symptoms are unknown and separately identifies the doctor who prescribed the inhaler. Household/occupation/trigger answers select relevant facts, and sleep/work quantities are explicit. Remaining clarity issues: three compound responses use an unnamed unknown statement; wheeze relief repeats two consistent authored sentences. Brand/dose, last-night meal and chest inhaler prescriber remain unknown rather than being invented.

## Measured speed and capacity

| Metric (minimum / median / maximum, ms) | Baseline 44 | Final 52 |
|---|---:|---:|
| Native first token | 578 / 1,430.0 / 4,094 | 719 / 1,789.5 / 5,516 |
| Native complete generation | 1,032 / 2,062.5 / 5,031 | 1,485 / 2,555.0 / 5,937 |
| Controller complete turn | 1,140 / 2,211.0 / 5,141 | 1,672 / 2,789.5 / 6,109 |

The final run was slower despite smaller selected prompts; this does not establish a speed improvement or a sub-five-second guarantee. Runs differed in ordering, cache state, text-history reporting and speaker setting, with other verification work on the same laptop. Controller timing excludes subsequent audible playback. Actual native completion tokens represent the compact selection protocol; the app renders the selected authored facts afterward.

Final maximum prompt: 1,393 tokens. Including 128 output and 128 safety tokens: 1,649 / 2,048. Largest actual native prompt-plus-completion: 1,397. All 52 turns used exactly one generation and respected the total context. Shorter explicit scopes omit unrelated earlier turns; ambiguous follow-ups retain bounded references. This does not mean unlimited history fits into a 2,048-token window.

## Actual questions and answers

Answers below are the captured delivered text. Each row includes native generation time; review labels use the same rubric before and after. The patient Alex is fictional. Private login, learner and enrollment information is omitted.

### Baseline: Chest discomfort interview

| # | Actual question | Actual answer | Review | Native ms |
|---:|---|---|---|---:|
| 1 | Hello, what is your name? | My name is Alex. | Complete | 1625 |
| 2 | How are you feeling today? | I get tightness in my chest when I walk uphill. It started two days ago. Each episode lasts about five minutes. I'm not sure about that. | Partial: Current complaint is present, but unrelated onset/duration and unexplained uncertainty weaken the response. | 2688 |
| 3 | When did your chest discomfort start? | It started two days ago. | Complete | 3062 |
| 4 | How long does each episode last? | Each episode lasts about five minutes. | Complete | 1688 |
| 5 | What degree of pain are you experiencing right now? | My pain score is 0.0 out of ten. | Complete | 1390 |
| 6 | What makes your chest discomfort worse? | I get tightness in my chest when I walk uphill. | Complete | 1718 |
| 7 | What makes it better? | The tightness is mild during episodes. I have no chest pain while resting now. | Wrong scope: Resting severity is not the recorded relieving factor: rest usually helps. | 1813 |
| 8 | Does it spread anywhere? | I'm not sure about that. | Complete | 1032 |
| 9 | Do you have a fever or a cough? | I get a little breathless during an episode. I have not fainted or had a fever. | Partial: Fever is denied; unrecorded cough status is left unanswered. Breathlessness/fainting are unrequested. | 1250 |
| 10 | What medicines are you taking? | I am not currently taking any medicines. | Complete | 1391 |
| 11 | Does your family have similar chest problems? | I do not know whether relatives have similar chest symptoms. | Complete | 2938 |
| 12 | Who do you live with? | I do not smoke. I rarely drink alcohol and live with my family. | Complete | 2188 |
| 13 | What do you do for work? | I am a Schoolteacher. I have a bachelor degree and a teaching qualification. I work at school Monday to Friday. I'm not sure about that. | Partial: Occupation is correct, but degree/schedule and unexplained uncertainty are unrequested. | 2750 |
| 14 | Tell me about your educational qualification. | I have a bachelor degree and a teaching qualification. | Complete | 1468 |
| 15 | How many hours a day do you teach? | I teach four hours per school day. | Complete | 2781 |
| 16 | What do you usually eat? | I usually eat home-cooked rice, lentils and vegetables. I prefer vegetarian food. | Complete | 2453 |
| 17 | What did you eat yesterday and what is your educational qualification? | I have a bachelor degree and a teaching qualification. I'm not sure about that. | Partial: Qualification is correct; the unknown statement does not identify yesterday's meal. | 2063 |
| 18 | How many hours do you sleep? | I usually sleep from 10 pm to 6 am. | Complete | 1453 |
| 19 | What is the capital of France? | The capital of France is Paris. | Complete | 1344 |
| 20 | What is two plus three? | Two plus three equals five. | Complete | 1046 |
| 21 | Can you explain what asthma is? | Asthma is a chronic condition where the airways become inflamed and narrow, causing breathing difficulties. | Complete | 2188 |
| 22 | What are your exact inhaler dose and brand? | I'm not sure about that. | Complete | 3235 |

### Baseline: Wheeze interview

| # | Actual question | Actual answer | Review | Native ms |
|---:|---|---|---|---:|
| 1 | Hello, what is your name? | My name is Alex. | Complete | 2969 |
| 2 | How are you feeling today? | I have wheezing and my breathing feels tight. It started two days ago. The wheeze comes and goes over these two days, especially at night. I'm not sure about that. | Partial: Current complaint is present, but unrelated timing and unexplained uncertainty weaken the response. | 2828 |
| 3 | When did your wheezing start? | It started two days ago. | Complete | 5031 |
| 4 | Is your wheezing constant or intermittent? | The wheeze comes and goes over these two days, especially at night. | Complete | 1297 |
| 5 | What makes your wheeze worse? | Dust seems to trigger it. My reliever inhaler helps for a while. | Complete | 2031 |
| 6 | What makes it better? | Dust seems to trigger it. My reliever inhaler helps for a while. | Complete | 4391 |
| 7 | Can you speak in full sentences? | I can speak in full sentences but feel breathless when walking. | Complete | 1219 |
| 8 | Do you get breathless when walking? | I can speak in full sentences but feel breathless when walking. | Complete | 4079 |
| 9 | Do you have a fever or cough up blood? | I have a dry cough. I have not had a fever or coughed up blood. | Complete | 1391 |
| 10 | How long have you had asthma? | I have had asthma since my teenage years. I have never needed a breathing machine. | Complete | 1984 |
| 11 | Who prescribed your inhaler and what makes your wheeze worse? | A doctor prescribed my reliever inhaler. Dust seems to trigger it. My reliever inhaler helps for a while. | Complete | 3265 |
| 12 | Does your family have similar wheezing? Who prescribed your inhaler? | My father has high blood pressure. A doctor prescribed my reliever inhaler. | Wrong scope: Father's hypertension does not answer similar-family wheezing; prescribed-by-doctor part is correct. | 4078 |
| 13 | What is your inhaler brand and dose? | I'm not sure about that. | Complete | 4391 |
| 14 | Who do you live with? | I do not smoke. I rarely drink alcohol and live with my family. | Complete | 2156 |
| 15 | Tell me about your educational qualification. | I have a bachelor degree and a teaching qualification. | Complete | 1828 |
| 16 | How many days a week do you work? | I work at school Monday to Friday. | Complete | 2203 |
| 17 | What did you eat yesterday and what is your educational qualification? | I have a bachelor degree and a teaching qualification. I'm not sure about that. | Partial: Qualification is correct; the unknown statement does not identify yesterday's meal. | 2062 |
| 18 | How many hours do you sleep? | I usually sleep from 10 pm to 6 am. | Complete | 1375 |
| 19 | What is the capital of France? | The capital of France is Paris. | Complete | 1375 |
| 20 | What is two plus three? | Two plus three equals five. | Complete | 1234 |
| 21 | Can you explain what asthma is? | Asthma is a chronic condition where the airways become inflamed and narrow, causing breathing difficulties. | Complete | 3203 |
| 22 | What degree of pain are you experiencing right now? | My pain score is 2.0 out of ten. | Complete | 3297 |

### Final: Wheeze interview

| # | Actual question | Actual answer | Review | Native ms |
|---:|---|---|---|---:|
| 1 | Hello, what is your name? | My name is Alex. | Complete | 3359 |
| 2 | How are you feeling today? | I have wheezing and my breathing feels tight. I can speak in full sentences but feel breathless when walking. | Complete | 1594 |
| 3 | When did your wheezing start? | It started two days ago. | Complete | 3937 |
| 4 | Is your wheezing constant or intermittent? | The wheeze comes and goes over these two days, especially at night. | Complete | 4250 |
| 5 | What makes your wheeze worse? | Dust seems to trigger it. | Complete | 2297 |
| 6 | What makes it better? | My reliever inhaler helps for a while. I use a blue reliever inhaler when wheezy; it helps briefly. | Complete: Supported relief is correct; two sentences repeat it. | 3468 |
| 7 | Can you speak in full sentences? | I can speak in full sentences but feel breathless when walking. | Complete | 3907 |
| 8 | Do you get breathless when walking? | I can speak in full sentences but feel breathless when walking. | Complete | 5109 |
| 9 | Do you have a fever or cough up blood? | I have not had a fever or coughed up blood. | Complete | 1938 |
| 10 | How long have you had asthma? | I have had asthma since my teenage years. | Complete | 2781 |
| 11 | Who prescribed your inhaler and what makes your wheeze worse? | A doctor prescribed my reliever inhaler. Dust seems to trigger it. | Complete | 2578 |
| 12 | Does your family have similar wheezing? Who prescribed your inhaler? | I do not know whether relatives have asthma or similar wheezing. A doctor prescribed my reliever inhaler. | Complete | 2219 |
| 13 | What is your inhaler brand and dose? | I'm not sure about that. | Complete | 3828 |
| 14 | Who do you live with? | I live with my family. | Complete | 2031 |
| 15 | Tell me about your educational qualification. | I have a bachelor degree and a teaching qualification. | Complete | 2078 |
| 16 | How many days a week do you work? | I work five days a week, Monday to Friday. | Complete | 3000 |
| 17 | What did you eat yesterday and what is your educational qualification? | I have a bachelor degree and a teaching qualification. I'm not sure about that. | Partial: Qualification is correct and meal is not invented, but the unknown statement should explicitly name yesterday's meal. | 2531 |
| 18 | How many hours do you sleep? | I usually sleep eight hours, from 10 pm to 6 am. | Complete | 2843 |
| 19 | What is the capital of France? | The capital of France is Paris. | Complete | 1578 |
| 20 | What is two plus three? | Two plus three equals five. | Complete | 1782 |
| 21 | Can you explain what asthma is? | Asthma is a chronic condition where the airways become inflamed and narrow, causing breathing difficulties. | Complete | 2969 |
| 22 | What degree of pain are you experiencing right now? | My pain score is 2.0 out of ten. | Complete | 5937 |
| 23 | Does your father have high blood pressure? | My father has high blood pressure. | Complete | 2422 |
| 24 | Do you smoke? | I do not smoke. | Complete | 1625 |
| 25 | What did you eat last night? | I'm not sure about that. | Complete | 4031 |
| 26 | What relieves your wheezing? | My reliever inhaler helps for a while. I use a blue reliever inhaler when wheezy; it helps briefly. | Complete: Supported relief is correct; two sentences repeat it. | 3969 |

### Final: Chest discomfort interview

| # | Actual question | Actual answer | Review | Native ms |
|---:|---|---|---|---:|
| 1 | Hello, what is your name? | My name is Alex. | Complete | 3328 |
| 2 | How are you feeling today? | I get tightness in my chest when I walk uphill. The tightness is mild during episodes. I have no chest pain while resting now. | Complete | 2937 |
| 3 | When did your chest discomfort start? | It started two days ago. | Complete | 4000 |
| 4 | How long does each episode last? | Each episode lasts about five minutes. | Complete | 3406 |
| 5 | What degree of pain are you experiencing right now? | My pain score is 0.0 out of ten. | Complete | 1922 |
| 6 | What makes your chest discomfort worse? | I get tightness in my chest when I walk uphill. | Complete | 2063 |
| 7 | What makes it better? | Rest usually helps. | Complete | 1765 |
| 8 | Does it spread anywhere? | I'm not sure about that. | Complete | 3063 |
| 9 | Do you have a fever or a cough? | I have not fainted or had a fever. I'm not sure about that. | Partial: No fever is supported. The uncertainty is appropriate for cough but does not name cough; fainting is unrequested. | 2438 |
| 10 | What medicines are you taking? | I am not currently taking any medicines. | Complete | 3297 |
| 11 | Does your family have similar chest problems? | I do not know whether relatives have similar chest symptoms. | Complete | 2532 |
| 12 | Who do you live with? | I live with my family. | Complete | 2281 |
| 13 | What do you do for work? | I am a Schoolteacher. | Complete | 1782 |
| 14 | Tell me about your educational qualification. | I have a bachelor degree and a teaching qualification. | Complete | 2000 |
| 15 | How many hours a day do you teach? | I teach four hours per school day. | Complete | 2484 |
| 16 | What do you usually eat? | I usually eat home-cooked rice, lentils and vegetables. I prefer vegetarian food. | Complete | 2969 |
| 17 | What did you eat yesterday and what is your educational qualification? | I have a bachelor degree and a teaching qualification. I'm not sure about that. | Partial: Qualification is correct and meal is not invented, but the unknown statement should explicitly name yesterday's meal. | 2453 |
| 18 | How many hours do you sleep? | I usually sleep eight hours, from 10 pm to 6 am. | Complete | 2484 |
| 19 | What is the capital of France? | The capital of France is Paris. | Complete | 1969 |
| 20 | What is two plus three? | Two plus three equals five. | Complete | 1485 |
| 21 | Can you explain what asthma is? | Asthma is a chronic condition where the airways become inflamed and narrow, causing breathing difficulties. | Complete | 2812 |
| 22 | What are your exact inhaler dose and brand? | I'm not sure about that. | Complete | 4125 |
| 23 | What helps your chest tightness? | Rest usually helps. | Complete | 3297 |
| 24 | Do you smoke? | I do not smoke. | Complete | 1750 |
| 25 | What did you eat last night? | I'm not sure about that. | Complete | 1625 |
| 26 | Who prescribed your inhaler? | I'm not sure about that. | Complete | 3875 |

## Server persistence

Both final assigned sessions completed normally. With audio/camera disabled, each archive contained exactly 26 conversation items: 26 received / 26 expected, transfer synced and capture complete while the app remained open. Baseline speaker-enabled archives contained 47 / 47 items each, including generated audio. These counts describe different capture modes; saved items are not message counts.

The final verification discovered a separate history-upload rejection when the paired device belonged to a department but the laptop omitted the department field. The API fix resolves only omitted device scope from its authenticated registration, then checks the frozen conversation and ownership; explicit mismatches remain rejected. After the final VM API deployment, the normal uploader acknowledged all 74 pending events with zero remaining. Each completed final session exposes 52 messages, exactly matching its 26 actual question/answer pairs. The authenticated browser verified both full conversation and archived conversation/recording links with zero page errors. Unified session details also reads the authorized archive when the separate text-history record is empty.

Only the English conversation pack was exercised. Hindi documents validate, but Hindi inference, the user's other machine, microphone/camera capture and a blinded unseen-question accuracy benchmark remain unverified. Hosted desktop ZIPs were not updated during this API/UI/database review.
