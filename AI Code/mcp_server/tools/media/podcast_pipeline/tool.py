import json
import logging

from tool_registry import register
from .ingestion import (
    _make_episode_id,
    download_podcast_audio,
    list_rss_episodes,
    list_youtube_channel_episodes as _list_youtube_channel_episodes,
)
from .deliver import push_to_reader, verify_readwise_token
from tools.media.youtube.logic import summarize_youtube_video
from tools.media._pipeline_core.ingestion.bridge import sync_episode_artifacts as _sync_episode_artifacts
from tools.media._pipeline_core.backup import backup_db
from tools.media._pipeline_core.shared.contracts import ArtifactRow, EpisodeRow, ToolExecutionRow
from tools.media._pipeline_core.storage.client import get_store

logger = logging.getLogger(__name__)


def _safe_provenance_write(callback, action: str) -> None:
    try:
        callback()
    except Exception:
        logger.exception("Podcast provenance write failed during %s", action)


def _log_tool_execution(tool_name: str, episode_id: str, status: str, message: str = "") -> None:
    _safe_provenance_write(
        lambda: get_store().log_tool_execution(
            ToolExecutionRow(
                tool_name=tool_name,
                episode_id=episode_id,
                status=status,
                message=message,
            )
        ),
        f"log_tool_execution:{tool_name}",
    )


def list_rss_feed_episodes(rss_url: str, limit: int = 5) -> str:
    """
    List the latest episodes from a podcast RSS feed.

    rss_url: full RSS feed URL (e.g. https://feeds.example.com/podcast.rss).
    limit:   maximum number of episodes to return (default 5).

    Returns a JSON array. Each element has:
      episode_id, title, source_url, platform, published, description.
    """
    try:
        episodes = list_rss_episodes(rss_url, limit)
    except Exception as exc:
        _log_tool_execution(
            tool_name="list_rss_feed_episodes",
            episode_id="",
            status="error",
            message=str(exc),
        )
        raise

    _log_tool_execution(
        tool_name="list_rss_feed_episodes",
        episode_id="",
        status="completed",
        message=f"rss_url={rss_url} episodes={len(episodes)}",
    )
    return json.dumps(episodes, indent=2)


def download_podcast_audio_file(url: str, title: str = "") -> str:
    """
    Download a podcast episode audio file to local storage.

    Accepts direct audio URLs (mp3/m4a/etc.) or any YouTube URL.
    Already-downloaded files are returned from cache immediately.

    url:   direct audio URL from an RSS feed or a YouTube video URL.
    title: optional display name used for logging only.

    Returns the absolute path to the local MP3 file.
    """
    episode_id = _make_episode_id(url)
    try:
        audio_path = download_podcast_audio(url, title)
    except Exception as exc:
        _log_tool_execution(
            tool_name="download_podcast_audio_file",
            episode_id=episode_id,
            status="error",
            message=str(exc),
        )
        raise

    def _write_download_provenance() -> None:
        store = get_store()
        store.upsert_episode(
            EpisodeRow(
                episode_id=episode_id,
                title=title,
                source_url=url,
                status="downloaded",
            )
        )
        store.save_artifact(
            ArtifactRow(
                episode_id=episode_id,
                artifact_type="audio",
                artifact_path=audio_path,
            )
        )
        store.log_tool_execution(
            ToolExecutionRow(
                tool_name="download_podcast_audio_file",
                episode_id=episode_id,
                status="completed",
                message=audio_path,
            )
        )

    _safe_provenance_write(_write_download_provenance, "download_podcast_audio_file")
    return audio_path


def list_youtube_channel_episodes(channel_id: str, limit: int = 5) -> str:
    """
    List the latest videos from a YouTube channel.

    channel_id: YouTube channel ID (the UCxxxxxxxx string from the channel URL).
    limit:      maximum number of videos to return (default 5).

    Returns a JSON array. Each element has: episode_id, title, source_url, platform.
    Use the source_url with summarize_youtube_video to get a full analyst summary,
    or with download_podcast_audio_file to fetch the audio.
    """
    try:
        episodes = _list_youtube_channel_episodes(channel_id, limit)
    except Exception as exc:
        _log_tool_execution(
            tool_name="list_youtube_channel_episodes",
            episode_id="",
            status="error",
            message=str(exc),
        )
        raise

    _log_tool_execution(
        tool_name="list_youtube_channel_episodes",
        episode_id="",
        status="completed",
        message=f"channel_id={channel_id} episodes={len(episodes)}",
    )
    return json.dumps(episodes, indent=2)


