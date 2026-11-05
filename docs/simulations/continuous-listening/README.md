# Continuous microphone recovery regression

From the repository root, with the human-test environment installed:

```powershell
.\human-test\.venv\Scripts\python.exe docs/simulations/continuous-listening/run.py
```

This opens a transparent native Tk test window, injects synthetic PCM audio and
mocked PMS responses, and saves `results/<UTC timestamp>/result.json`. It uses no
microphone, camera, cloud service, credentials or physical speaker. Exit 0 means
all assertions passed; a failed assertion exits nonzero and retains the result.

One press of **Start microphone** exercises an unknown transcription outcome, an
unknown response outcome, a microphone disconnection, and then a successful
question. Each failed turn must return to fresh capture after three seconds,
retain the recovery reference, show a bordered warning and keep **Pause
microphone** available. No failed audio/question is replayed; only the completed
turn enters history and speaks. Manual pause must prevent another capture.

Offline business-rule tests are in `human-test/tests/test_continuous_listening.py`;
launcher outage tests are in `human-test/scripts/tests/test_startup_cloud_recovery.py`.
The existing `human-test/tests/busy_window_smoke.py` separately exercises busy retry
rounds, exhaustion, countdown and cancellation.
