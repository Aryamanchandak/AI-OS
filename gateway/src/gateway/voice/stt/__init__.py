"""STT facade. The dispatcher in `router.py` routes by `prefer=...` to
the provider catalogue under `providers/<name>/`."""

from gateway.voice.stt.base import STTError, STTProvider, TranscribeResult
from gateway.voice.stt.router import transcribe

__all__ = ["STTError", "STTProvider", "TranscribeResult", "transcribe"]
