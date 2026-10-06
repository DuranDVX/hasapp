"""Speech to text with a local faster-whisper model (dev only)."""
import subprocess
import threading
import time

import numpy as np

from . import config

_model = None
_lock = threading.Lock()


def _get():
    global _model
    with _lock:
        if _model is None:
            from faster_whisper import WhisperModel  # slow import
            _model = WhisperModel(config.WHISPER_MODEL, device="cpu",
                                  compute_type="int8")
    return _model


def warm_up() -> None:
    threading.Thread(target=_get, daemon=True).start()


def _decode(path: str) -> np.ndarray:
    """Any browser format (webm/opus, mp4/aac, ogg) -> 16 kHz mono float32."""
    out = subprocess.run(
        ["ffmpeg", "-loglevel", "error", "-protocol_whitelist", "file,pipe", "-i", path, "-ac", "1", "-ar", "16000",
         "-f", "f32le", "-"], capture_output=True, check=True, timeout=60)
    return np.frombuffer(out.stdout, dtype=np.float32)


def transcribe(path: str, vocabulary: str = "") -> tuple[str, float]:
    """Return (text, seconds)."""
    t0 = time.monotonic()
    segments, _ = _get().transcribe(
        _decode(path), vad_filter=True, beam_size=1,
        initial_prompt=vocabulary or None)
    text = " ".join(s.text.strip() for s in segments).strip()
    return text, time.monotonic() - t0
