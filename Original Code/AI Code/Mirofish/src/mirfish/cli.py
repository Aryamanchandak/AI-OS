"""MIRFISH CLI (typer).

M1 scope: `mirfish graph validate | stats | review-proposed` work; run/backtest/
report are stubs that land in M2+.
"""

from __future__ import annotations

from pathlib import Path

import typer

from mirfish.graph import DEFAULT_GRAPH_PATH, Graph, GraphError

app = typer.Typer(
    name="mirfish",
    help="Event Transmission Mapping System. Hypothesis generator, never a signal.",
    no_args_is_help=True,
)
graph_app = typer.Typer(help="Seed graph tools.", no_args_is_help=True)
app.add_typer(graph_app, name="graph")

GraphPathOpt = typer.Option(DEFAULT_GRAPH_PATH, "--graph", help="Path to graph YAML.")


def _load_graph(path: Path) -> Graph:
    try:
        return Graph.load(path)
    except FileNotFoundError:
        typer.secho(f"graph file not found: {path}", fg="red")
        raise typer.Exit(1) from None
    except GraphError as exc:
        typer.secho(str(exc), fg="red")
        raise typer.Exit(1) from None


@graph_app.command("validate")
def graph_validate(path: Path = GraphPathOpt) -> None:
    """Validate the seed graph (schema, dangling edges, duplicate aliases)."""
    graph = _load_graph(path)
    typer.secho(
        f"OK: {len(graph.nodes)} nodes, {len(graph.edges)} edges, "
        f"{graph.review_flags} edges flagged # REVIEW",
        fg="green",
    )


@graph_app.command("stats")
def graph_stats(path: Path = GraphPathOpt) -> None:
    """Print seed graph statistics."""
    stats = _load_graph(path).stats()
    typer.echo(f"nodes: {stats['nodes']}    edges: {stats['edges']}")
    typer.echo(f"avg degree: {stats['avg_degree']}    # REVIEW flags: {stats['review_flags']}")
    typer.echo("\nnodes by type:")
    for k, v in stats["nodes_by_type"].items():
        typer.echo(f"  {k:16} {v}")
    typer.echo("\nedges by channel:")
    for k, v in stats["edges_by_channel"].items():
        typer.echo(f"  {k:16} {v}")
    if stats["isolated_nodes"]:
        typer.secho(f"\nisolated nodes: {', '.join(stats['isolated_nodes'])}", fg="yellow")
    else:
        typer.echo("\nisolated nodes: none")


@graph_app.command("review-proposed")
def graph_review_proposed() -> None:
    """Review quarantined llm_proposed edges from past runs (implemented in M3)."""
    typer.secho("No proposed-edge review yet — propagation lands in M3.", fg="yellow")
    raise typer.Exit(1)


@app.command()
def run(
    fixture: Path | None = typer.Option(None, help="Event fixture YAML."),
    headline: str | None = typer.Option(None, help="Event headline."),
    body: Path | None = typer.Option(None, help="Path to event body text."),
    as_of: str | None = typer.Option(None, help="Event date YYYY-MM-DD."),
    consensus: str | None = typer.Option(None, help="Consensus context at as_of."),
) -> None:
    """Run the full pipeline on an event (implemented in M2+)."""
    typer.secho("Pipeline not implemented yet — ingest lands in M2.", fg="yellow")
    raise typer.Exit(1)


@app.command()
def backtest() -> None:
    """Run all fixtures and produce a summary table (implemented in M5)."""
    typer.secho("Backtest not implemented yet — lands in M5.", fg="yellow")
    raise typer.Exit(1)


@app.command()
def report(
    run_id: str = typer.Argument(..., help="Run ID under runs/."),
    open_: bool = typer.Option(False, "--open", help="Open the HTML report."),
) -> None:
    """Open or re-render a run's HTML report (implemented in M5)."""
    typer.secho("Reporting not implemented yet — lands in M5.", fg="yellow")
    raise typer.Exit(1)


if __name__ == "__main__":
    app()
