"""TTS facade. Provider catalogue under `providers/<name>/`."""

from gateway.voice.tts.base import SynthesizeResult, TTSError, TTSProvider
from gateway.voice.tts.router import synthesize

__all__ = ["SynthesizeResult", "TTSError", "TTSProvider", "synthesize"]
