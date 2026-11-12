# `credit_note_eval`  ·  group: `finance`

2 registered MCP tool(s). Everything for this tool lives in this folder.

### `generate_credit_note(annual_report_uri: str, rationale_uris: list[str]) -> dict[str, str]`

Generate a complete 10-section internal credit note. Sections: Company Profile, Credit
Rating, ESG Profile, Business Profile, Key Risks & Mitigants, Capital, Asset Quality,
Earnings, Management, Liquidity. annual_report_uri: `uri` returned by
upload_file_to_gemini for the annual report PDF. rationale_uris: list of `uri` values
returned by upload_file_to_gemini for rating rationale PDFs. Returns a dict mapping
section name to generated text. All 10 sections are generated concurrently.

### `generate_credit_section(section_name: str, annual_report_uri: str, rationale_uris: list[str]) -> str`

Generate one section of a credit note.

**Files:** `logic.py`, `__init__.py` (registration).
