import importlib.util
import platform
import shutil
from pathlib import Path


def inspect(settings):
    """Read-only and redacted; never open capture devices during a health check."""
    root = settings.app_root
    parent = root if root.exists() else root.parent
    return {
        "system": platform.system(),
        "machine": platform.machine(),
        "python": platform.python_version(),
        "enrolled": bool(settings.device_id and settings.pms_token.get_secret_value()),
        "free_mb": shutil.disk_usage(parent).free // (1024 * 1024) if parent.exists() else None,
        "camera_backend": settings.camera_backend,
        "rpicam_available": bool(shutil.which("rpicam-vid")),
        "audio_module": importlib.util.find_spec("sounddevice") is not None,
        "video_module": importlib.util.find_spec("av") is not None,
        "physical_devices_verified": False,
        "inference_transport": "https" if settings.inference_url else "cloud_only",
        "live_audio_transport": bool(settings.stream_audio),
        "partial_transcripts": False,
        "capture_on_boot": False,
        "listen_on_explicit_begin": settings.listen_on_begin,
    }


def audio_devices():
    import sounddevice

    return [
        {"name": row["name"], "inputs": row["max_input_channels"], "outputs": row["max_output_channels"]}
        for row in sounddevice.query_devices()
    ]


def hardware(settings):
    """Enumerate/check device formats without opening capture or playing a tone."""
    result = {
        "microphone": "unknown",
        "speaker": "disabled" if not settings.speaker_output else "unknown",
        "camera": "disabled" if settings.camera_backend == "none" else "unknown",
    }
    try:
        import sounddevice as sd
        from training_client.devices import input_device, input_rate

        from .hardware.audio import output_device

        devices = sd.query_devices()
        try:
            index, _, _ = input_device(settings, devices, sd.default.device[0])
            result["microphone_native_rate"] = input_rate(settings, index, sd)
            result["microphone"] = "available"
        except Exception:
            result["microphone"] = "unavailable"
        if settings.speaker_output:
            try:
                index = output_device(settings.speaker_device_name, devices)
                index = sd.default.device[1] if index is None else index
                if index < 0 or devices[index]["max_output_channels"] < 1:
                    raise ValueError()
                result["speaker"] = "available"
            except Exception:
                result["speaker"] = "unavailable"
    except Exception:
        result["microphone"] = "unavailable"
        if settings.speaker_output:
            result["speaker"] = "unavailable"
    if settings.camera_backend == "csi":
        result["camera"] = "driver_available" if shutil.which("rpicam-vid") else "driver_missing"
    elif settings.camera_backend == "usb":
        if settings.camera_device:
            result["camera"] = "device_present" if Path(settings.camera_device).exists() else "unavailable"
        elif platform.system() == "Linux":
            result["camera"] = (
                "device_present" if Path(f"/dev/video{settings.camera_index}").exists() else "unavailable"
            )
    return {**result, "capture_tested": False}
