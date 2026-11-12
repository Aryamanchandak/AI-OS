"""
podcast-pipeline CLI — no MCP, no agents, direct Python calls.

Use this for automation scripts or when something breaks on the agent side.
All logic lives in the podcast-brief MCP project; this is a thin caller.

Usage:
    python run.py rss <rss_url> [--limit 5]
    python run.py youtube <channel_id> [--limit 5]
    python run.py download <url> [--title "Episode title"]
    python run.py deliver <html_file> <title> <source_url>
    python run.py sync <episode_id>
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Point at the podcast-brief MCP project so we can import from it.
PODCAST_PROJECT = Path("/Users/aryamanchandak/Documents/AI Code/Personal/Podcast pipeline/podcast-brief MCP")
if str(PODCAST_PROJECT) not in sys.path:
    sys.path.insert(0, str(PODCAST_PROJECT))

MCP_SERVER_PROJECT = Path("/Users/aryamanchandak/Documents/AI Code/mcp_server")


def cmd_rss(args):
    from mcp_tools.ingestion import RSSFeedRequest, list_rss_episodes
    episodes = list_rss_episodes(RSSFeedRequest(rss_url=args.rss_url, limit=args.limit))
    for ep in episodes:
        print(f"[{ep.episode_id}] {ep.title}")
        print(f"  {ep.source_url}")
        if ep.published:
            print(f"  published: {ep.published}")
        print()


def cmd_youtube(args):
    from mcp_tools.ingestion import YouTubeChannelRequest, list_youtube_episodes
    episodes = list_youtube_episodes(YouTubeChannelRequest(channel_id=args.channel_id, limit=args.limit))
    for ep in episodes:
        print(f"[{ep.episode_id}] {ep.title}")
        print(f"  {ep.source_url}")
        print()


def cmd_download(args):
    from mcp_tools.ingestion import AudioDownloadRequest, download_audio
    result = download_audio(AudioDownloadRequest(url=args.url, title=args.title or ""))
    print(f"episode_id : {result.episode.episode_id}")
    print(f"title      : {result.episode.title}")
    print(f"audio_path : {result.audio_path}")
    print(f"cached     : {result.cached}")


def cmd_deliver(args):
    from mcp_tools.tools.deliver import push_to_reader, verify_readwise_token
    if not verify_readwise_token():
        print("ERROR: READWISE_TOKEN is missing or invalid. Set it in your environment.")
        sys.exit(1)
    html = Path(args.html_file).read_text(encoding="utf-8")
    result = push_to_reader(html=html, title=args.title, source_url=args.source_url)
    print(f"Saved to Reader: {result['url']}")


def cmd_backup(args):
    if str(MCP_SERVER_PROJECT) not in sys.path:
        sys.path.insert(0, str(MCP_SERVER_PROJECT))
    from mcp_tools.backup import backup_db
    backup_path = backup_db(reason=args.reason)
    print(backup_path)


def cmd_sync(args):
    if str(MCP_SERVER_PROJECT) not in sys.path:
        sys.path.insert(0, str(MCP_SERVER_PROJECT))
    from mcp_tools.ingestion.bridge import sync_episode_artifacts
    print(json.dumps(sync_episode_artifacts(args.episode_id), indent=2))


def main():
    parser = argparse.ArgumentParser(description="Podcast pipeline CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    p_rss = sub.add_parser("rss", help="List episodes from an RSS feed")
    p_rss.add_argument("rss_url")
    p_rss.add_argument("--limit", type=int, default=5)

    p_yt = sub.add_parser("youtube", help="List episodes from a YouTube channel")
    p_yt.add_argument("channel_id")
    p_yt.add_argument("--limit", type=int, default=5)

    p_dl = sub.add_parser("download", help="Download audio for a URL")
    p_dl.add_argument("url")
    p_dl.add_argument("--title", default="")

    p_del = sub.add_parser("deliver", help="Push an HTML brief to Readwise Reader")
    p_del.add_argument("html_file", help="Path to HTML file")
    p_del.add_argument("title")
    p_del.add_argument("source_url")

    p_backup = sub.add_parser("backup", help="Create a provenance DB backup")
    p_backup.add_argument("--reason", default="")

    p_sync = sub.add_parser("sync", help="Sync pipeline artifacts into provenance DB")
    p_sync.add_argument("episode_id")

    args = parser.parse_args()
    dispatch = {
        "rss": cmd_rss,
        "youtube": cmd_youtube,
        "download": cmd_download,
        "deliver": cmd_deliver,
        "backup": cmd_backup,
        "sync": cmd_sync,
    }
    dispatch[args.command](args)


if __name__ == "__main__":
    main()
