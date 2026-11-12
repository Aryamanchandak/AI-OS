# Claude Code Execution Plan — AI Agents MCP Server with Prefab UI

## What You Are Building

A single FastMCP server that:
1. Exposes one user-facing tool: `route_query` — takes natural language input, uses Gemini to classify which of 5 systems the user wants, then returns the corresponding Prefab UI
2. Exposes 5 UI tools (one per system), each returning a static `PrefabApp` that exactly mirrors the real application UI
3. Is structured so backends, real data, and interactivity can be wired in later without touching UI code

The 5 systems are:
- **Report ChatBot** — company search + document dropdowns + file upload
- **Meeting Recorder** — audio recorder with control buttons
- **Podcast Agent** — sector table with audio players per row
- **US Result Note** — Morningstar PDF uploader
- **Annual Report Analysis** — 3-tab layout with URL input and analyze button

---

## Before Writing Any Code — Mandatory Doc Reads

Before writing a single line, fetch and read these Prefab documentation pages in order.
Do not skip any. Do not guess at component APIs.

```
fetch https://prefab.prefect.io/docs/getting-started/installation
fetch https://prefab.prefect.io/docs/getting-started/quickstart
fetch https://prefab.prefect.io/docs/concepts/core-concepts
fetch https://prefab.prefect.io/docs/concepts/components
fetch https://prefab.prefect.io/docs/concepts/state
fetch https://prefab.prefect.io/docs/concepts/actions
fetch https://prefab.prefect.io/docs/running/fastmcp
fetch https://prefab.prefect.io/docs/reference/app
fetch https://prefab.prefect.io/docs/components/tabs
fetch https://prefab.prefect.io/docs/components/card
fetch https://prefab.prefect.io/docs/components/combobox
fetch https://prefab.prefect.io/docs/components/select
fetch https://prefab.prefect.io/docs/components/drop-zone
fetch https://prefab.prefect.io/docs/components/audio
fetch https://prefab.prefect.io/docs/components/button
fetch https://prefab.prefect.io/docs/components/data-table
fetch https://prefab.prefect.io/docs/components/input
fetch https://prefab.prefect.io/docs/components/typography
fetch https://prefab.prefect.io/docs/components/row
fetch https://prefab.prefect.io/docs/components/column
fetch https://prefab.prefect.io/docs/components/grid
fetch https://prefab.prefect.io/docs/components/badge
fetch https://prefab.prefect.io/docs/components/separator
fetch https://prefab.prefect.io/docs/styling/themes
fetch https://prefab.prefect.io/docs/styling/css
```

After reading all docs, proceed with implementation in the exact file order specified below.

---

## Project Structure to Create

```
ai_agents_mcp/
├── requirements.txt
├── config.py
├── server.py
└── tools/
    ├── __init__.py
    ├── report_chatbot.py
    ├── meeting_recorder.py
    ├── podcast_agent.py
    ├── us_result_note.py
    └── annual_report_analysis.py
```

Create the `ai_agents_mcp/` directory and `tools/` subdirectory first.

---

## File 1: `requirements.txt`

```
fastmcp[apps]
prefab-ui==0.15.0
google-genai
python-dotenv
```

Pin `prefab-ui` explicitly. The `fastmcp[apps]` extra pulls in `prefab-ui` but with no upper bound — pinning prevents breaking changes.

---

## File 2: `config.py`

This is the single source of truth for all data. Every piece of data in every tool comes from here.
When a real database is wired later, only this file changes.

