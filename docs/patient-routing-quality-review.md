# Patient routing quality and turn cost — 2026-09-20

Why in-scope questions were answered with the out-of-case clarification line, what was
changed, and what the change is actually worth. Every number here comes from a run against
the configured models: `nemotron-3-super-120b` over the operator's OpenAI-compatible
endpoint, and the laptop's `qwen3-4b` on llama.cpp.

## The reported symptom

"What's your name" sometimes answered *"Sorry, doctor, I'm not sure. Please ask about my
symptoms or medical history."* The case answers that question, and the same question
succeeded five times in the same session.

Two causes, measured separately.

**The router is not deterministic.** Ten identical routing calls at `temperature: 0`, no
history, returned `name` nine times and `unknown` once, with deliberation ranging from 91
to 420 tokens on identical input. The provider does not guarantee determinism, so a
single run can never establish a small difference; every comparison below is repeated.

**Refused turns poison the conversation.** The routing call receives the patient
conversation, including the patient's previous replies. When a turn is refused, the text
*"Sorry, doctor, I'm not sure…"* is appended as an assistant turn, and the router then
imitates it. Same question, ten calls each:

| history before "What's your name" | routed to `name` |
| --- | --- |
| none | 9/10 |
| two previously refused questions | 1/10 |

The refusals used were identity questions ("what is your agent?", "what model are you
running on"), so this measures generalisation from a refused identity question onto the
patient's own name. Whether an unrelated refusal poisons as strongly is not measured.

## Simulation

Three 50-turn interviews against the shipped case, scored per turn against the topic a
clinician-facing router should return. Labels were written before any arm ran; sessions 1
(clean English) and 2 (clipped, ungrammatical, romanised Hindi) are the development set
and session 3 (refusals first, prompt-injection attempts, abuse, then ordinary questions)
was held out. Guard turns — backchannel, command, boundary, genuinely out-of-case — are
scored separately from in-scope recall so recall can never be bought with guard failures.

## What changed

**Routing rules** (`training_contracts.patient_turn.ROUTING_RULES`). Four additions: the
message is a speech transcript, judge intent not grammar; an explicit decision order with
boundary first; prefer the closest topic and reserve `unknown` for what no topic can
answer; and classify this message alone, because an earlier unanswered message says
nothing about this one. Recall is cheap to raise here because the router is not the
fabrication guard — `spoken_answer` is. A misroute answers a neighbouring authored fact;
it cannot invent one.

**Per-call budgets** (`turn_budget`, four settings). Routing and speaking are budgeted
separately, and both are configuration because a 2048-token laptop model and a hosted
model need different values. Routing emits about fifteen tokens of JSON; the rest of a
reasoning model's allowance is deliberation nobody reads, so reserving the connection's
whole budget for it was waste. Quota reservation for a two-call turn drops from 8192 to
4608, and an authored-mode turn from 4096 to 512.

**One history policy** (`bounded_history`), applied by the platform for hosted turns and
by the laptop for local ones, so a caller cannot widen the window by sending more turns.

**Thinking control** (`model_options.disable_thinking`), off by default — see below.

## Results

Local `qwen3-4b`, deterministic (`temperature: 0`, `seed: 42`), 150 turns per row:

| history | in-scope before | after | guards before | after | bad JSON | max prompt tokens |
| --- | --- | --- | --- | --- | --- | --- |
| 0 | 84/111 | **97/111** | 32/39 | **33/39** | 11 → 8 | 943 |
| 2 (shipped) | 93/111 | **96/111** | 31/39 | **34/39** | 1 → 2 | 980 |
| 4 | 90/111 | **96/111** | 31/39 | **35/39** | 5 → 4 | 1019 |
| 6 | 94/111 | **96/111** | 32/39 | **35/39** | 2 → 3 | 1055 |

Six more questions answered at every depth, better guards, and stable across depths where
the old prompt swung between 84 and 94. Routing latency is unchanged at about 420 ms. The
2048-token window is verified with llama.cpp's own tokenizer, not estimated: worst case
1055 prompt + 75 routing allowance + 64 margin = 1194 of 2048. No truncation, no overflow.

Cloud `nemotron-3-super-120b`, three repeats of all 150 turns:

| | in-scope mean | runs | held-out | guards | p50 |
| --- | --- | --- | --- | --- | --- |
| before | 92.5% (sd 1.4) | 91.0 / 93.7 / 92.8 | 95.8% | 38, 39, 39 of 39 | 1782 ms |
| after | **93.7%** (sd 1.6) | 91.9 / 94.6 / 94.6 | **96.9%** | **39, 39, 39** | 1859 ms |

Honest reading: on the cloud model the gain is 1.2 points against a standard deviation of
about 1.5, so three repeats do not establish it on their own. It is positive on every
measure including the held-out session, it never regressed, and the same prompt produces a
large, repeatable gain on the deterministic local model. The prompt is about 70 ms slower
because it is longer. No boundary message was ever routed to a topic, in any arm.

## History depth

Swept 0, 2, 4, 6 and 12 messages on both models, with and without refused turns removed.
No depth showed a reliable accuracy advantage on either model; the local model's best was
2. Depth was therefore chosen for cost and for the local context window, not for accuracy:
2 messages locally (keeps the routing prompt near 1000 tokens), 12 remotely.

Removing refused turns from the history — the obvious fix for the poisoning above — was
measured and **did not help**: 90.1% against 92.8% for the unchanged policy on a 150-turn
run, and no better across the sweep. It is not implemented. The prompt instruction to
judge each message alone addresses the same failure and does measure better.

## Thinking suppression: measured, kept off

`chat_template_kwargs: {"enable_thinking": false}` works on this endpoint and is a large
speed win in isolation — 78 output tokens to 13, roughly 1200 ms to 400 ms on a single
question. Across the full 150-turn simulation it collapsed in-scope accuracy to **4.5%**
with 105 false refusals: without deliberation this model cannot classify against 32
topics. It is implemented as a per-connection option because other OpenAI-compatible
models will behave differently, and it defaults to off. Do not enable it for a model that
has not been measured with it on. `reasoning_effort: "none"` returned an empty completion
on this endpoint and should not be used at all. Prompt-level directives
("detailed thinking off", "/no_think") did not suppress deliberation here.

## The second provider call earns its latency

Thirty-nine in-scope turns, generated mode: 13 answered in one call (objective facts
short-circuit), 24 spent a second call. Of those 24 the spoken call changed the wording 19
times, the fact guard rejected nothing, and median similarity to the authored line was
0.82. The rephrasing is better patient speech, not noise — "Walking uphill makes it worse.
Resting usually helps." against the authored "The tightness is in the centre of my chest.
Rest usually helps." Switching the connection to `patient_answer_mode: "authored"` would
remove a median 1422 ms per turn and that quality with it. Not recommended while quality
leads.

## Where the remaining latency is

A generated cloud turn is about 1.86 s of routing plus about 1.42 s of speaking, before
speech recognition and playback. The routing call is a classification task being run on a
120B reasoning model; the laptop's 4B model performs the same routing **more accurately
and about four times faster** (420 ms, 96/111 against 93.7%). The largest remaining win is
therefore to route on a small fast model and speak on the large one. That needs a second
connection binding for the routing call and is not implemented here.

## Limitations

- One case (`alex_chest_discomfort`, 32 topics), one language pair, one cloud endpoint.
- Expected labels are a considered judgement, not a clinical ground truth.
- Session 3 was held out for tuning decisions, but its per-question failures were
  inspected once while diagnosing, so it is no longer pristine for future work.
- The simulation drives the shared routing contract directly. It does not exercise Whisper,
  text-to-speech, the HTTP and authorisation layers, or quota accounting, and it uses
  non-streamed calls so absolute latencies are indicative while differences are comparable.
- Session assistant turns use the authored answer as a stand-in for generated wording,
  which keeps history realistic without paying for a second call on every simulated turn.
