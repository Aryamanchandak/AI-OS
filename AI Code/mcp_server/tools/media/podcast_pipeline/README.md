# `podcast_pipeline`  ·  group: `media`

11 registered MCP tool(s). Everything for this tool lives in this folder.

### `backup_provenance_db(reason: str = '') -> str`

Create a hot-copy backup of the SQLite provenance database.

### `check_readwise_connection() -> str`

Verify that the READWISE_TOKEN environment variable is set and accepted by Readwise.

### `download_podcast_audio_file(url: str, title: str = '') -> str`

Download a podcast episode audio file to local storage.

### `get_episode_claims(episode_id: str) -> str`

Return the stored claims for an episode as JSON.

### `get_episode_runs(episode_id: str) -> str`

Return the run history for an episode as JSON.

### `get_episode_status(episode_id: str) -> str`

Return the stored provenance record for an episode as JSON.

### `list_rss_feed_episodes(rss_url: str, limit: int = 5) -> str`

List the latest episodes from a podcast RSS feed.

### `list_youtube_channel_episodes(channel_id: str, limit: int = 5) -> str`

List the latest videos from a YouTube channel.

### `push_episode_to_reader(html: str, title: str, source_url: str, author: str = '', tags: str = '', summary: str = '') -> str`

Save a podcast brief (HTML) to Readwise Reader inbox.

### `summarize_youtube_channel_latest(channel_id: str, video_index: int = 0) -> str`

Pipeline: list a YouTube channel's latest videos and summarize one of them.

### `sync_episode_artifacts(episode_id: str) -> str`

Sync pipeline disk artifacts for an episode into SQLite provenance.

**Files:** `deliver.py`, `ingestion.py`, `tool.py`, `__init__.py` (registration).