```python
"""
config.py — Central data configuration for all AI Agent tools.

When wiring real backends:
- Replace placeholder lists with DB queries or API calls
- Keep the variable names identical — tools import directly from here
- Add connection setup (DB clients, API keys) at the bottom of this file
"""

# ── SYSTEM ROUTING ──────────────────────────────────────────────────────────
# Used by Gemini to understand what each system does.
# Keys must exactly match the tool function names in server.py.

SYSTEM_DESCRIPTIONS = {
    "report_chatbot": (
        "Analyses company documents including annual reports, concall transcripts, "
        "and investor presentations. User wants to ask questions about a specific "
        "company's financial documents, upload PDFs, or chat with a report."
    ),
    "meeting_recorder": (
        "Records, transcribes, and analyses meeting audio. User wants to record "
        "a meeting, upload a recording, view past recordings, or get a meeting summary."
    ),
    "podcast_agent": (
        "Generates and plays sector-wise financial podcasts. User wants to listen "
        "to a podcast about a market sector like Auto, Pharma, FMCG, Banking, etc."
    ),
    "us_result_note": (
        "Analyses US company earnings results from Morningstar PDF reports. User "
        "wants to upload Morningstar PDFs and generate result notes for US stocks."
    ),
    "annual_report_analysis": (
        "Deep analysis of company annual reports via URL. User wants to analyse "
        "an annual report, compare reports year-on-year, or do peer-to-peer "
        "comparison of annual reports across companies."
    ),
}

# Ordered list of valid system keys — used to validate Gemini's response
VALID_SYSTEMS = list(SYSTEM_DESCRIPTIONS.keys())

# ── REPORT CHATBOT DATA ──────────────────────────────────────────────────────
# TODO: Replace with DB query — SELECT company_name, company_id FROM companies

COMPANIES: list[dict] = [
    # {"label": "Reliance Industries", "value": "RIL"},
    # {"label": "HDFC Bank", "value": "HDFCBANK"},
]

# TODO: Replace with DB query — SELECT doc_type, doc_id, label FROM documents WHERE company_id = ?
# Structure per company: { "company_value": { "doc_type": [{"label": ..., "value": ...}] } }
COMPANY_DOCUMENTS: dict = {
    # "RIL": {
    #     "annual_report": [{"label": "Annual Report 2024", "value": "ar_ril_2024"}],
    #     "concall": [{"label": "Q3 FY24 Concall", "value": "cc_ril_q3_24"}],
    #     "investor_presentation": [],
    # }
}

# ── PODCAST AGENT DATA ───────────────────────────────────────────────────────
# TODO: Replace with DB query — SELECT sector_name, audio_url FROM sector_podcasts

SECTORS: list[dict] = [
    {"sector": "Auto",              "audio_url": ""},
    {"sector": "Bank and Finance",  "audio_url": ""},
    {"sector": "FMCG",              "audio_url": ""},
    {"sector": "Metals and Mining", "audio_url": ""},
    {"sector": "Oil and Gas",       "audio_url": ""},
    {"sector": "Pharma",            "audio_url": ""},
    {"sector": "Software",          "audio_url": ""},
]

# ── GEMINI CONFIG ────────────────────────────────────────────────────────────
GEMINI_MODEL = "gemini-2.0-flash"

ROUTER_SYSTEM_PROMPT = """You are a routing assistant for an AI agents platform.
Your only job is to read the user's query and return exactly one system key from the list provided.
Return ONLY the key string. No explanation. No punctuation. No other text.
If you are unsure, return the closest match. Never return anything not in the list."""
```

---

## File 3: `tools/__init__.py`

Empty file. Just create it so `tools/` is a Python package.

```python
```

---

## File 4: `tools/report_chatbot.py`

### What the UI looks like (from screenshot)
- Warm peach/cream background (`#FFF3E0` or similar)
- Section: "Select Company" — a searchable combobox with a teal "C" avatar icon
- Section: "Select Documents (Optional if files uploaded)" — 3 side-by-side cards:
  - Annual Report — shows "0 options", dropdown says "Select company first"
  - Concall — same
  - Investor Presentation — same
- Section: "Upload Documents (File should be PDF and maximum size should be less than 30MB)"
  - Large drag-and-drop zone with upload icon, "Drag and drop files here or browse files", "Maximum 1 file, 50 MB Max Size"

### Component mapping (verify exact prop names against docs before writing)
- Outer: `PrefabApp` with `css_class="p-6"` and background color
- `Column` with `gap=6`
- Company search: `Combobox` with options from `config.COMPANIES` (empty list for now)
- Documents row: `Row` of 3 `Card` components, each containing a `Select` with `disabled=True`
- Upload: `DropZone` component

### Code pattern to follow

