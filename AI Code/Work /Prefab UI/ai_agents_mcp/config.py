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
    {"label": "HDFC Bank", "value": "hdfc_bank"},
    {"label": "ICICI Bank", "value": "icici_bank"},
    {"label": "Infosys", "value": "infosys"},
    {"label": "Reliance Industries", "value": "reliance"},
    {"label": "TCS", "value": "tcs"},
    {"label": "Wipro", "value": "wipro"},
    {"label": "Bajaj Finance", "value": "bajaj_finance"},
    {"label": "Kotak Mahindra Bank", "value": "kotak"},
]

# TODO: Replace with DB query — SELECT doc_type, doc_id, label FROM documents WHERE company_id = ?
COMPANY_DOCUMENTS: dict = {
    "hdfc_bank": {
        "annual_report":         [{"label": "Annual Report 2023-24", "value": "ar_hdfc_2024"}, {"label": "Annual Report 2022-23", "value": "ar_hdfc_2023"}],
        "concall":               [{"label": "Q4 FY24 Earnings Call", "value": "cc_hdfc_q4_24"}, {"label": "Q3 FY24 Earnings Call", "value": "cc_hdfc_q3_24"}],
        "investor_presentation": [{"label": "Investor Day 2024", "value": "ip_hdfc_2024"}],
    },
    "icici_bank": {
        "annual_report":         [{"label": "Annual Report 2023-24", "value": "ar_icici_2024"}],
        "concall":               [{"label": "Q4 FY24 Earnings Call", "value": "cc_icici_q4_24"}, {"label": "Q3 FY24 Earnings Call", "value": "cc_icici_q3_24"}],
        "investor_presentation": [{"label": "Investor Presentation 2024", "value": "ip_icici_2024"}],
    },
    "infosys": {
        "annual_report":         [{"label": "Annual Report 2023-24", "value": "ar_infy_2024"}],
        "concall":               [{"label": "Q4 FY24 Earnings Call", "value": "cc_infy_q4_24"}],
        "investor_presentation": [{"label": "Capital Markets Day 2024", "value": "ip_infy_2024"}],
    },
    "reliance": {
        "annual_report":         [{"label": "Annual Report 2023-24", "value": "ar_ril_2024"}],
        "concall":               [{"label": "Q4 FY24 Earnings Call", "value": "cc_ril_q4_24"}],
        "investor_presentation": [],
    },
    "tcs": {
        "annual_report":         [{"label": "Annual Report 2023-24", "value": "ar_tcs_2024"}],
        "concall":               [{"label": "Q4 FY24 Earnings Call", "value": "cc_tcs_q4_24"}],
        "investor_presentation": [{"label": "Analyst Day 2024", "value": "ip_tcs_2024"}],
    },
    "wipro": {
        "annual_report":         [{"label": "Annual Report 2023-24", "value": "ar_wipro_2024"}],
        "concall":               [{"label": "Q4 FY24 Earnings Call", "value": "cc_wipro_q4_24"}],
        "investor_presentation": [],
    },
    "bajaj_finance": {
        "annual_report":         [{"label": "Annual Report 2023-24", "value": "ar_bjfin_2024"}],
        "concall":               [{"label": "Q4 FY24 Earnings Call", "value": "cc_bjfin_q4_24"}],
        "investor_presentation": [{"label": "Investor Presentation Q4FY24", "value": "ip_bjfin_2024"}],
    },
    "kotak": {
        "annual_report":         [{"label": "Annual Report 2023-24", "value": "ar_kotak_2024"}],
        "concall":               [{"label": "Q4 FY24 Earnings Call", "value": "cc_kotak_q4_24"}],
        "investor_presentation": [],
    },
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
GEMINI_MODEL = "gemini-3-flash-preview"

ROUTER_SYSTEM_PROMPT = """You are a routing assistant for an AI agents platform.
Your only job is to read the user's query and return exactly one system key from the list provided.
Return ONLY the key string. No explanation. No punctuation. No other text.
If you are unsure, return the closest match. Never return anything not in the list."""