def summarize_youtube_channel_latest(channel_id: str, video_index: int = 0) -> str:
    """
    Pipeline: list a YouTube channel's latest videos and summarize one of them.

    channel_id:  YouTube channel ID (UCxxxxxxxx).
    video_index: which video to summarize (0 = most recent, 1 = second most recent, etc.).

    Steps: list channel videos → pick video at video_index → fetch transcript → analyst summary.
    Returns a structured markdown summary.
    """
    try:
        episodes = _list_youtube_channel_episodes(channel_id, limit=video_index + 1)
        if not episodes:
            raise RuntimeError(f"No videos found for channel {channel_id!r}.")
        if video_index >= len(episodes):
            raise ValueError(
                f"video_index {video_index} is out of range — "
                f"only {len(episodes)} video(s) found."
            )
        video_url = episodes[video_index]["source_url"]
        title = episodes[video_index]["title"]
        summary = summarize_youtube_video(video_url)
    except Exception as exc:
        _log_tool_execution(
            tool_name="summarize_youtube_channel_latest",
            episode_id="",
            status="error",
            message=str(exc),
        )
        raise

    _log_tool_execution(
        tool_name="summarize_youtube_channel_latest",
        episode_id="",
        status="completed",
        message=f"channel_id={channel_id} video_index={video_index}",
    )
    return f"# {title}\n\n{summary}"


def push_episode_to_reader(
    html: str,
    title: str,
    source_url: str,
    author: str = "",
    tags: str = "",
    summary: str = "",
) -> str:
    """
    Save a podcast brief (HTML) to Readwise Reader inbox.

    html:       HTML content of the brief/article.
    title:      document title shown in Reader.
    source_url: original episode URL used for attribution.
    author:     optional show/author name.
    tags:       comma-separated tag list (e.g. "podcast,investing,interview").
    summary:    optional short summary shown in the Reader list view (max 500 chars).

    Requires READWISE_TOKEN environment variable.
    Returns a JSON object with keys 'id' and 'url' (the read.readwise.io link).
    """
    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []
    episode_id = _make_episode_id(source_url)
    try:
        result = push_to_reader(
            html=html,
            title=title,
            source_url=source_url,
            author=author,
            tags=tag_list,
            summary=summary,
        )
    except Exception as exc:
        _log_tool_execution(
            tool_name="push_episode_to_reader",
            episode_id=episode_id,
            status="error",
            message=str(exc),
        )
        raise

    def _write_delivery_provenance() -> None:
        store = get_store()
        store.save_artifact(
            ArtifactRow(
                episode_id=episode_id,
                artifact_type="brief_html",
                artifact_path=result.get("url", ""),
            )
        )
        store.log_tool_execution(
            ToolExecutionRow(
                tool_name="push_episode_to_reader",
                episode_id=episode_id,
                status="completed",
                message=result.get("url", ""),
            )
        )

    _safe_provenance_write(_write_delivery_provenance, "push_episode_to_reader")
    return json.dumps(result)


def check_readwise_connection() -> str:
    """
    Verify that the READWISE_TOKEN environment variable is set and accepted by Readwise.

    Returns 'OK' if the token is valid, or an error message if not.
    """
    try:
        is_valid = verify_readwise_token()
    except Exception as exc:
        _log_tool_execution(
            tool_name="check_readwise_connection",
            episode_id="",
            status="error",
            message=str(exc),
        )
        raise

    if is_valid:
        _log_tool_execution(
            tool_name="check_readwise_connection",
            episode_id="",
            status="completed",
            message="valid",
        )
        return "OK — Readwise token is valid."
    token = __import__("os").getenv("READWISE_TOKEN")
    if not token:
        _log_tool_execution(
            tool_name="check_readwise_connection",
            episode_id="",
            status="error",
            message="token_missing",
        )
        return "READWISE_TOKEN environment variable is not set."
    _log_tool_execution(
        tool_name="check_readwise_connection",
        episode_id="",
        status="error",
        message="token_rejected",
    )
    return "READWISE_TOKEN is set but was rejected by the Readwise API."


def backup_provenance_db(reason: str = "") -> str:
    """Create a hot-copy backup of the SQLite provenance database."""
    return str(backup_db(reason=reason))


def sync_episode_artifacts(episode_id: str) -> str:
    """
    Sync pipeline disk artifacts for an episode into SQLite provenance.

    episode_id: canonical pipeline episode id (e.g. yt_<videoid> or ep_<hash>).

    Returns a JSON summary with artifact and claim counts.
    """
    return json.dumps(_sync_episode_artifacts(episode_id), indent=2)


def get_episode_status(episode_id: str) -> str:
    """Return the stored provenance record for an episode as JSON."""
    return json.dumps(get_store().get_episode(episode_id), indent=2)


def get_episode_claims(episode_id: str) -> str:
    """Return the stored claims for an episode as JSON."""
    return json.dumps(get_store().get_claims(episode_id), indent=2)


def get_episode_runs(episode_id: str) -> str:
    """Return the run history for an episode as JSON."""
    return json.dumps(get_store().get_runs(episode_id), indent=2)


for _fn in [
    list_rss_feed_episodes,
    download_podcast_audio_file,
    list_youtube_channel_episodes,
    summarize_youtube_channel_latest,
    push_episode_to_reader,
    check_readwise_connection,
    sync_episode_artifacts,
    backup_provenance_db,
    get_episode_status,
    get_episode_claims,
    get_episode_runs,
]:
    register(group="media")(_fn)
