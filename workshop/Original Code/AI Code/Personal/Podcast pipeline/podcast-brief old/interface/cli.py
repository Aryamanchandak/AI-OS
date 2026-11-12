"""
cli.py — Command-line interface for podcast-brief.

Usage:
    podcast-brief brief <url> [--profile P] [--show "Name"] [--transcript-only]
    podcast-brief browse [show-name] [--limit N]
    podcast-brief poll
    podcast-brief recent [--limit N]
    podcast-brief check
"""

import sys
import argparse
from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table

# Load .env before importing modules that read env vars
load_dotenv()

from core import state
from core import pipeline
from core.config import load_shows, find_show_by_url, ensure_dirs


console = Console()


def cmd_brief(args):
    """Manually generate a brief from a URL."""
    show = None
    if args.show:
        for s in load_shows():
            if s.name.lower() == args.show.lower():
                show = s
                break
        if not show:
            console.print(f"[red]No configured show named '{args.show}'.[/red]")
            console.print("Available shows:")
            for s in load_shows():
                console.print(f"  - {s.name}")
            sys.exit(1)
    else:
        # Try to auto-match the URL to a configured show
        show = find_show_by_url(args.url)

    profile = args.profile or (show.profile if show else "hybrid")
    speakers_hint = show.speakers_hint if show else ""
    show_name = show.name if show else "Manual entry"

    try:
        pipeline.run_pipeline(
            url=args.url,
            show=show,
            profile=profile,
            speakers_hint=speakers_hint,
            show_name=show_name,
            transcript_only=args.transcript_only,
            skip_research=args.skip_research,
        )
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted.[/yellow]")
        sys.exit(130)
    except Exception as e:
        console.print(f"\n[bold red]✗ Pipeline failed:[/bold red] {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


def cmd_browse(args):
    """Interactively pick an episode from a show's RSS feed and brief it."""
    from ingestion.ingest import get_latest_rss_episodes

    shows = [s for s in load_shows() if s.rss and s.active]
    if not shows:
        console.print("[yellow]No active shows with RSS configured.[/yellow]")
        return

    # Show selection
    if args.show:
        matched = [s for s in shows if s.name.lower() == args.show.lower()]
        if not matched:
            console.print(f"[red]No show named '{args.show}'.[/red]")
            for s in shows:
                console.print(f"  - {s.name}")
            sys.exit(1)
        show = matched[0]
    else:
        console.print("[bold]Available shows:[/bold]")
        for i, s in enumerate(shows, 1):
            console.print(f"  {i}. {s.name}")
        raw = input("\nPick a show (number): ").strip()
        if not raw.isdigit() or not (1 <= int(raw) <= len(shows)):
            console.print("[red]Invalid selection.[/red]")
            sys.exit(1)
        show = shows[int(raw) - 1]

    # Fetch episodes
    console.print(f"\n[dim]Fetching episodes from {show.name}…[/dim]")
    try:
        episodes = get_latest_rss_episodes(show.rss, limit=args.limit)
    except Exception as e:
        console.print(f"[red]RSS fetch failed:[/red] {e}")
        sys.exit(1)

    if not episodes:
        console.print("[yellow]No episodes found in feed.[/yellow]")
        return

    # Display episode table
    table = Table(title=show.name)
    table.add_column("#", style="dim", width=3)
    table.add_column("Title")
    table.add_column("Published", style="dim")
    for i, ep in enumerate(episodes, 1):
        table.add_row(str(i), ep.title[:70], ep.published[:16])
    console.print(table)

    raw = input("\nPick an episode (number, or q to quit): ").strip()
    if raw.lower() == "q":
        return
    if not raw.isdigit() or not (1 <= int(raw) <= len(episodes)):
        console.print("[red]Invalid selection.[/red]")
        sys.exit(1)
    ep = episodes[int(raw) - 1]

    # Run pipeline
    console.print(f"\n[bold]Briefing:[/bold] {ep.title}")
    try:
        pipeline.run_pipeline(
            url=ep.audio_url,
            show=show,
            profile=args.profile or show.profile,
            speakers_hint=show.speakers_hint,
            show_name=show.name,
            transcript_only=args.transcript_only,
            skip_research=args.skip_research,
        )
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted.[/yellow]")
        sys.exit(130)
    except Exception as e:
        console.print(f"\n[bold red]✗ Pipeline failed:[/bold red] {e}")
        sys.exit(1)


def cmd_poll(args):
    """Check all configured shows for new episodes and process them."""
    from ingestion import poll
    poll.poll_all_shows(limit_per_show=args.limit, dry_run=args.dry_run)


def cmd_recent(args):
    """List recently processed episodes."""
    state.init_db()
    episodes = state.get_recent_episodes(limit=args.limit)

    if not episodes:
        console.print("[yellow]No episodes processed yet.[/yellow]")
        return

    table = Table(title=f"Recent episodes (last {args.limit})")
    table.add_column("Date", style="dim")
    table.add_column("Show")
    table.add_column("Title")
    table.add_column("Status")
    table.add_column("Reader")

    for ep in episodes:
        status_color = {
            "completed": "green",
            "error": "red",
            "pending": "yellow",
        }.get(ep["status"], "white")
        reader = ep["reader_url"] or "—"
        if reader != "—":
            reader = f"[link={reader}]open[/link]"
        table.add_row(
            (ep["created_at"] or "")[:10],
            ep["show_name"][:25],
            (ep["title"] or "")[:50],
            f"[{status_color}]{ep['status']}[/{status_color}]",
            reader,
        )
    console.print(table)


def cmd_check(args):
    """Check that API keys are configured and reachable."""
    from core.config import check_config
    console.print("[bold]Checking environment and API connectivity...[/bold]\n")

    result = check_config()

    for key, info in result["keys"].items():
        status = "[green]✓ set[/green]" if info["set"] else "[yellow]✗ missing[/yellow]"
        console.print(f"  {status}  {key}  — {info['description']}")

    console.print()

    if result["readwise_token_valid"] is not None:
        if result["readwise_token_valid"]:
            console.print("  [green]✓[/green] Readwise token is valid")
        else:
            console.print("  [red]✗[/red] Readwise token rejected by API")

    shows = result["shows"]
    console.print(f"\n[bold]Shows configured:[/bold] {len(shows)}")
    for s in shows:
        sources_str = " + ".join(s["sources"]) if s["sources"] else "no sources"
        active = "[green]active[/green]" if s["active"] else "[dim]inactive[/dim]"
        console.print(f"  - {s['name']}  ({s['profile']}, {sources_str}, {active})")


def main():
    parser = argparse.ArgumentParser(
        prog="podcast-brief",
        description="Generate research briefs from podcasts and push to Readwise Reader.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # brief
    p_brief = sub.add_parser("brief", help="Generate a brief from a URL.")
    p_brief.add_argument("url", help="YouTube URL, direct MP3 URL, or RSS item URL.")
    p_brief.add_argument("--profile", choices=["academic", "current_events", "hybrid"],
                         help="Override the profile for this brief.")
    p_brief.add_argument("--show", help="Use a configured show (matches by name).")
    p_brief.add_argument("--transcript-only", action="store_true",
                         help="Just transcribe and push the transcript to Reader.")
    p_brief.add_argument("--skip-research", action="store_true",
                         help="Skip the research stage (faster, cheaper, less useful).")
    p_brief.add_argument("--verbose", "-v", action="store_true")
    p_brief.set_defaults(func=cmd_brief)

    # poll
    p_poll = sub.add_parser("poll", help="Check all shows for new episodes.")
    p_poll.add_argument("--limit", type=int, default=3,
                        help="Max new episodes to check per show.")
    p_poll.add_argument("--dry-run", action="store_true",
                        help="Show what would be processed, don't actually run.")
    p_poll.set_defaults(func=cmd_poll)

    # recent
    p_recent = sub.add_parser("recent", help="List recently processed episodes.")
    p_recent.add_argument("--limit", type=int, default=20)
    p_recent.set_defaults(func=cmd_recent)

    # check
    p_check = sub.add_parser("check", help="Verify environment and configuration.")
    p_check.set_defaults(func=cmd_check)

    # browse
    p_browse = sub.add_parser("browse", help="Pick an episode from a show's RSS feed and brief it.")
    p_browse.add_argument("show", nargs="?", help="Show name (optional; prompts interactively if omitted).")
    p_browse.add_argument("--limit", type=int, default=8, help="Number of episodes to fetch from RSS.")
    p_browse.add_argument("--profile", choices=["academic", "current_events", "hybrid"],
                          help="Override the synthesis profile.")
    p_browse.add_argument("--transcript-only", action="store_true",
                          help="Transcribe and push to Reader without research or synthesis.")
    p_browse.add_argument("--skip-research", action="store_true",
                          help="Skip the research stage.")
    p_browse.set_defaults(func=cmd_browse)

    args = parser.parse_args()
    ensure_dirs()
    args.func(args)


if __name__ == "__main__":
    main()
