# Operating Pi-test

| Path | Contents |
| --- | --- |
| `/opt/pi-test/releases/VERSION` | Immutable release venv and wheels |
| `/opt/pi-test/current` | Active release symlink |
| `/etc/pi-test/config.toml` | Nonsecret configuration; root owned, service readable |
| `/var/lib/pi-test/connection.json` | Private enrolled device identity/credential |
| `/var/lib/pi-test/.local` | Shared private history, archives and camera spool |
| `/var/lib/pi-test/inference-requests` | Request IDs and outcomes, no prompts |
| `/var/lib/pi-test/synthesis` | Cloud processing request/run IDs, no text |
| `/var/lib/pi-test/processing` | Video request/run IDs and outcomes, no frames |
| `/run/pi-test/control.sock` | Private local command socket |

Boot and process restart leave capture off. The service verifies platform access
and retries readiness. Loss of access pauses work; recovery permits an explicit
operator command, never automatic microphone restart. Assigned sessions additionally
enforce their existing platform lease/contact deadline. Service liveness is reported
to systemd independently of internet readiness.

`systemctl status pi-test` and `journalctl -u pi-test` report process failures.
`pi-test status` reports active state, job/error class, counters and the latest
inference request. `pi-test doctor` is read-only and does not open any audio/camera
device. Missing hardware remains distinct from software readiness.

Commission with `config-check`, `audio-devices`, then `probe`. The probe enumerates
devices and checks formats without recording or playback; it is not a physical
acceptance test. Configure exact microphone/speaker names; for USB cameras prefer
`camera_device=/dev/v4l/by-id/...` over an index. CSI uses `rpicam-vid --nopreview`.
Use `microphone_native_rate` only to select a supported 16/44.1/48 kHz mono PCM format.

Readiness reports platform contact, binding agreement and language-model availability.
A changed active model configuration pauses work; finish, reload, and begin again.
`pause`, `finish`, camera-stop and remote session completion cancel associated video
processing. Cancellation closes the device run where possible; an already submitted
cloud job or admitted remote grant can still finish externally. Inspect run status
after uncertain responses. Neither recovery nor status inspection replays work.

Results are available for five minutes through `result`, then removed from the
service's result slot. They are also cleared when new work starts or the session ends.
Shared conversation history retains its separately configured private persistence.
Concurrent audio/video jobs share the last-result slot; use processing-status for a
specific video run. Large results remain accessible through the platform.

Use `pause` before unplugging audio devices or changing configuration. Use `finish`
to end the session. SIGTERM stops media and closes the shared runtime; systemd owns
the whole process group, including a camera driver that needs forced termination.
Once shutdown is requested, queued and new work are rejected. The control server
cancels pending commands before the runtime and its storage are closed.
Private archives recover interrupted segments and resume only their idempotent
upload protocol. Cloud submissions and model questions never resume automatically.

Disk reserve and per-spool quotas stop new capture before storage is exhausted.
Do not remove queued media to make space without checking its platform transfer
status. Back up device identity separately from releases, with account-restricted
permissions. Never copy identity to a second simultaneously running device.

Cloud synthesis journals retain unknown request keys when a submit response is
lost. They deliberately do not resubmit. An administrator can inspect processing
runs using the existing platform workflow. Cancelling local playback does not
claim that an already submitted provider request was cancelled.

TLS failures: check the hostname, CA file, certificate expiry and clock. Grant
failures: check enrollment/lifecycle, assigned models, host UUID/origin and the
pinned signing key. Use time synchronization on both machines. Keep public TLS
certificates separate from the platform signing key. The Pi never needs the latter.

For Windows development only, a killed process can leave `control.json`. Confirm
the development service is stopped before removing that descriptor; production
Unix sockets recover stale endpoints automatically. Never remove a live socket.

Update using a new release version and reviewed wheelhouse. Installation validates
imports before stopping the existing service, then changes the release symlink.
A failed service stop aborts the update before switching the active executable.
A failed service start restores the previous executable. Rollback preserves
forward-compatible journals; it never deletes media or downgrades the platform DB.