```python
"""
tools/report_chatbot.py — Report ChatBot UI

UI Layer: Prefab component tree. Do not add logic here.

Extensibility points (search for TODO):
  - DATA: Replace config.COMPANIES with real DB query
  - DATA: Replace config.COMPANY_DOCUMENTS with real DB query  
  - ACTION: Wire Combobox on_change to filter document dropdowns
  - ACTION: Wire DropZone on_upload to file processing backend
  - ACTION: Wire a submit button to CallTool("report_chatbot_query")
"""

from fastmcp import FastMCP
from prefab_ui.app import PrefabApp
# Import all required components — check exact names against docs
from prefab_ui.components import (
    Column, Row, Card, CardHeader, CardContent, CardTitle,
    Heading, Text, Muted, Separator,
    Combobox, ComboboxOption, Select, SelectOption,
)
from prefab_ui.components import DropZone  # verify import path from docs

import config

def register(mcp: FastMCP):
    @mcp.tool(app=True)
    def report_chatbot() -> PrefabApp:
        """
        Report ChatBot — Search company documents and upload PDFs for analysis.
        Opens the Report ChatBot interface.
        """
        with PrefabApp(
            title="Report ChatBot",
            css_class="p-6 min-h-screen",
            # TODO: Match exact background color from screenshot (#FFF3E0 or closest Tailwind)
        ) as app:
            with Column(gap=6):

                # ── SELECT COMPANY ───────────────────────────────────────
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

                # ── SELECT DOCUMENTS ─────────────────────────────────────
                with Row(gap=2, align="center"):
                    Heading("Select Documents", level=4)
                    Muted("(Optional if files uploaded)")

                with Row(gap=4):
                    for doc_type, label in [
                        ("annual_report",          "Annual Report"),
                        ("concall",                "Concall"),
                        ("investor_presentation",  "Investor Presentation"),
                    ]:
                        with Card(css_class="flex-1"):
                            with CardHeader():
                                with Row(css_class="justify-between", align="center"):
                                    CardTitle(label)
                                    Muted("0 options")  # TODO: Replace with dynamic count
                            with CardContent():
                                # TODO ACTION: Enable and populate when company is selected
                                # TODO DATA: Options from config.COMPANY_DOCUMENTS[selected_company][doc_type]
                                with Select(
                                    name=f"selected_{doc_type}",
                                    disabled=True,
                                    placeholder="Select company first",
                                ):
                                    pass  # TODO: Populate with SelectOption per document

                Separator()

                # ── UPLOAD DOCUMENTS ─────────────────────────────────────
                with Row(gap=2, align="center"):
                    Heading("Upload Documents", level=4)
                    Muted("(File should be PDF and maximum size should be less than 30MB)")

                # TODO ACTION: on_upload=CallTool("process_uploaded_document", ...)
                # Verify DropZone props against: https://prefab.prefect.io/docs/components/drop-zone
                DropZone(
                    accept=".pdf",
                    max_size_mb=50,
                    label="Drag and drop files here or browse files",
                    hint="Maximum 1 file, 50 MB Max Size",
                    # TODO: wire on_upload action
                )

        return app
```

**Important:** Before writing the final code, verify:
- Exact `DropZone` import path and prop names from `https://prefab.prefect.io/docs/components/drop-zone`
- Exact `Select`/`SelectOption` import path from `https://prefab.prefect.io/docs/components/select`
- Exact `Combobox`/`ComboboxOption` import path from `https://prefab.prefect.io/docs/components/combobox`
- Background color: use `css_class` with Tailwind (`bg-orange-50`) or inline style — check `https://prefab.prefect.io/docs/styling/css`

---

## File 5: `tools/meeting_recorder.py`

### What the UI looks like (from screenshot)
- Light blue/grey background
- Centered `Card` taking ~60% width
- `Heading` "Audio Recorder" centered
- Status text "Not Recording" in green, centered
- Row 1 of buttons: "Start Recording" (blue), pause icon button (yellow/amber), "Stop Recording" (red)
- Row 2 of buttons: "Submit Recording" (green), "Clear Recording" (teal/cyan)
- Top right of page (outside card): two orange buttons "Upload Recording" and "View Recording List"

### Component mapping
- Outer `Column` with full-height, centered alignment
- Top-right `Row` for the two orange action buttons
- `Card` centered with `css_class="mx-auto w-2/3"`
- Inside card: `Column` centered, `Heading`, status `Text`, two `Row`s of `Button`s

### Code pattern to follow

