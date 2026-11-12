"""
tools/report_chatbot.py — Report ChatBot UI

UI Layer: Prefab component tree. Do not add logic here.

Extensibility points (search for TODO):
  - DATA: Replace config.COMPANIES with real DB query
  - DATA: Replace config.COMPANY_DOCUMENTS with real DB query
  - ACTION: Wire Combobox on_change to filter document dropdowns
  - ACTION: Wire DropZone on_change to file processing backend
  - ACTION: Wire a submit button to CallTool("report_chatbot_query")
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastmcp import FastMCP
from prefab_ui.app import PrefabApp
from prefab_ui.components import (
    Column, Row, Card, CardHeader, CardContent, CardTitle,
    Heading, Muted, Separator,
    Combobox, ComboboxOption,
    Select, SelectOption,
    DropZone,
)

import config
from theme import REACT_LOOP_THEME


def report_chatbot() -> PrefabApp:
    """
    Report ChatBot — Search company documents and upload PDFs for analysis.
    Opens the Report ChatBot interface.
    """
    with PrefabApp(
        title="Report ChatBot",
        theme=REACT_LOOP_THEME,
        css_class="p-6",
    ) as app:
        with Column(gap=6):

            # ── SELECT COMPANY ───────────────────────────────────────────────
            Heading("Select Company", level=4)

            # TODO DATA: Replace with real company list from DB
            # config.COMPANIES is [] until DB is wired
            with Combobox(
                placeholder="Search for a company...",
                name="selected_company",
                # TODO ACTION: on_change=CallTool("get_company_documents", ...)
            ):
                for company in config.COMPANIES:
                    ComboboxOption(company["label"], value=company["value"])

            Separator()

            # ── SELECT DOCUMENTS ─────────────────────────────────────────────
            with Row(gap=2, align="center"):
                Heading("Select Documents", level=4)
                Muted("(Optional if files uploaded)")

            with Row(gap=4):
                # Use HDFC Bank as the default stub company for demo
                _stub_docs = config.COMPANY_DOCUMENTS.get("hdfc_bank", {})
                for doc_type, label in [
                    ("annual_report",         "Annual Report"),
                    ("concall",               "Concall"),
                    ("investor_presentation", "Investor Presentation"),
                ]:
                    _options = _stub_docs.get(doc_type, [])
                    with Card(css_class="flex-1"):
                        with CardHeader():
                            with Row(css_class="justify-between", align="center"):
                                CardTitle(label)
                                Muted(f"{len(_options)} options")
                        with CardContent():
                            with Select(
                                name=f"selected_{doc_type}",
                                placeholder="Select a document",
                            ):
                                for doc in _options:
                                    SelectOption(doc["label"], value=doc["value"])

            Separator()

            # ── UPLOAD DOCUMENTS ─────────────────────────────────────────────
            with Row(gap=2, align="center"):
                Heading("Upload Documents", level=4)
                Muted("(File should be PDF and maximum size should be less than 30MB)")

            # TODO ACTION: on_change=CallTool("process_uploaded_document", ...)
            # max_size is in bytes: 50 MB = 50 * 1024 * 1024
            DropZone(
                accept=".pdf",
                max_size=50 * 1024 * 1024,
                label="Drag and drop files here or browse files",
                description="Maximum 1 file, 50 MB Max Size",
                icon="upload-cloud",
            )

    return app


# Alias for route_query to call
build_ui = report_chatbot


def register(mcp: FastMCP):
    """Registers report_chatbot as an MCP tool."""
    mcp.tool(app=True)(report_chatbot)


app = build_ui()
