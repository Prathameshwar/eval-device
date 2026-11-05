# Compatibility and qualification

Target: Raspberry Pi OS Lite Trixie ARM64, Python 3.13, Raspberry Pi 4/5 class hardware.
Python 3.12 is supported for development. A 32-bit OS and on-Pi model inference are
outside this implementation. CSI uses the OS `rpicam-vid` command instead of Python
libcamera bindings, avoiding a venv/interpreter ABI dependency.

Reference documentation: [Raspberry Pi OS](https://www.raspberrypi.com/documentation/computers/os.html),
[camera software](https://www.raspberrypi.com/documentation/computers/camera_software.html),
[systemd service lifecycle](https://www.freedesktop.org/software/systemd/man/latest/systemd.service.html).

Qualification evidence is recorded in [review](review.md). Keep these claims separate:
The later release is covered in [completion review](completion-review.md).

| Check | What it proves |
| --- | --- |
| Windows unit/integration tests | Contracts, lifecycle, auth, bounded transport and simulated failures |
| Real disposable PostgreSQL | Tenant/device permissions and API persistence |
| ARM64 wheel resolution/download | Availability of the pinned native distribution artifacts |
| Linux shell/unit inspection | Deployment command and service configuration consistency |
| Physical Pi acceptance | Still required: ALSA, CSI/USB, reboot, WiFi loss, thermal/storage endurance |

No physical Pi was available for implementation. Do not present simulated camera
frames, mocked model calls or a successful wheel build as hardware verification.
Paid cloud calls and hosted deployment were not requested and are not part of the
verification. The existing supported cloud providers/models still determine which
ASR, LLM and output routes are usable.

Hardware acceptance when a Pi is available: install the wheelhouse, enroll, verify
exact input/output names, run two published scenarios with microphone/playback,
record CSI and USB video, unplug/reconnect each device, interrupt WiFi and the GPU
host, fill a disposable spool to its reserve, reboot during upload, rotate/revoke
the device credential, and run a sustained temperature/memory/disk test. Verify
that no capture resumes on boot and completed archives remain private and bounded.

On a native Linux ARM64 runner, install the locked development environment and run:

```sh
cd pi-test
uv sync --locked --group dev
uv run python deployment/qualify.py --output ../.test_artifacts/pi-native.json
```

The script checks architecture, native imports, codecs, private Unix control and
the shared/Pi regression suites. It refuses to certify Windows or x86 as native ARM.
After installing on a Pi, `--installed` additionally verifies the actual systemd unit
and requires an idle running service. Run that check as root or the service account,
with access to the checked-out source/dev environment. Its report explicitly keeps
hardware and cloud verification false. No Linux/ARM runner was available here.

Audio normalization follows the [PyAV resampler contract](https://pyav.org/docs/stable/api/audio.html).
CSI capture follows the [official rpicam tools](https://www.raspberrypi.com/documentation/computers/camera_software.html).
