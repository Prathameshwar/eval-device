# Voice activity detection engine comparison

Completed 2026-09-20. `device/audio-process` can now segment with either of two voice detectors, and the default changed from `webrtc` to `silero`. Transcription models, model selection, GPU configuration, transport, recording and private settings are unchanged. The detector only decides where an utterance starts and stops; it never alters a sample.

## What changed

`device_audio.vad` holds both engines behind the existing `VoiceDetector` protocol, so `Segmenter` and `StreamingSegmenter` build one without knowing which:

```dotenv
AUDIO_VAD_ENGINE=silero        # or webrtc
AUDIO_VAD_THRESHOLD=0.5        # silero speech probability, 0.05-0.95
AUDIO_VAD_AGGRESSIVENESS=2     # webrtc only, unchanged
# AUDIO_VAD_MODEL_PATH=.models/silero_vad_v6.onnx
```

Silero needs no download: the v6 ONNX weights (1.2 MB) already ship inside the installed `faster-whisper`, and `onnxruntime` was already a direct dependency. `AUDIO_VAD_MODEL_PATH` overrides the location and is rejected at configuration validation if the file is absent or if the engine is not `silero`. There is no silent fallback between engines — an operator who asks for one gets it or gets a startup failure.

Framing did not change. `FRAME_MS` remains 30, so `pre_roll_ms`, `silence_ms`, `min_speech_ms` and every existing test keep their meaning. Silero only accepts 512-sample (32 ms) windows, so `SileroDetector` buffers the 480-sample frames it is given and scores complete windows as they form, holding the previous decision for the calls that complete none. The cost of that is at most 32 samples — 2 ms — of decision lag.

The adapter keeps the model's LSTM state and its 64-sample lookback between calls. This is the part that needed writing rather than reusing: faster-whisper's own `SileroVADModel` zeroes `h`/`c` on every call because it scores finished files, so driving it per frame would re-decide from nothing 33 times a second. The ONNX graph exposes `h`/`c` as inputs and `hn`/`cn` as outputs, so the streaming state is carried explicitly instead. One `InferenceSession` is shared across concurrent capture sessions with one intra-op thread; the per-stream state lives in the detector, so `max_sessions` captures cost one copy of the weights, not one each.

## Why the default changed

Measured through the real `Segmenter`, not by comparing detector outputs. The 25 generated question WAVs from the alex-cardiology simulation were concatenated with one second of room between them and white noise was added across the whole stream — pauses included — at each SNR. Both engines saw identical audio. A correct result is 25 chunks with none ending on the `max_chunk_seconds` limit, because a chunk that ends on the hard limit was cut mid-sentence rather than at the speaker's pause.

| Room noise | Engine | Chunks | Cut at the 8 s limit | Longest chunk | Audio sent to Whisper |
| --- | --- | --- | --- | --- | --- |
| none | webrtc | 25 | 0 | 4.59 s | 70.9 s |
| none | silero | 25 | 0 | 4.38 s | 67.0 s |
| SNR 20 dB | webrtc | 25 | 0 | 4.44 s | 67.5 s |
| SNR 20 dB | silero | 25 | 0 | 4.38 s | 66.7 s |
| SNR 15 dB | webrtc | **27** | 0 | 4.68 s | 77.5 s |
| SNR 15 dB | silero | 25 | 0 | 4.38 s | 67.5 s |
| SNR 10 dB | webrtc | **13** | **12** | **8.01 s** | **100.5 s** |
| SNR 10 dB | silero | 25 | 0 | 4.35 s | 67.9 s |
| SNR 5 dB | webrtc | **13** | **12** | **8.01 s** | **100.5 s** |
| SNR 5 dB | silero | 25 | 0 | 4.26 s | 67.3 s |

In a quiet room the two engines are equivalent, and the existing latency and accuracy measurements were not taken in a condition where the choice mattered. From about 15 dB SNR the energy detector starts splitting questions, and by 10 dB it has stopped finding pauses at all: it calls every frame speech, `quiet_ms` never reaches `silence_ms`, and 25 questions collapse into 13 chunks of which 12 are chopped at exactly 8.00 seconds. It also forwards the entire 100.5-second stream to the transcriber instead of 67 seconds of it — 48% more inference on a pipeline whose interactive latency gate is already unmet per [the audio review](audio-latency-review.md). Silero is unaffected across the whole range.

That 15 dB onset is the same point at which the desktop client's per-turn report starts warning about signal-to-noise ratio, which was set independently.

## What it costs

Detector plus segmenter: 0.0045 ms per 30 ms frame for webrtc against 0.1242 ms for silero. In isolation the detector is 0.129 ms per frame, or 0.43% of one core for a continuous stream, against 0.01% — negligible beside transcription measured in seconds, and it does not touch the GPU. The shared session loads in well under a second and a second concurrent session adds no load time.

Speech onset is detected a median 60 ms later than the energy detector across the first eight questions. `pre_roll_ms` defaults to 300, so the audio before the detected onset is still prepended to the chunk and no word start is lost; a deployment that lowers `pre_roll_ms` below about 100 ms should re-check that.

## Verification

179 tests pass in `device/audio-process`, including 12 new ones in `tests/test_vad.py`; Ruff, Ruff format and mypy pass (21 source files). The new tests run the real ONNX weights rather than a stand-in, and cover framing invariance, state carried across calls, per-stream state isolation with shared weights, hysteresis through an injected scripted session, refusal of non-16 kHz and unaligned audio, and both segmenters building their own detector. Speech is synthesised in-test — a pitch-contoured pulse train through gliding formants with syllable closures — so the suite carries no audio fixture. A steady vowel is not sufficient: Silero scores an unmodulated buzz at barely 0.5 once it has any preceding context.

Evidence: `.test_artifacts/vad-engine/{measure.py,results.json}`.

## Limits

The speech in this measurement is Piper text-to-speech and the noise is synthetic and stationary. Nothing here was recorded through a microphone, so it does not establish behaviour on real voices, real rooms, reverberation, keyboard and chair noise, or overlapping speakers, and it is not a word-error-rate result — [the three-audio tests](whisper-three-audio-tests.md) show that clean input does not by itself fix recognition errors. `AUDIO_VAD_ENGINE=webrtc` restores the previous behaviour exactly if a real-room comparison contradicts this. Raspberry Pi capture, Wi-Fi and the target 16 GB machine remain untested; `device/training` still uses its own energy threshold and was not changed.
