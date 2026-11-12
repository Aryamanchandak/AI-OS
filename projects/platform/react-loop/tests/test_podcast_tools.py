import os
import sys

from react_loop.config import ServerConfig
from react_loop.mcp_client import MCPClient

from podcast_tools import storage
from podcast_tools import summarize
from podcast_tools import transcription
from podcast_tools.storage import make_episode_id, read_markdown, transcript_path, write_transcript
from podcast_tools.transcription import _parse_vtt

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _simple_server() -> ServerConfig:
    return ServerConfig(command=sys.executable, args=["-m", "simple_server"], cwd=_REPO)


async def test_podcast_tool_registration():
    async with MCPClient(_simple_server()) as client:
        tools = await client.list_tools()
        names = {t.name for t in tools}
    assert {
        "podcast_list_feeds",
        "podcast_list_rss",
        "podcast_list_youtube",
        "youtube_video_summariser",
        "podcast_transcribe",
        "podcast_summarize",
        "podcast_ask",
    } <= names

    transcribe_tool = next(t for t in tools if t.name == "podcast_transcribe")
    assert "prefer_captions" in transcribe_tool.input_schema["properties"]


def test_make_episode_id_is_deterministic():
    url = "https://example.com/feed/audio-episode.mp3"
    assert make_episode_id(url) == make_episode_id(url)
    assert make_episode_id("https://youtu.be/abcdefghijk") == "yt_abcdefghijk"


def test_transcript_write_read_roundtrip(tmp_path, monkeypatch):
    # Text artifacts now live in the shared store; isolate it to a tmp dir.
    monkeypatch.setenv("CRUD_FILES_DIR", str(tmp_path))

    path = write_transcript(
        episode_id="ep_test",
        transcript="Speaker 1: Hello.\n\nSpeaker 2: Hi.",
        title="Test Episode",
        source_url="https://example.com/test.mp3",
        platform="rss",
    )

    assert path == str(transcript_path("ep_test"))
    stored = read_markdown(transcript_path("ep_test"))
    assert "episode_id: ep_test" in stored
    assert "# Transcript: Test Episode" in stored
    assert "Speaker 1: Hello." in stored


def test_parse_vtt_cleans_captions():
    raw = """WEBVTT

Kind: captions
Language: en

00:00:00.000 --> 00:00:02.000
<c>Hello&nbsp;there</c>

00:00:02.000 --> 00:00:04.000
Hello&nbsp;there

00:00:04.000 --> 00:00:06.000
general science.
"""

    assert _parse_vtt(raw) == "Hello there general science."


def test_transcribe_source_can_force_audio_path(monkeypatch, tmp_path):
    calls = []

    def fake_fetch_captions(url):
        calls.append(("captions", url))
        return "caption transcript"

    def fake_download_audio(url, title=""):
        calls.append(("download", url, title))
        return str(tmp_path / "audio.mp3")

    def fake_transcribe_audio(path):
        calls.append(("deepgram", path))
        return "audio transcript"

    def fake_write_transcript(**kwargs):
        calls.append(("write", kwargs))
        return str(tmp_path / "transcript.md")

    monkeypatch.setattr(transcription, "fetch_youtube_captions", fake_fetch_captions)
    monkeypatch.setattr(transcription, "download_podcast_audio", fake_download_audio)
    monkeypatch.setattr(transcription, "transcribe_audio", fake_transcribe_audio)
    monkeypatch.setattr(transcription, "write_transcript", fake_write_transcript)

    path = transcription.transcribe_source(
        "https://www.youtube.com/watch?v=abcdefghijk",
        title="Full Video",
        prefer_captions=False,
    )

    assert path == str(tmp_path / "transcript.md")
    assert [call[0] for call in calls] == ["download", "deepgram", "write"]
    assert calls[-1][1]["transcript"] == "audio transcript"


def test_summarize_youtube_video_chains_transcribe_then_summarize(monkeypatch):
    calls = []

    def fake_transcribe_source(url, **kwargs):
        calls.append(("transcribe", url, kwargs.get("prefer_captions")))
        return "/tmp/transcript.md"

    def fake_summarize_episode(episode_id, title="", model=None):
        calls.append(("summarize", episode_id))
        return "/tmp/summary.md"

    def fake_read_markdown(path):
        return "SUMMARY TEXT"

    # transcribe_source is imported lazily inside summarize_youtube_video, so patch
    # it on the transcription module where it is defined.
    monkeypatch.setattr(transcription, "transcribe_source", fake_transcribe_source)
    monkeypatch.setattr(summarize, "summarize_episode", fake_summarize_episode)
    monkeypatch.setattr(summarize, "read_markdown", fake_read_markdown)

    result = summarize.summarize_youtube_video(
        "https://www.youtube.com/watch?v=abcdefghijk", prefer_captions=True
    )

    assert [c[0] for c in calls] == ["transcribe", "summarize"]
    assert result["episode_id"] == "yt_abcdefghijk"
    assert result["summary"] == "SUMMARY TEXT"


def test_summary_prompt_requests_richer_sections():
    # Cheap, no-key check that the expansion (Part 3) is actually wired.
    assert "Notable Quotes" in summarize.SUMMARY_SYSTEM_PROMPT
    assert "Notable Quotes" in summarize._summary_prompt("some transcript")
