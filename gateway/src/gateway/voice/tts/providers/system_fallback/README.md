# System TTS fallback (shipped working)

This provider ships fully implemented to keep
`/v1/speak?prefer=fallback` working on a fresh install before another TTS
provider is configured.

## How it works

- macOS: invokes the bundled `say` binary, returns AIFF.
- Linux / Windows: invokes `pyttsx3`, returns WAV.

No API keys. No models to download. Cross-platform.

## When to override it

If your environment has neither `say` nor `pyttsx3`, the provider
raises `TTSError`. That is the signal to either install `pyttsx3`
(`uv pip install pyttsx3`) or to drop in one of the other providers
(`prefer=default` → Kokoro, `prefer=quality` → ElevenLabs).
