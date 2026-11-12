"""
tools/us_result_note.py — US Result Note UI

UI Layer only. No PDF processing here.

Extensibility points (search for TODO):
  - ACTION: Wire "Choose Files" to OpenFilePicker action
  - ACTION: Wire "Upload" button to CallTool("process_morningstar_pdfs")
  - STATE: Show selected filename(s) reactively when files chosen
  - VALIDATION: Enforce 2-file max and 5MB limit in backend tool
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastmcp import FastMCP
from prefab_ui.app import PrefabApp
from prefab_ui.components import (
    Column, Row, Card, CardContent,
    Heading, Muted, Button, DropZone,
)

from theme import REACT_LOOP_THEME


def us_result_note() -> PrefabApp:
    """
    US Result Note — Upload Morningstar PDF reports to generate US earnings result notes.
    Opens the US Result Note upload interface.
    """
    with PrefabApp(
        title="US Result Note",
        theme=REACT_LOOP_THEME,
        css_class="p-6",
    ) as app:
        with Column(gap=4, css_class="items-center justify-center min-h-screen"):
            with Card(css_class="w-full max-w-xl"):
                with CardContent(css_class="flex flex-col gap-6 py-8 px-10"):

                    Heading("Upload Morningstar PDFs", level=3, css_class="text-center")

                    # ── FILE DROP ZONE ───────────────────────────────────────
                    DropZone(
                        accept=".pdf",
                        max_size=5 * 1024 * 1024,
                        label="Drag and drop PDF files here or click to browse",
                        description="Up to 2 PDF files, 5 MB each",
                        icon="file-text",
                    )

                    Muted("You can upload up to 2 PDF files. Each must be under 5 MB.")

                    # ── UPLOAD BUTTON ───────────────────────────────────────
                    with Row(css_class="justify-end"):
                        Button("Upload", icon="upload", variant="default")

    return app


# Alias for route_query to call
build_ui = us_result_note


def register(mcp: FastMCP):
    """Registers us_result_note as an MCP tool."""
    mcp.tool(app=True)(us_result_note)


app = build_ui()
