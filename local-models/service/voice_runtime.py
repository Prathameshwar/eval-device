"""CPU-bounded Piper sessions that share the laptop with speech recognition and Qwen."""

import json
from pathlib import Path


def load_voice(model, config):
    import onnxruntime as ort
    from piper import PiperVoice
    from piper.config import PiperConfig

    options = ort.SessionOptions()
    # Piper's default starts a physical-core-sized pool for every cached voice.
    # Keep two voices resident without spinning those pools during LLM inference.
    options.intra_op_num_threads = 2
    options.inter_op_num_threads = 1
    options.add_session_config_entry("session.intra_op.allow_spinning", "0")
    options.add_session_config_entry("session.inter_op.allow_spinning", "0")
    return PiperVoice(
        config=PiperConfig.from_dict(json.loads(Path(config).read_text(encoding="utf-8"))),
        session=ort.InferenceSession(str(model), sess_options=options, providers=["CPUExecutionProvider"]),
    )
