"""Pure presentation helpers shared by the Streamlit and HTML interfaces.

Both UI shells (web/app.py's Jinja templates and legacy/main.py's Streamlit
widgets) need to turn the same resolved Graph into glyphs, labels, table
rows, and a Graphviz DOT string. Keeping that logic here instead of
duplicating it per UI means the two shells can never visually disagree about
what a "sharply up" outcome looks like, and it stays testable without a
browser or a Streamlit runtime. No LLM calls, no I/O — everything here is a
pure function of a Graph.
"""

from __future__ import annotations

import itertools
import textwrap

import pandas as pd

from engine.schema import Graph
from engine.sensitivity import load_bearing_edges

_INTERROGATIVES = {
    "does",
    "do",
    "will",
    "is",
    "are",
    "did",
    "has",
    "have",
    "can",
    "would",
    "could",
    "should",
    "might",
}


def short_label(question: str) -> str:
    """Compress a yes/no question into a short phrase for scenario names."""
    words = question.strip().rstrip("?").split()
    if words and words[0].lower() in _INTERROGATIVES:
        words = words[1:]
    label = " ".join(words)
    return label[:1].upper() + label[1:] if label else question


def scenario_name(graph: Graph, assignment: dict[str, int]) -> str:
    """Return a readable scenario name for one unknown assignment."""
    parts = []
    for unknown in graph.unknowns:
        mark = "✓" if assignment.get(unknown.id, 1) >= 0 else "✗"
        parts.append(f"{short_label(unknown.question)} {mark}")
    return " · ".join(parts)


def all_assignments(graph: Graph) -> list[dict[str, int]]:
    """Return the stable four-scenario order over the graph's two unknowns."""
    u1, u2 = graph.unknowns[0].id, graph.unknowns[1].id
    return [
        {u1: first, u2: second}
        for first, second in itertools.product((1, -1), (1, -1))
    ]


_CELL = {
    (1, "high"): "↑↑",
    (1, "med"): "↑",
    (1, "low"): "▴",
    (-1, "high"): "↓↓",
    (-1, "med"): "↓",
    (-1, "low"): "▾",
}


def cell(node) -> str:
    """Map a resolved node to the compact glyph used in comparison tables."""
    if node.contested:
        return "⚠"
    if node.sign == 0:
        return "·"
    return _CELL.get((node.sign, node.magnitude), "·")


def impact_class(node) -> str:
    """Return the semantic CSS class for one resolved outcome."""
    if node.contested:
        return "impact-contested"
    if node.sign > 0:
        return "impact-up"
    if node.sign < 0:
        return "impact-down"
    return "impact-flat"


def _dot_escape(value: str) -> str:
    """Escape arbitrary model-generated text for a quoted Graphviz value."""
    return (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\r", "")
        .replace("\n", "\\n")
    )


def _wrapped(value: str, width: int = 24) -> str:
    """Wrap labels so wide causal graphs remain readable."""
    return "\\n".join(
        _dot_escape(line)
        for line in textwrap.wrap(value, width=width, break_long_words=False)
    )


def graph_to_dot(graph: Graph) -> str:
    """Return a polished left-to-right Graphviz diagram for a causal graph."""
    node_styles = {
        "intervention": {
            "fillcolor": "#17212B",
            "color": "#D7A443",
            "fontcolor": "#FFF9EC",
            "penwidth": "2.0",
        },
        "intermediate": {
            "fillcolor": "#FFFDF8",
            "color": "#D8D1C3",
            "fontcolor": "#17212B",
            "penwidth": "1.2",
        },
        "outcome": {
            "fillcolor": "#EDF4EE",
            "color": "#66816C",
            "fontcolor": "#263C2C",
            "penwidth": "1.7",
        },
    }

    lines = [
        "digraph causal_graph {",
        '  graph [rankdir="LR", bgcolor="transparent", pad="0.35", '
        'nodesep="0.55", ranksep="0.9", splines="spline", outputorder="edgesfirst"];',
        '  node [shape="box", style="rounded,filled", margin="0.18,0.12", '
        'fontname="Manrope", fontsize="12"];',
        '  edge [fontname="Manrope", fontsize="10", arrowsize="0.75", '
        'penwidth="1.7"];',
    ]

    for node in graph.nodes:
        style = node_styles.get(node.node_type, node_styles["intermediate"])
        tooltip = _dot_escape(f"{node.id} · {node.node_type} · {node.label}")
        lines.append(
            f'  "{_dot_escape(node.id)}" [label="{_wrapped(node.label)}", '
            f'fillcolor="{style["fillcolor"]}", color="{style["color"]}", '
            f'fontcolor="{style["fontcolor"]}", penwidth="{style["penwidth"]}", '
            f'tooltip="{tooltip}"];'
        )

    for unknown in graph.unknowns:
        unknown_id = f"unknown_{unknown.id}"
        tooltip = _dot_escape(
            f"{unknown.id} sets {unknown.affects_node_id}: {unknown.question}"
        )
        lines.append(
            f'  "{_dot_escape(unknown_id)}" [label="{_wrapped(unknown.question, 28)}", '
            'shape="box", style="rounded,filled,dashed", fillcolor="#FFF7E6", '
            'color="#D7A443", fontcolor="#684B12", penwidth="1.5", '
            f'tooltip="{tooltip}"];'
        )
        lines.append(
            f'  "{_dot_escape(unknown_id)}" -> '
            f'"{_dot_escape(unknown.affects_node_id)}" '
            '[label="sets", style="dashed", color="#B47C1B", '
            'fontcolor="#684B12", penwidth="1.3"];'
        )

    for edge in graph.edges:
        positive = edge.sign > 0
        color = "#3E6C89" if positive else "#A44D43"
        sign = "+" if positive else "−"
        mechanism = _dot_escape(edge.mechanism)
        lines.append(
            f'  "{_dot_escape(edge.src)}" -> "{_dot_escape(edge.dst)}" '
            f'[label="{sign} {edge.strength}", color="{color}", '
            f'fontcolor="{color}", tooltip="{mechanism}"];'
        )

    outcome_ids = [
        f'"{_dot_escape(node.id)}"'
        for node in graph.nodes
        if node.node_type == "outcome"
    ]
    if outcome_ids:
        lines.append(f'  {{ rank="same"; {"; ".join(outcome_ids)}; }}')

    lines.append("}")
    return "\n".join(lines)


def edge_robustness(
    graph: Graph,
    assignment: dict[str, int],
) -> pd.DataFrame:
    """Name the exact load-bearing links for the selected scenario."""
    impacts = load_bearing_edges(graph, [assignment], limit=len(graph.edges))
    node_labels = {node.id: node.label for node in graph.nodes}
    rows = []
    for impact in impacts:
        edge = graph.edges[impact.edge_index]
        outcomes = ", ".join(
            node_labels[outcome_id] for outcome_id in impact.changed_outcomes
        )
        rows.append(
            {
                "Edge": f"{node_labels[edge.src]} → {node_labels[edge.dst]}",
                "Mechanism": edge.mechanism,
                "Changed outcomes": outcomes,
                "Evidence": edge.evidence_status,
            }
        )
    return pd.DataFrame(rows)
