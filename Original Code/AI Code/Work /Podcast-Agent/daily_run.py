#!/usr/bin/env python3
"""Daily batch runner: transcribes and summarises all new podcast episodes.

Run once per day (e.g. via cron). Episodes already present in
data/processed_episodes.json are skipped — safe to re-run at any time.

Usage:
    python daily_run.py            # last 7 days (default)
    python daily_run.py --days 14  # extend lookback window
"""
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from orchestrator import (
    IngestError,
    RSSError,
    SummariseError,
    TranscribeError,
    _output_slug,
    get_all_episodes,
    ingest_direct_url,
    load_podcasts,
    save_summary,
    save_transcript,
    stream_summary,
    transcribe,
)

PROCESSED_FILE = Path("data/processed_episodes.json")
SUMMARY_MODEL = "gemini-2.5-flash"


def load_processed() -> dict:
    if PROCESSED_FILE.exists():
        return json.loads(PROCESSED_FILE.read_text())
    return {}


def save_processed(processed: dict) -> None:
    PROCESSED_FILE.parent.mkdir(parents=True, exist_ok=True)
    PROCESSED_FILE.write_text(json.dumps(processed, indent=2))


def process_episode(podcast_name: str, episode: dict, processed: dict) -> bool:
    """Download, transcribe, and summarise one episode. Updates processed in-place.

    Returns True on success, False if an error occurred.
    """
    audio_url = episode["url"]
    print(f"    Downloading audio...")
    try:
        ingest_result = ingest_direct_url(audio_url)
    except IngestError as e:
        print(f"    [error] Download failed: {e}", file=sys.stderr)
        return False

    print(f"    Transcribing...")
    try:
        tr = transcribe(ingest_result["path"], diarise=False)
    except TranscribeError as e:
        print(f"    [error] Transcription failed: {e}", file=sys.stderr)
        return False

    if tr.get("cached"):
        print(f"    (transcript from cache)")

    slug = _output_slug(podcast_name, episode["title"])
    transcript_path = save_transcript(slug, podcast_name, episode["title"], tr["text"])

    print(f"    Summarising...")
    try:
        chunks = []
        for chunk in stream_summary(
            transcript=tr["text"],
            title=episode["title"],
            source_url=audio_url,
            duration_seconds=ingest_result["duration_seconds"] or episode["duration_seconds"],
            speaker_count=tr["speaker_count"] or None,
            model=SUMMARY_MODEL,
        ):
            chunks.append(chunk)
    except SummariseError as e:
        print(f"    [error] Summarisation failed: {e}", file=sys.stderr)
        return False

    summary_path = save_summary(slug, podcast_name, episode["title"], "".join(chunks))

    processed[audio_url] = {
        "podcast_name": podcast_name,
        "episode_title": episode["title"],
        "published": episode["published"],
        "processed_at": datetime.now(timezone.utc).isoformat(),
        "transcript_path": str(transcript_path),
        "summary_path": str(summary_path),
    }
    save_processed(processed)
    print(f"    Saved -> {summary_path.name}")
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=7, help="Lookback window in days (default: 7)")
    args = parser.parse_args()

    podcasts = load_podcasts()
    if not podcasts:
        print("No podcasts found in podcasts.yaml")
        sys.exit(1)

    processed = load_processed()
    n_new = n_skipped = n_errors = 0

    print(f"Daily run — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"Checking {len(podcasts)} podcasts | lookback: {args.days} days\n")

    for podcast in podcasts:
        name = podcast["name"]
        rss = podcast["rss"]
        print(f"[{name}]")

        try:
            episodes = get_all_episodes(rss, max_age_days=args.days)
        except RSSError as e:
            print(f"  [error] RSS failed: {e}", file=sys.stderr)
            n_errors += 1
            continue

        if not episodes:
            print(f"  No episodes in the last {args.days} days")
            continue

        print(f"  Found {len(episodes)} episode(s)")
        for episode in reversed(episodes):  # oldest first so history reads chronologically
            if episode["url"] in processed:
                print(f"  [skip] {episode['title']}")
                n_skipped += 1
                continue

            print(f"  [new]  {episode['title']}")
            ok = process_episode(name, episode, processed)
            if ok:
                n_new += 1
            else:
                n_errors += 1

    print(f"\n{'─' * 40}")
    print(f"  Processed : {n_new}")
    print(f"  Skipped   : {n_skipped}")
    print(f"  Errors    : {n_errors}")


if __name__ == "__main__":
    main()
