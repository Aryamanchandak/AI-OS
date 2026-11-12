"""
tools/podcast_agent.py — Podcast Agent UI

UI Layer only. No audio generation here.

Extensibility points (search for TODO):
  - DATA: Replace config.SECTORS audio_url="" with real CDN URLs from DB
  - ACTION: Audio players auto-populate when audio_url is filled in
  - FEATURE: Add "Generate Podcast" button per sector row to trigger backend
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastmcp import FastMCP
from prefab_ui.app import PrefabApp
from prefab_ui.components import (
    Column, Row,
    Heading, Icon, Text,
    DataTable, DataTableColumn,
    Audio,
)

import config
from theme import REACT_LOOP_THEME


def _build_sector_rows() -> list[dict]:
    """
    Build DataTable row dicts from config.SECTORS.
    Each row has a 'sector' cell (Row with speaker icon + text)
    and a 'podcast' cell (Audio component if URL present, else placeholder text).

    TODO DATA: When audio_url is populated in config.SECTORS, the Audio component
    will render with native playback controls automatically.
    """
    rows = []
    for sector_data in config.SECTORS:
        # Sector cell: orange speaker icon + sector name text
        sector_cell = Row(gap=2, align="center")
        with sector_cell:
            Icon("volume-2", css_class="text-[#5cffc3]", size="sm")
            Text(sector_data["sector"])

        # Podcast cell: Audio player if URL present, placeholder Muted text if not
        if sector_data["audio_url"]:
            podcast_cell = Audio(
                src=sector_data["audio_url"],
                controls=True,
                css_class="w-full",
            )
        else:
            # TODO DATA: Replace placeholder when audio_url is wired from DB
            podcast_cell = Text("—", css_class="text-muted-foreground text-sm")

        rows.append({
            "sector":  sector_cell,
            "podcast": podcast_cell,
        })
    return rows


def podcast_agent() -> PrefabApp:
    """
    Podcast Agent — Listen to AI-generated sector-wise financial podcasts.
    Opens the Podcast interface with audio players per sector.
    """
    # Build row data BEFORE opening any PrefabApp/Column context so that the
    # Row/Icon/Text components created inside _build_sector_rows() are not
    # auto-attached to any active parent context — they only exist as objects
    # referenced in the row dicts, which DataTable then renders in cells.
    sector_rows = _build_sector_rows()

    with PrefabApp(
        title="Podcast Agent",
        theme=REACT_LOOP_THEME,
        css_class="p-6",
    ) as app:
        with Column(gap=4):
            Heading("Sector Podcasts", level=3)

            # DataTable with component cells (supported per docs)
            # Themed hairline header — uppercase micro-label treatment
            DataTable(
                columns=[
                    DataTableColumn(
                        key="sector",
                        header="SECTOR",
                        header_class="font-semibold uppercase tracking-wider text-[10px]",
                        min_width="180px",
                    ),
                    DataTableColumn(
                        key="podcast",
                        header="PODCAST",
                        header_class="font-semibold uppercase tracking-wider text-[10px]",
                    ),
                ],
                rows=sector_rows,
            )

    return app


# Alias for route_query to call
build_ui = podcast_agent


def register(mcp: FastMCP):
    """Registers podcast_agent as an MCP tool."""
    mcp.tool(app=True)(podcast_agent)


app = build_ui()
