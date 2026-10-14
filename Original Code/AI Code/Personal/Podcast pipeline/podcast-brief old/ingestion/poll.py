"""
poll.py — Check all configured shows for new episodes and process them.

Designed to be run on a cron schedule (e.g. 4am daily).
"""

from rich.console import Console

from core import state
from . import ingest
from core import pipeline
from core.config import load_shows, ShowConfig


console = Console()


def poll_all_shows(limit_per_show: int = 3, dry_run: bool = False):
    """Check every active show for new episodes and process them sequentially."""
    state.init_db()
    shows = [s for s in load_shows() if s.active]

    if not shows:
        console.print("[yellow]No active shows configured. Edit config/shows.yaml.[/yellow]")
        return

    console.print(f"[bold]Polling {len(shows)} active show(s)...[/bold]\n")

    new_episodes = []
    for show in shows:
        console.print(f"[cyan]→ {show.name}[/cyan]")
        candidates = _find_new_episodes(show, limit_per_show)
        if not candidates:
            console.print("  [dim]No new episodes.[/dim]")
            continue

        for c in candidates:
            console.print(f"  [green]NEW:[/green] {c['title']}")
            new_episodes.append((show, c))

    if not new_episodes:
        console.print("\n[bold green]All caught up.[/bold green]")
        return

    console.print(f"\n[bold]{len(new_episodes)} new episode(s) to process.[/bold]\n")

    if dry_run:
        console.print("[yellow](dry-run — not processing)[/yellow]")
        return

    failed = []
    for i, (show, ep) in enumerate(new_episodes, 1):
        console.print(f"\n{'─' * 70}")
        console.print(f"[bold]Processing {i}/{len(new_episodes)}: {ep['title']}[/bold]")
        console.print(f"{'─' * 70}")
        try:
            pipeline.run_pipeline(
                url=ep["url"],
                show=show,
            )
        except Exception as e:
            console.print(f"[red]✗ Failed: {e}[/red]")
            failed.append((show.name, ep["title"], str(e)))

    console.print(f"\n[bold]Poll complete.[/bold]")
    console.print(f"  Processed: {len(new_episodes) - len(failed)}/{len(new_episodes)}")
    if failed:
        console.print(f"  [red]Failed: {len(failed)}[/red]")
        for show_name, title, err in failed:
            console.print(f"    - [{show_name}] {title}: {err}")


def _find_new_episodes(show: ShowConfig, limit: int) -> list[dict]:
    """
    Find new episodes for a show. Tries RSS first, falls back to YouTube.
    Returns list of {id, url, title} dicts for episodes not yet processed.
    """
    candidates = []

    # Prefer RSS — usually has cleaner metadata and smaller files
    if show.rss:
        try:
            rss_episodes = ingest.get_latest_rss_episodes(show.rss, limit=limit)
            for ep in rss_episodes:
                ep_id = ingest.make_episode_id(ep.audio_url)
                if not state.episode_exists(ep_id):
                    candidates.append({
                        "id": ep_id,
                        "url": ep.audio_url,
                        "title": ep.title,
                    })
        except Exception as e:
            console.print(f"  [dim red]RSS fetch failed: {e}[/dim red]")

    # Fall back to YouTube if RSS yielded nothing or isn't configured
    if not candidates and show.youtube_channel:
        try:
            yt_episodes = ingest.get_latest_youtube_episodes(show.youtube_channel, limit=limit)
            for ep in yt_episodes:
                if not state.episode_exists(ep["id"]):
                    candidates.append({
                        "id": ep["id"],
                        "url": ep["url"],
                        "title": ep["title"],
                    })
        except Exception as e:
            console.print(f"  [dim red]YouTube fetch failed: {e}[/dim red]")

    return candidates
