"""
tools/meeting_recorder.py — Meeting Recorder UI

UI Layer only. No recording logic here.

Extensibility points (search for TODO):
  - ACTION: Wire "Start Recording" button to browser recording API via CallHandler or JS
  - ACTION: Wire "Stop Recording" to stop stream
  - ACTION: Wire "Submit Recording" to CallTool("transcribe_and_analyse_recording")
  - ACTION: Wire "Upload Recording" button to OpenFilePicker action
  - ACTION: Wire "View Recording List" to CallTool("list_recordings")
  - STATE: Replace hardcoded "Not Recording" with reactive state variable
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastmcp import FastMCP
from prefab_ui.app import PrefabApp
from prefab_ui.components import (
    Column, Row, Card, CardContent,
    Heading, Text, Button,
)

from theme import REACT_LOOP_THEME


def meeting_recorder() -> PrefabApp:
    """
    Meeting Recorder — Record, upload, and analyse meeting audio.
    Opens the Meeting Recorder interface.
    """
    with PrefabApp(
        title="Meeting Recorder",
        theme=REACT_LOOP_THEME,
        css_class="p-6",
    ) as app:
        with Column(gap=4):

            # ── TOP RIGHT ACTION BUTTONS ──────────────────────────────────────
            with Row(css_class="justify-end", gap=2):
                Button("Upload Recording", icon="upload", variant="outline")
                Button("View Recording List", icon="list", variant="outline")

            # ── RECORDER CARD ──────────────────────────────────────────────────
            with Card(css_class="mx-auto w-2/3 text-center"):
                with CardContent(css_class="flex flex-col items-center gap-6 py-10"):
                    Heading("Audio Recorder", level=3)

                    Text("Not Recording", css_class="text-[#8cff8c] font-medium")

                    # ── RECORDING CONTROLS ─────────────────────────────────────
                    with Row(gap=3, css_class="justify-center"):
                        Button("Start Recording", icon="mic", variant="default")
                        Button("", icon="pause", size="icon", variant="outline")
                        Button("Stop Recording", icon="square", variant="destructive")

                    # ── SUBMIT / CLEAR ─────────────────────────────────────────
                    with Row(gap=3, css_class="justify-center"):
                        Button("Submit Recording", icon="send", variant="default")
                        Button("Clear Recording", icon="trash-2", variant="outline")

    return app


# Alias for route_query to call
build_ui = meeting_recorder


def register(mcp: FastMCP):
    """Registers meeting_recorder as an MCP tool."""
    mcp.tool(app=True)(meeting_recorder)


app = build_ui()