```python
"""
tools/meeting_recorder.py — Meeting Recorder UI

UI Layer only. No recording logic here.

Extensibility points (search for TODO):
  - ACTION: Wire "Start Recording" button to browser recording API via CallHandler or JS
  - ACTION: Wire "Stop Recording" to stop stream
  - ACTION: Wire "Submit Recording" to CallTool("transcribe_and_analyse_recording")
  - ACTION: Wire "Upload Recording" button to DropZone or file picker
  - ACTION: Wire "View Recording List" to CallTool("list_recordings")
  - STATE: Replace hardcoded "Not Recording" with reactive state variable
"""

from fastmcp import FastMCP
from prefab_ui.app import PrefabApp
from prefab_ui.components import (
    Column, Row, Card, CardContent,
    Heading, Text, Button, Icon,
)

def register(mcp: FastMCP):
    @mcp.tool(app=True)
    def meeting_recorder() -> PrefabApp:
        """
        Meeting Recorder — Record, upload, and analyse meeting audio.
        Opens the Meeting Recorder interface.
        """
        with PrefabApp(
            title="Meeting Recorder",
            css_class="p-6 min-h-screen bg-slate-100",
        ) as app:
            with Column(gap=4):

                # ── TOP RIGHT ACTION BUTTONS ──────────────────────────────
                # TODO ACTION: on_click=OpenFilePicker() for Upload Recording
                # TODO ACTION: on_click=CallTool("list_recordings") for View Recording List
                with Row(css_class="justify-end", gap=2):
                    Button(
                        "Upload Recording",
                        variant="default",
                        css_class="bg-orange-500 hover:bg-orange-600 text-white",
                        disabled=True,  # TODO: enable when backend ready
                    )
                    Button(
                        "View Recording List",
                        variant="default",
                        css_class="bg-red-500 hover:bg-red-600 text-white",
                        disabled=True,  # TODO: enable when backend ready
                    )

                # ── RECORDER CARD ─────────────────────────────────────────
                with Card(css_class="mx-auto w-2/3 text-center"):
                    with CardContent(css_class="flex flex-col items-center gap-6 py-10"):
                        Heading("Audio Recorder", level=3)

                        # TODO STATE: Replace with Rx("recording_status")
                        # Possible values: "Not Recording", "Recording...", "Paused"
                        Text("Not Recording", css_class="text-green-500 font-medium")

                        # ── RECORDING CONTROLS ────────────────────────────
                        # TODO ACTION: Wire each button's on_click
                        with Row(gap=3, css_class="justify-center"):
                            Button(
                                "Start Recording",
                                css_class="bg-blue-500 hover:bg-blue-600 text-white",
                                disabled=True,  # TODO
                            )
                            # Pause icon button — square amber button with pause icon
                            Button(
                                "",  # icon only
                                css_class="bg-amber-400 hover:bg-amber-500 text-white w-12 h-12",
                                disabled=True,  # TODO
                            )
                            # NOTE: Check if Icon component can be nested inside Button
                            # from docs: https://prefab.prefect.io/docs/components/button
                            Button(
                                "Stop Recording",
                                css_class="bg-red-500 hover:bg-red-600 text-white",
                                disabled=True,  # TODO
                            )

                        # ── SUBMIT / CLEAR ────────────────────────────────
                        with Row(gap=3, css_class="justify-center"):
                            Button(
                                "Submit Recording",
                                css_class="bg-green-500 hover:bg-green-600 text-white",
                                disabled=True,  # TODO
                            )
                            Button(
                                "Clear Recording",
                                css_class="bg-teal-500 hover:bg-teal-600 text-white",
                                disabled=True,  # TODO
                            )

        return app
```

**Important:** Before writing final code, verify:
- How to embed an icon inside a `Button` — check `https://prefab.prefect.io/docs/components/button` and `https://prefab.prefect.io/docs/components/icon`
- Tailwind color classes available — check `https://prefab.prefect.io/docs/styling/css`

---

## File 6: `tools/podcast_agent.py`

### What the UI looks like (from screenshot)
- White/light background
- Full-width table with two columns: "SECTOR" and "PODCAST"
- Header row has an orange/peach background
- 7 data rows: Auto, Bank and Finance, FMCG, Metals and Mining, Oil and Gas, Pharma, Software
- Each row in SECTOR column has a small orange speaker icon before the name
- Each row in PODCAST column has: play button (▶), "0:00", a progress scrubber bar, and a volume icon
- This is a native audio player per row

### Component mapping
- `DataTable` with custom columns, OR a manual `Table` with `Audio` component per cell
- Check docs: `DataTable` may not support embedding components in cells — if not, use manual `Table` rows with `Row` + `Audio` components
- Fetch `https://prefab.prefect.io/docs/components/audio` to understand `Audio` component props
- Fetch `https://prefab.prefect.io/docs/components/data-table` to check if component embedding in cells is supported
- If DataTable doesn't support it, use `https://prefab.prefect.io/docs/components/table` (manual table)

### Code pattern to follow

