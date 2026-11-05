"""Select an explicit ALSA/PortAudio output by name, refusing ambiguity."""


def output_device(name, devices=None):
    if name is None:
        return None
    if devices is None:
        import sounddevice

        devices = sounddevice.query_devices()
    matches = [
        index for index, row in enumerate(devices) if row["name"] == name and row["max_output_channels"] >= 1
    ]
    if len(matches) != 1:
        raise ValueError("Configured speaker is missing or ambiguous")
    return matches[0]
