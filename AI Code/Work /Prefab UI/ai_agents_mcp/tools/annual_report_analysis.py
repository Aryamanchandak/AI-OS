"""
tools/annual_report_analysis.py — Annual Report Analysis UI

UI Layer only. No analysis logic here.

Extensibility points (search for TODO):
  - ACTION: Wire "Analyze" button to CallTool("run_ar_analysis", url=...)
  - ACTION: Wire Tab 2 (YoY) to CallTool("run_yoy_comparison", ...)
  - ACTION: Wire Tab 3 (P2P) to CallTool("run_peer_comparison", ...)
  - CONTENT: Add form fields to Tab 2 and Tab 3 when backend is ready
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastmcp import FastMCP
from prefab_ui.app import PrefabApp
from prefab_ui.components import (
    Column, Row, Card, CardContent,
    Heading, Text, Muted, Button, Input, Select, SelectOption,
    Tabs, Tab,
)

from theme import REACT_LOOP_THEME


def annual_report_analysis() -> PrefabApp:
    """
    Annual Report Analysis — Analyse annual reports via URL, compare YoY, or run peer comparisons.
    Opens the Annual Report Analysis tool.
    """
    with PrefabApp(
        title="Annual Report Analysis",
        theme=REACT_LOOP_THEME,
        css_class="p-6",
    ) as app:
        with Card(css_class="mx-4 my-2"):
            with CardContent(css_class="p-8"):
                with Column(gap=6):
                    Heading("Annual Report Analysis Tool", level=2)

                    # ── TABS ────────────────────────────────────────────────
                    # Tabs(value=...) sets the initially active tab.
                    # Tab("Title", value="id") — positional title is required.
                    # variant="line" gives the orange-underline style.
                    with Tabs(
                        value="AR Analysis",
                        variant="line",
                    ):

                        # TAB 1 — AR Analysis
                        with Tab("AR Analysis"):
                            with Column(gap=4, css_class="mt-4"):
                                Text("Please paste a public link to the company's annual report.")
                                Muted(
                                    "e.g., https://www.bseindia.com/annual-report-2023.pdf",
                                    italic=True,
                                )
                                with Row(gap=2):
                                    Input(
                                        name="ar_url",
                                        placeholder="e.g. https://www.bseindia.com/annual-report-2023.pdf",
                                        css_class="flex-1",
                                        # TODO ACTION: on_change=SetState("ar_url", "{{ $event }}")
                                    )
                                    Button("Analyze", icon="search", variant="default")

                        # TAB 2 — YoY AR Comparison
                        with Tab("YoY AR Comparison"):
                            with Column(gap=4, css_class="mt-4"):
                                Text("Compare annual reports for the same company across two financial years.")
                                with Row(gap=3):
                                    with Column(gap=1, css_class="flex-1"):
                                        Text("Company", css_class="text-sm font-medium")
                                        with Select(name="yoy_company", placeholder="Select company"):
                                            SelectOption("HDFC Bank", value="hdfc_bank")
                                            SelectOption("ICICI Bank", value="icici_bank")
                                            SelectOption("Infosys", value="infosys")
                                            SelectOption("Reliance Industries", value="reliance")
                                            SelectOption("TCS", value="tcs")
                                    with Column(gap=1, css_class="flex-1"):
                                        Text("Year 1", css_class="text-sm font-medium")
                                        Input(name="yoy_year1", placeholder="e.g. FY2023")
                                    with Column(gap=1, css_class="flex-1"):
                                        Text("Year 2", css_class="text-sm font-medium")
                                        Input(name="yoy_year2", placeholder="e.g. FY2024")
                                Button("Compare", icon="bar-chart-2", variant="default", css_class="w-fit")

                        # TAB 3 — Peer To Peer AR Comparison
                        with Tab("Peer To Peer AR Comparison"):
                            with Column(gap=4, css_class="mt-4"):
                                Text("Compare annual reports across multiple companies for the same financial year.")
                                with Row(gap=3):
                                    with Column(gap=1, css_class="flex-1"):
                                        Text("Company A", css_class="text-sm font-medium")
                                        with Select(name="p2p_company_a", placeholder="Select company"):
                                            SelectOption("HDFC Bank", value="hdfc_bank")
                                            SelectOption("ICICI Bank", value="icici_bank")
                                            SelectOption("Kotak Mahindra Bank", value="kotak")
                                            SelectOption("Bajaj Finance", value="bajaj_finance")
                                    with Column(gap=1, css_class="flex-1"):
                                        Text("Company B", css_class="text-sm font-medium")
                                        with Select(name="p2p_company_b", placeholder="Select company"):
                                            SelectOption("HDFC Bank", value="hdfc_bank")
                                            SelectOption("ICICI Bank", value="icici_bank")
                                            SelectOption("Kotak Mahindra Bank", value="kotak")
                                            SelectOption("Bajaj Finance", value="bajaj_finance")
                                    with Column(gap=1, css_class="flex-1"):
                                        Text("Financial Year", css_class="text-sm font-medium")
                                        Input(name="p2p_year", placeholder="e.g. FY2024")
                                Button("Compare Peers", icon="users", variant="default", css_class="w-fit")

    return app


# Alias for route_query to call
build_ui = annual_report_analysis


def register(mcp: FastMCP):
    """Registers annual_report_analysis as an MCP tool."""
    mcp.tool(app=True)(annual_report_analysis)


app = build_ui()