```python
"""
tools/podcast_agent.py — Podcast Agent UI

UI Layer only. No audio generation here.

Extensibility points (search for TODO):
  - DATA: Replace config.SECTORS audio_url="" with real CDN URLs from DB
  - ACTION: Podcasts auto-play when audio_url is populated
  - FEATURE: Add "Generate Podcast" button per sector to trigger backend
"""

from fastmcp import FastMCP
from prefab_ui.app import PrefabApp
from prefab_ui.components import (
    Column, Row,
    Heading, Text, Muted,
)
# TODO: Import Audio, Table components — verify exact import paths from docs
# from prefab_ui.components import Audio
# from prefab_ui.components import Table, TableHeader, TableRow, TableCell, TableHead, TableBody

import config

def register(mcp: FastMCP):
    @mcp.tool(app=True)
    def podcast_agent() -> PrefabApp:
        """
        Podcast Agent — Listen to AI-generated sector-wise financial podcasts.
        Opens the Podcast interface with audio players per sector.
        """
        with PrefabApp(
            title="Podcast Agent",
            css_class="p-6",
        ) as app:
            with Column(gap=4):

                # ── SECTOR PODCAST TABLE ──────────────────────────────────
                # NOTE: If DataTable supports component cells, use DataTable.
                # If not, build manually with Table components.
                # Decision: Read both doc pages before implementing.
                #
                # Option A — DataTable (preferred if component cells supported):
                # DataTable(
                #     columns=[
                #         DataTableColumn(key="sector", header="SECTOR"),
                #         DataTableColumn(key="podcast", header="PODCAST"),  # needs Audio component
                #     ],
                #     rows=[...],
                #     css_class="...",  # orange header
                # )
                #
                # Option B — Manual Table:
                # with Table():
                #     with TableHeader(css_class="bg-orange-200"):
                #         with TableRow():
                #             TableHead("SECTOR")
                #             TableHead("PODCAST")
                #     with TableBody():
                #         for sector_data in config.SECTORS:
                #             with TableRow():
                #                 with TableCell():
                #                     Row([Icon("volume-2", css_class="text-orange-400"), Text(sector_data["sector"])])
                #                 with TableCell():
                #                     Audio(src=sector_data["audio_url"], controls=True)
                #
                # TODO: Implement once doc pages are read

                Text("Podcast table — implement after reading Audio and Table docs")
                # Placeholder until final implementation

        return app
```

**Critical doc reads for this file:**
- `https://prefab.prefect.io/docs/components/audio` — understand `src`, `controls` props
- `https://prefab.prefect.io/docs/components/data-table` — check if cells support components
- `https://prefab.prefect.io/docs/components/table` — fallback manual table API

---

## File 7: `tools/us_result_note.py`

### What the UI looks like (from screenshot)
- Light blue/grey background
- Single centered `Card`, roughly half-page width
- `Heading` "Upload Morningstar PDFs" centered
- Row: "Choose Files" button (blue outlined) + "No file chosen" text
- Constraint text: "You can upload up to 2 PDF files. Each must be under 5 MB."
- Bottom right: "Upload" button (salmon/orange-pink color, disabled-looking)

### Component mapping
- `Card` centered with `css_class="mx-auto max-w-xl"`
- `Heading`, file row, constraint `Muted` text, upload `Button`
- File input: check if Prefab has a file input component other than DropZone — check `https://prefab.prefect.io/docs/actions/open-file-picker`

```python
"""
tools/us_result_note.py — US Result Note UI

UI Layer only. No PDF processing here.

Extensibility points (search for TODO):
  - ACTION: Wire "Choose Files" to OpenFilePicker action
  - ACTION: Wire "Upload" button to CallTool("process_morningstar_pdfs")
  - STATE: Show selected filename(s) reactively when files chosen
  - VALIDATION: Enforce 2-file max and 5MB limit in backend tool
"""

from fastmcp import FastMCP
from prefab_ui.app import PrefabApp
from prefab_ui.components import (
    Column, Row, Card, CardContent,
    Heading, Text, Muted, Button,
)

def register(mcp: FastMCP):
    @mcp.tool(app=True)
    def us_result_note() -> PrefabApp:
        """
        US Result Note — Upload Morningstar PDF reports to generate US earnings result notes.
        Opens the US Result Note upload interface.
        """
        with PrefabApp(
            title="US Result Note",
            css_class="p-6 min-h-screen bg-slate-100",
        ) as app:
            with Column(gap=4, css_class="items-center justify-center min-h-screen"):
                with Card(css_class="w-full max-w-xl"):
                    with CardContent(css_class="flex flex-col gap-6 py-8 px-10"):

                        Heading("Upload Morningstar PDFs", level=3, css_class="text-center")

                        # ── FILE CHOOSER ROW ──────────────────────────────
                        # TODO ACTION: Replace Button with OpenFilePicker action
                        # Read: https://prefab.prefect.io/docs/actions/open-file-picker
                        with Row(gap=4, align="center"):
                            Button(
                                "Choose Files",
                                variant="outline",
                                css_class="border-blue-500 text-blue-600",
                                disabled=True,  # TODO: wire OpenFilePicker
                            )
                            # TODO STATE: Replace with Rx("selected_filenames") when files chosen
                            Muted("No file chosen")

                        Muted("You can upload up to 2 PDF files. Each must be under 5 MB.")

                        # ── UPLOAD BUTTON ─────────────────────────────────
                        # TODO ACTION: on_click=CallTool("process_morningstar_pdfs", ...)
                        with Row(css_class="justify-end"):
                            Button(
                                "Upload",
                                css_class="bg-orange-300 hover:bg-orange-400 text-white",
                                disabled=True,  # TODO: enable when files selected
                            )

        return app
```

