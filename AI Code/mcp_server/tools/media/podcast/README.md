# `podcast`  ·  group: `media`

3 registered MCP tool(s). Everything for this tool lives in this folder.

### `generate_podcast_transcript(content: str, style: str = 'financial') -> str`

Generate a podcast-style spoken transcript from any input text using Gemini.

### `run_podcast_pipeline(content: str, style: str = 'financial', voice_name: str = 'Kore', output_path: str | None = None) -> str`

Convert any text into a podcast audio file in one step.

### `synthesize_podcast_audio(transcript: str, voice_name: str = 'Kore', output_path: str | None = None) -> str`

Convert a podcast transcript to a WAV audio file using Gemini TTS.

**Files:** `logic.py`, `prompts.py`, `__init__.py` (registration).
