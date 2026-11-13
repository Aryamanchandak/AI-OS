"""The notebook screen, built with Prefab.

One function turns the current notes into a `PrefabApp`. Buttons on the
screen call the server's `notes_file` tool, and the reply refreshes the
screen's state, so the page and the file never disagree.
"""

from __future__ import annotations

from prefab_ui.actions import SetState, ShowToast
from prefab_ui.actions.mcp import CallTool
from prefab_ui.app import PrefabApp
from prefab_ui.components import (
    Badge,
    Button,
    Card,
    CardContent,
    CardDescription,
    CardHeader,
    CardTitle,
    Column,
    DataTable,
    DataTableColumn,
    Grid,
    Heading,
    Input,
    Metric,
    Muted,
    Row,
    Textarea,
)
from prefab_ui.components.charts import PieChart
from prefab_ui.rx import RESULT

NOTES_TOOL = "notes_file"


def _refresh() -> list:
    """After any change, copy the tool's reply into the screen's state."""
    return [
        SetState("notes", RESULT.notes),
        SetState("counts", RESULT.counts),
        SetState("chart", RESULT.chart),
    ]


def _call(arguments: dict, done: str) -> CallTool:
    return CallTool(
        NOTES_TOOL,
        arguments=arguments,
        on_success=[*_refresh(), ShowToast(done, variant="success")],
        on_error=ShowToast("{{ $error }}", variant="error"),
    )


def chart_rows(counts: dict[str, int]) -> list[dict]:
    return [
        {"status": "Verified", "notes": counts["verified"]},
        {"status": "Unverified", "notes": counts["unverified"]},
    ]


def build_notebook(notes: list[dict], counts: dict[str, int], topic: str = "") -> PrefabApp:
    state = {
        "notes": notes,
        "counts": counts,
        "chart": chart_rows(counts),
        "selected": None,
        "new_title": "",
        "new_body": "",
        "new_source": "",
    }
    with PrefabApp(title="Research notebook", state=state) as app:
        with Column(gap=6, css_class="max-w-5xl mx-auto p-6"):
            with Row(gap=3, align="center"):
                Heading("Research notebook")
                if topic:
                    Badge(topic, variant="secondary")
            Muted("What you have read, and how much of it you have checked.")

            with Grid(columns=3, gap=4):
                with Card(css_class="p-6"):
                    Metric(label="Notes", value="{{ counts.total }}")
                with Card(css_class="p-6"):
                    Metric(label="Verified", value="{{ counts.verified }}")
                with Card(css_class="p-6"):
                    Metric(label="Still to check", value="{{ counts.unverified }}")

            with Grid(columns=[2, 1], gap=4):
                with Card():
                    with CardHeader():
                        CardTitle("Notes")
                        CardDescription("Click a row to select it.")
                    with CardContent():
                        DataTable(
                            columns=[
                                DataTableColumn(key="title", header="Title", sortable=True),
                                DataTableColumn(key="status", header="Status", sortable=True),
                                DataTableColumn(key="source_url", header="Source"),
                                DataTableColumn(key="created_at", header="Saved", sortable=True),
                            ],
                            rows="{{ notes }}",
                            search=True,
                            search_placeholder="Search notes...",
                            paginated=True,
                            on_row_click=SetState("selected", "{{ $event }}"),
                        )
                with Card():
                    with CardHeader():
                        CardTitle("Checked so far")
                    with CardContent():
                        PieChart(data="{{ chart }}", data_key="notes", name_key="status")

            with Card():
                with CardHeader():
                    CardTitle("{{ selected ? selected.title : 'No note selected' }}")
                    CardDescription("{{ selected ? selected.status : 'Pick a note from the table.' }}")
                with CardContent():
                    with Column(gap=4):
                        Muted("{{ selected ? selected.body : '' }}")
                        with Row(gap=2):
                            Button(
                                "Mark verified",
                                on_click=_call(
                                    {"action": "update", "note_id": "{{ selected.id }}", "status": "verified"},
                                    "Marked verified",
                                ),
                            )
                            Button(
                                "Mark unverified",
                                variant="outline",
                                on_click=_call(
                                    {"action": "update", "note_id": "{{ selected.id }}", "status": "unverified"},
                                    "Marked unverified",
                                ),
                            )
                            Button(
                                "Delete",
                                variant="destructive",
                                on_click=[
                                    _call({"action": "delete", "note_id": "{{ selected.id }}"}, "Deleted"),
                                    SetState("selected", None),
                                ],
                            )

            with Card():
                with CardHeader():
                    CardTitle("Add a note")
                with CardContent():
                    with Column(gap=3):
                        Input(name="new_title", placeholder="Title")
                        Textarea(name="new_body", placeholder="What did you read?")
                        Input(name="new_source", placeholder="Source link (optional)")
                        Button(
                            "Save note",
                            on_click=_call(
                                {
                                    "action": "create",
                                    "title": "{{ new_title }}",
                                    "body": "{{ new_body }}",
                                    "source_url": "{{ new_source }}",
                                },
                                "Saved",
                            ),
                        )
    return app