---

## File 8: `tools/annual_report_analysis.py`

### What the UI looks like (from screenshot)
- Light background
- `Heading` "Annual Report Analysis Tool"
- `Tabs` component with 3 tabs:
  - "AR Analysis" (active, underlined in orange)
  - "YoY AR Comparison"
  - "Peer To Peer AR Comparison"
- Active tab content:
  - Text: "Please paste a public link to the company's annual report."
  - Italic hint: "e.g., https://www.bseindia.com/annual-report-2023.pdf"
  - Wide text `Input` + "Analyze" orange button on the right

```python
"""
tools/annual_report_analysis.py — Annual Report Analysis UI

UI Layer only. No analysis logic here.

Extensibility points (search for TODO):
  - ACTION: Wire "Analyze" button to CallTool("run_ar_analysis", url=...)
  - ACTION: Wire Tab 2 (YoY) to CallTool("run_yoy_comparison", ...)
  - ACTION: Wire Tab 3 (P2P) to CallTool("run_peer_comparison", ...)
  - CONTENT: Add form fields to Tab 2 and Tab 3 when ready
"""

from fastmcp import FastMCP
from prefab_ui.app import PrefabApp
from prefab_ui.components import (
    Column, Row, Card, CardContent,
    Heading, Text, Muted, Button, Input,
)
# TODO: Verify Tabs import path from docs
# from prefab_ui.components import Tabs, Tab

def register(mcp: FastMCP):
    @mcp.tool(app=True)
    def annual_report_analysis() -> PrefabApp:
        """
        Annual Report Analysis — Analyse annual reports via URL, compare YoY, or run peer comparisons.
        Opens the Annual Report Analysis tool.
        """
        with PrefabApp(
            title="Annual Report Analysis",
            css_class="p-6",
        ) as app:
            with Card(css_class="mx-4 my-2"):
                with CardContent(css_class="p-8"):
                    with Column(gap=6):
                        Heading("Annual Report Analysis Tool", level=2)

                        # ── TABS ──────────────────────────────────────────
                        # Verify exact Tabs + Tab API from:
                        # https://prefab.prefect.io/docs/components/tabs
                        with Tabs(default="ar_analysis"):

                            # TAB 1 — AR Analysis
                            with Tab(value="ar_analysis", label="AR Analysis"):
                                with Column(gap=4, css_class="mt-4"):
                                    Text("Please paste a public link to the company's annual report.")
                                    Muted("e.g., https://www.bseindia.com/annual-report-2023.pdf")
                                    with Row(gap=2):
                                        Input(
                                            name="ar_url",
                                            placeholder="e.g. https://www.bseindia.com/annual-report-2023.pdf",
                                            css_class="flex-1",
                                            # TODO ACTION: on_change=SetState("ar_url", "{{ $event }}")
                                        )
                                        Button(
                                            "Analyze",
                                            css_class="bg-orange-500 hover:bg-orange-600 text-white",
                                            disabled=True,  # TODO: enable when backend ready
                                            # TODO ACTION: on_click=CallTool("run_ar_analysis", arguments={"url": "{{ ar_url }}"})
                                        )

                            # TAB 2 — YoY AR Comparison
                            with Tab(value="yoy_comparison", label="YoY AR Comparison"):
                                with Column(gap=4, css_class="mt-4"):
                                    # TODO: Add YoY comparison form fields when backend ready
                                    Muted("Year-on-year comparison form — coming soon.")

                            # TAB 3 — Peer To Peer AR Comparison
                            with Tab(value="peer_comparison", label="Peer To Peer AR Comparison"):
                                with Column(gap=4, css_class="mt-4"):
                                    # TODO: Add peer comparison form fields when backend ready
                                    Muted("Peer-to-peer comparison form — coming soon.")

        return app
```

**Important:** Before writing final code, verify:
- Exact `Tabs` and `Tab` import paths and props from `https://prefab.prefect.io/docs/components/tabs`
- How to set active tab styling (orange underline) — may be handled by `variant` or `css_class`

---

## File 9: `server.py`

This is the entry point. It:
1. Creates the FastMCP server
2. Registers all 5 tool modules
3. Defines the Gemini-powered `route_query` tool

