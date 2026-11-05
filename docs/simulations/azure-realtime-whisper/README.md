# Azure Realtime Whisper compatibility probe

Live verification on 2026-09-20 confirmed that the existing encrypted Azure
Whisper connection's key works with `gpt-realtime-whisper` on the supplied Azure
resource. Three synthetic English questions transcribed correctly in one persistent
transcription session. The active app profile and production adapters were not
modified.

## Endpoint and session configuration

The supplied path, with HTTPS changed to the required WebSocket scheme:

```text
wss://aiforce-openai.openai.azure.com/openai/v1/realtime?model=gpt-realtime-whisper
```

returned HTTP **400**, code **OperationNotSupported**. It selects the conversation
operation. The dedicated transcription flow succeeded:

```text
wss://aiforce-openai.openai.azure.com/openai/v1/realtime?intent=transcription
```

Authenticate with the resource key in the `api-key` header. Then send:

```json
{
  "type": "session.update",
  "session": {
    "type": "transcription",
    "audio": {
      "input": {
        "format": {"type": "audio/pcm", "rate": 24000},
        "turn_detection": null,
        "transcription": {
          "model": "gpt-realtime-whisper",
          "language": "en",
          "delay": "low"
        }
      }
    }
  }
}
```

Send base64-encoded mono PCM16 chunks with `input_audio_buffer.append`, then
`input_audio_buffer.commit` at the end of the question. Match transcript delta and
completion events to their `item_id`. This follows the
[Azure WebSocket transcription example](https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/realtime-audio-websockets#transcribe-audio-in-real-time).
The [Azure model overview](https://learn.microsoft.com/en-us/azure/foundry/openai/concepts/gpt-realtime-whisper)
describes a streaming transcription model; it is not the current file-upload API.

## Observed results

The probe reused the first three fictional audio inputs from the existing Alex
suite, converted 16 kHz PCM16 to 24 kHz, and sent 100 ms chunks at approximately
real-time speed. Matching ignores capitalization and punctuation.

| Input / returned transcript | First text from audio start | Final after commit | Match |
|---|---:|---:|---|
| What's your name? | 1.078 s | 0.875 s | Yes |
| How old are you? | 1.063 s | 0.765 s | Yes |
| What do you do for work? | 1.063 s | 0.922 s | Yes |

All three received text before the recording finished streaming. Session creation
and configuration took approximately 1.7 seconds, once for the three questions.
No automatic retries or 429 responses occurred in this short successful session.
The initial incompatible-URL probe sent no audio.

Redacted event evidence:
[result.json](results/20260920T144708_288478Z/result.json).

This establishes deployment access, authentication, session configuration and
basic English transcription. It does not establish medical/Hindi accuracy,
physical microphone quality, sustained capacity, end-to-end answer latency, or
that the previous provider throttling is resolved.

## Repeat the live check

From the repository root, with the existing demo database running:

```powershell
.\platform\api\.venv\Scripts\python.exe docs/simulations/azure-realtime-whisper/probe.py
```

To check both URL/session configurations without sending audio:

```powershell
.\platform\api\.venv\Scripts\python.exe docs/simulations/azure-realtime-whisper/probe.py --configure-only
```

Each run creates `results/<UTC timestamp>/result.json`. These are live cloud checks
and can consume provider capacity. Exit codes are 0 for a successful transcription
probe, 2 for a failed probe/transcript comparison, and 1 for setup errors.

The script uses the installed API Python environment and reads the one active
Whisper connection for this exact resource and demo organization, using the API
database role with read-only transactions. It decrypts the key in memory, sends it
only in the authenticated connection header, and never saves credentials or raw
session objects. It makes no database writes, model selections, LLM requests or
automatic replays. It requires the original three Alex WAV fixtures for an audio
run; `--configure-only` does not read them.

## Selectable app integration (2026-09-20)

The app now supports two separate Azure speech connections in **Models**:
**Azure Whisper audio** and **Azure GPT Realtime Whisper**. Restart the app and its
launcher to load the updated API and desktop code. Select the desired speech
connection and use the normal check/save flow. The original Whisper connection
and active profile are preserved.

Both use the existing `azure_openai_whisper` connection type and profile engine,
so no migration is required. Set connection `settings.model` to `whisper` (the
default) or `gpt-realtime-whisper`. The latter uses `settings.deployment` in its
transcription session; omit `api_version`. Endpoint remains the resource's
`https://.../openai/v1` base, not the WebSocket query URL. Validation opens and
configures a transcription session without sending audio.

The desktop still finishes each bounded 16 kHz recording before submitting it to
PMS. The Realtime adapter converts that recording to 24 kHz PCM, sends chunks over
one WebSocket session per utterance, and returns only its correlated final
transcript. This preserves the existing private recording, organization quota,
admission, idempotency, authorization and lifecycle checks. It does **not** yet
provide live partial microphone captions or persistent sessions across questions.
Credentials stay in PMS. Connections pin public DNS addresses, verify TLS, disable
proxies and redirects, and bound event sizes, counts and time. An interrupted
audio submission stays unknown and is never replayed automatically.

The idempotent demo registration helper adds and validates a separate choice
through the authenticated API without changing the active profile:

```powershell
.\platform\api\.venv\Scripts\python.exe docs/simulations/azure-realtime-whisper/register_choice.py
```

Add `--verify-audio` for four synthetic clips through the production adapters
(one original Whisper, three Realtime). These direct adapter checks are separate
provider verification, not PMS usage records. The script reads the existing
private demo credentials, stores the new provider credential through PMS's
encrypted/audited connection API, and writes `results/<UTC>/registration.json`.
It requires a running demo database and a current private operator token.

The [live adapter check](results/20260920T151606_113741Z/registration.json) passed
all four transcript comparisons with the same key. Original Whisper took 2.000 s;
Realtime took 3.515–4.625 s including one session per clip. This small check does
not establish that Realtime is faster or that sustained provider throttling is
resolved. Hindi/medical accuracy and a new 25-question live app run remain separate
verification work. The earlier persistent-session probe above measures a different
workflow and its timings are not directly comparable.
