# Local model inference gateway

This is a separate TLS service for remote devices. The existing manager and its
operator API remain on `127.0.0.1:8790`. Only fixed capabilities, inference,
inspection, stream and receipt operations are exposed on the gateway.

Install with `uv sync --group dev` from this directory. Copy
`deployment/gateway.example.toml`, set the host UUID, platform Ed25519 public key,
manager state directory and private gateway state directory. Provision and start
the selected models through the existing local-models workflow before first use.

```text
uv run local-model-gateway --config gateway.toml --cert tls.crt --key tls.key
```

Use a certificate valid for the DNS name configured on the Pi. Install a private CA
on the Pi with `inference_ca_file` where needed; verification cannot be disabled.
The platform verification-key endpoint helps retrieve the public key, but verify
its fingerprint through the deployment channel before pinning it. Replacing the
key requires a coordinated gateway restart. No provider credentials are copied.

The platform issues grants with a 30-second admission lifetime, host audience,
device/tenant identity, method, path, payload hash, model/voice and conversation.
The execution deadline is at most 180 seconds and is shortened by session expiry.
Revocation blocks new grants; already issued grants have that bounded lifetime.
The gateway commits a private metadata receipt before submitting work. An uncertain
call remains `unknown` across restart, and duplicate request IDs cannot execute
again. Status lookup requires a fresh grant and is scoped to the original device
and tenant. Receipt retention is 24 hours, capped at 100,000 records.

HTTP request bodies are capped at 1.5 MB and responses at 6 MB. Concurrency defaults
to two operations, with an atomic per-device limit of 120 accepted requests per
minute by default. Model token and audio-duration limits are signed by the platform
and enforced before forwarding. WSS audio/video have separate connections, monotonic timestamps,
strict sequence numbers, one acknowledged frame in flight and explicit completion.
An incomplete audio stream never invokes ASR. Video grants can authorize the existing
`video.motion` operation with `opencv_motion`. The platform reserves processing usage
and permits one grant per run, even under concurrent requests. JPEG dimensions are
checked before decoding; results contain bounded motion counts, never image data.
Unassigned video streams remain transport diagnostics. Cloud video processing uses
the platform's existing worker/provider path and does not pass through this gateway.

On Linux, adapt the two systemd units under `deployment/` to the installed paths
and dedicated account. On Windows, `deployment/register-windows.ps1` registers
startup tasks under a supplied account that owns the already provisioned models.
It does not start them or open a firewall. Stop an existing desktop-launched manager
before starting its supervised replacement. `service.daemon --start-selected llm
asr tts` starts only already provisioned services; it does not download or select
models. A failed startup exits so the OS supervisor can restart it.

The gateway is single-process by design: run one worker per host ID/state directory.
Put its TLS port behind a network policy allowing the intended devices. Do not
expose the manager or native worker ports to the LAN.