```python
"""
server.py — FastMCP server entry point

Responsibilities:
1. Create the MCP server
2. Register all tool UIs
3. Expose route_query — the single user-facing entry point

The route_query tool uses Gemini to classify user intent and returns
the appropriate Prefab UI. It is the only tool the host model should
present to the user directly.
"""

import os
from dotenv import load_dotenv
from fastmcp import FastMCP
from fastmcp.server.apps import AppConfig
from google import genai

import config

# ── TOOL MODULES ─────────────────────────────────────────────────────────────
from tools import (
    report_chatbot,
    meeting_recorder,
    podcast_agent,
    us_result_note,
    annual_report_analysis,
)

load_dotenv()

# ── SERVER SETUP ─────────────────────────────────────────────────────────────
mcp = FastMCP(
    name="AI Agents MCP",
    instructions=(
        "This server provides access to 5 AI-powered financial analysis tools. "
        "Always use route_query as the entry point — pass the user's raw message to it. "
        "Do not call the individual tool UIs directly."
    ),
)

# ── REGISTER TOOL UIs ─────────────────────────────────────────────────────────
# Each module's register() function attaches its tool to the mcp server.
# Tools are marked app-only (hidden from model's direct tool list) —
# the model should route through route_query, not call UIs directly.

report_chatbot.register(mcp)
meeting_recorder.register(mcp)
podcast_agent.register(mcp)
us_result_note.register(mcp)
annual_report_analysis.register(mcp)

# ── GEMINI CLIENT ─────────────────────────────────────────────────────────────
_gemini_client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

def _classify_intent(user_query: str) -> str:
    """
    Use Gemini to classify the user's query into one of the 5 system keys.
    Returns a key from config.VALID_SYSTEMS.
    Falls back to 'annual_report_analysis' if classification fails.
    """
    system_list = "\n".join(
        f"- {key}: {desc}"
        for key, desc in config.SYSTEM_DESCRIPTIONS.items()
    )

    prompt = (
        f"User query: {user_query}\n\n"
        f"Available systems:\n{system_list}\n\n"
        f"Return ONLY the key of the best matching system. "
        f"Valid keys: {', '.join(config.VALID_SYSTEMS)}"
    )

    response = _gemini_client.models.generate_content(
        model=config.GEMINI_MODEL,
        contents=prompt,
        config={"system_instruction": config.ROUTER_SYSTEM_PROMPT},
    )

    result = response.text.strip().lower().replace('"', "").replace("'", "")

    if result not in config.VALID_SYSTEMS:
        # Graceful fallback — log the bad response for debugging
        print(f"[ROUTER] Gemini returned invalid key: '{result}' — falling back to annual_report_analysis")
        return "annual_report_analysis"

    return result

# ── ROUTE QUERY TOOL ──────────────────────────────────────────────────────────
_TOOL_MAP = {
    "report_chatbot":          report_chatbot,
    "meeting_recorder":        meeting_recorder,
    "podcast_agent":           podcast_agent,
    "us_result_note":          us_result_note,
    "annual_report_analysis":  annual_report_analysis,
}

@mcp.tool(app=True)
def route_query(query: str):
    """
    Main entry point for the AI Agents platform.
    Takes any natural language query, identifies which AI tool the user needs,
    and opens the correct interface.

    Examples:
    - "analyse Reliance's annual report" → opens Annual Report Analysis
    - "I want to record a meeting" → opens Meeting Recorder
    - "play the pharma sector podcast" → opens Podcast Agent
    - "upload a Morningstar report" → opens US Result Note
    - "chat with HDFC's concall documents" → opens Report ChatBot
    """
    system_key = _classify_intent(query)
    print(f"[ROUTER] Query: '{query}' → Routed to: '{system_key}'")

    # Call the tool function directly and return its PrefabApp
    tool_module = _TOOL_MAP[system_key]
    # Each module exposes its tool function — call it to get the PrefabApp
    # Note: The @mcp.tool decorated function is accessible via the module
    # TODO: Verify the correct way to call a registered tool programmatically in FastMCP
    # Alternative: each module also exports a plain function that returns PrefabApp
    # and the @mcp.tool decorator wraps it. Import and call the plain function.
    return tool_module.build_ui()  # See note below


# ── ENTRY POINT ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    mcp.run()
```

### Critical implementation note for server.py

The `route_query` tool needs to call another tool's UI builder. The cleanest pattern is:

Each tool file exposes **two things**:
1. `build_ui()` — a plain Python function that builds and returns the `PrefabApp` (no decorator)
2. `register(mcp)` — wraps `build_ui` with `@mcp.tool(app=True)` and registers it

This way `route_query` can call `tool_module.build_ui()` directly and return the result.

Refactor each tool file to follow this pattern:

```python
# In each tool file — refactor to this structure:

def build_ui() -> PrefabApp:
    """Plain function — builds and returns the PrefabApp. No MCP decorator."""
    with PrefabApp(...) as app:
        # ... component tree ...
    return app

def register(mcp: FastMCP):
    """Registers build_ui as an MCP tool."""
    # Mark as app-only so model doesn't call individual UIs directly
    mcp.tool(app=AppConfig(visibility=["app"]))(build_ui)
```

