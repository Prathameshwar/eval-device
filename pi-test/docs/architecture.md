# Headless Pi training client

The Pi owns capture, speaker playback and bounded durable uploads. The shared
training-client owns conversation behavior, platform API calls, session leases,
history, playback gates, cancellation and archive completion. No model weights,
model engine, Tk, display server or database server is installed on the Pi.

Target: Raspberry Pi OS Lite Trixie ARM64, OS Python 3.13; Python 3.12/3.13 on
development machines. CSI capture uses the OS rpicam-vid executable without a
preview; USB capture uses the shared recorder. Native dependencies and physical
devices require real ARM verification before hardware support is certified.

One device identity has one daemon and one asyncio loop. Local operators use a
permission-restricted Unix socket (authenticated loopback fallback for Windows
development). Commands use bounded JSON and serialized
mutations. Text/media never enter operational logs. A second process cannot take
the same state directory. Boot reaches readiness with all capture stopped.

The service states are starting, unavailable, idle, paused, listening and stopping;
readiness and active-session ownership are reported separately.
The shared session supervisor remains authoritative for assigned-session claims,
deadlines, remote stop and finish retries; host states do not duplicate that engine.
Session begin is explicit. Process restart recovers uploads, never microphone
capture, playback or an uncertain external submission.

Platform device credentials travel only to the platform. GPU access uses an
explicit platform-managed device/host binding and short-lived signed grants.
The gateway checks host audience, device/organization, capability, model, expiry
and request identity; management remains loopback-only. Native GPU workers never
receive device credentials. Model inference is never automatically replayed.
Cloud routes use the existing platform provider/processing and quota boundaries.

Durable media is private and bounded. Interactive audio and video use separate
connections; an upload acknowledgement is distinct from completed persistence.
WSS audio sends frames during capture and finalizes ASR only after a clean end
marker; partial live recognition is not implemented. Video processing reserves a
platform run before remote motion analysis, or uploads a bounded video-only MP4 to
the platform's cloud processing path. A local video run authorizes one remote
execution. Motion/label observations never become clinical facts automatically.
Video processing and listening use independent tasks; session cancellation owns both.

Deployment separates /opt/pi-test releases, /etc/pi-test configuration/trust,
/var/lib/pi-test private state and /run/pi-test command sockets. systemd owns the
daemon and its camera children; Python does not daemonize or spawn upload helpers.
Readiness failures are retried at a configured interval; liveness/watchdog reports loop
health, not internet availability. SIGTERM closes capture/playback before archives.

Acceptance includes two fictional scenarios, shared desktop regression checks,
authorization/replay/size/time limits, interrupted capture, expired sessions,
storage failure, restart recovery, installation inspection and two review passes.
Mock, local native, Linux execution, ARM dependency and physical hardware evidence
must be reported separately.