Apply this refactor to ALL 5 tool files.

---

## File 10: `.env` (create template, do not fill values)

```
GEMINI_API_KEY=your_key_here
```

---

## Validation Steps After All Files Are Written

Run these checks in order:

### 1. Installation check
```bash
cd ai_agents_mcp
pip install -r requirements.txt
```

### 2. Import check (no MCP server running yet)
```bash
python -c "
import config
import tools.report_chatbot as rc
import tools.meeting_recorder as mr
import tools.podcast_agent as pa
import tools.us_result_note as us
import tools.annual_report_analysis as ar
print('All imports OK')
print('Valid systems:', config.VALID_SYSTEMS)
"
```

### 3. UI build check (verify each PrefabApp builds without error)
```bash
python -c "
from tools.report_chatbot import build_ui
app = build_ui()
print('report_chatbot UI OK:', type(app))

from tools.meeting_recorder import build_ui
app = build_ui()
print('meeting_recorder UI OK:', type(app))

from tools.podcast_agent import build_ui
app = build_ui()
print('podcast_agent UI OK:', type(app))

from tools.us_result_note import build_ui
app = build_ui()
print('us_result_note UI OK:', type(app))

from tools.annual_report_analysis import build_ui
app = build_ui()
print('annual_report_analysis UI OK:', type(app))
"
```

### 4. Prefab local preview (visual check of each UI)
```bash
# Install prefab CLI if not already available
pip install prefab-ui

# Preview each tool individually
prefab serve tools/report_chatbot.py
prefab serve tools/meeting_recorder.py
prefab serve tools/podcast_agent.py
prefab serve tools/us_result_note.py
prefab serve tools/annual_report_analysis.py
```

For each preview: visually compare against the screenshots. Check layout, colors, spacing, component presence.

### 5. Router classification check (requires GEMINI_API_KEY in .env)
```bash
python -c "
from dotenv import load_dotenv
load_dotenv()
import server

test_queries = [
    ('analyse Reliance annual report', 'annual_report_analysis'),
    ('record a meeting', 'meeting_recorder'),
    ('pharma podcast', 'podcast_agent'),
    ('upload morningstar report', 'us_result_note'),
    ('chat with HDFC concall', 'report_chatbot'),
]

for query, expected in test_queries:
    result = server._classify_intent(query)
    status = 'PASS' if result == expected else 'FAIL'
    print(f'[{status}] \"{query}\" → {result} (expected: {expected})')
"
```

### 6. Full server run check
```bash
python server.py
```

Should start without errors. In Claude Desktop, the `route_query` tool should appear.

---

## Common Errors to Watch For

| Error | Cause | Fix |
|-------|-------|-----|
| `ImportError: cannot import name 'DropZone'` | Wrong import path | Read the doc page for that component, use exact import |
| `TypeError: unexpected keyword argument` | Wrong prop name | Read component doc page, use exact prop names |
| `PrefabApp returned None` | Missing `return app` | Ensure `build_ui()` returns the app object |
| Gemini returns invalid key | Prompt too loose | Check `ROUTER_SYSTEM_PROMPT` in config.py, make it stricter |
| `prefab serve` shows blank screen | Component API mismatch | Read doc for the failing component, fix props |

---

## What Is Explicitly Out of Scope

Do not implement any of the following in this phase:

- Any actual backend logic for any of the 5 systems
- Real database connections or queries
- File upload processing
- Audio recording or transcription
- PDF parsing or analysis
- Authentication or user sessions
- `CallTool` wiring on any button
- Reactive state that changes based on user interaction

Every `disabled=True` button and every `# TODO ACTION` comment is intentional. This is the scaffold. The backend slots in later.

---

## Extensibility Reference — How to Add a Backend Later

When ready to wire a backend for any tool, the pattern is always:

**Step 1 — Add a backend tool (no `app=True`):**
```python
@mcp.tool  # NOT app=True — this is logic, not UI
def run_ar_analysis(url: str) -> str:
    # actual analysis logic here
    result = call_gemini_with_document(url)
    return result
```

**Step 2 — Wire the button in `build_ui()`:**
```python
# Change this:
Button("Analyze", disabled=True)

# To this:
Button(
    "Analyze",
    on_click=CallTool(
        "run_ar_analysis",
        arguments={"url": "{{ ar_url }}"},
        on_success=SetState("analysis_result", RESULT),
    )
)
```

**Step 3 — Add a `Slot` to display the result:**
```python
Slot("analysis_result")
```

**Step 4 — Update `config.py` data sources if needed.**

The UI component tree in `build_ui()` never changes structurally. You only add actions and slots.