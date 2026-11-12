# `tax/sbi_parser.py`

**Lines:** 190

## Purpose

Parses an SBI bank statement download — a tab-separated file masquerading as an `.xls` — into a list of structured `ParsedRow` dataclass instances. It extracts UPI/NEFT/IMPS reference numbers, counterparty VPAs and names, directions, amounts, and categorises the transaction type (upi, neft, imps, reversal, interest, charges, etc.). Nothing is written to disk or to the database; this is a pure parsing function.

## Entry Point

`parse_sbi_file(path)` — called by `ingest_excel.py`. Can also be run directly (`python sbi_parser.py file.xls`) for a quick count-by-kind summary.

## Data Flow

1. Reads file as TSV using `pandas.read_csv` with `sep="\t"`, skipping the first 19 header rows of account metadata.
2. Strips leading `**` footer rows (statement summary line) and drops rows with no `Txn Date`.
3. For each row: determines debit/credit direction, parses the Description field with three cascading regex patterns (UPI_RE, then NEFT_RE, then IMPS_RE), classifies the transaction kind via keyword matching in `_classify_kind`.
4. Parses the date in two formats: `"%d-%b-%y"` (e.g. `01-Jan-23`) and `"%d %b %Y"` (e.g. `01 Jan 2023`). Rows with neither format are silently skipped.
5. Returns `List[ParsedRow]`.

## Key Regex Patterns

| Pattern | What it matches |
|---|---|
| `UPI_RE` | `UPI/(DR\|CR\|REV)/<ref>[/<n>/<bank>/<vpa>/<narration>]` — the optional group means reversals set name/VPA to None |
| `NEFT_RE` | `NEFT*<IFSC>*<UTR>*<sender name>` — extracts UTR as ref_no, first 4 chars of IFSC as bank |
| `IMPS_RE` | `IMPS[-/]<ref>` — extracts ref only, no counterparty detail |

## Key Functions / Classes

| Name | What it actually does |
|---|---|
| `parse_sbi_file(path)` | Reads TSV, iterates rows, returns list of ParsedRow |
| `_clean_amount(x)` | Converts pandas cell to float, returns None for blank/NaN/comma-formatted numbers |
| `_classify_kind(desc)` | Keyword scan of the description string; returns one of 10 string literals |
| `ParsedRow` | Plain dataclass with 11 fields; `.to_dict()` calls `dataclasses.asdict()` |

## Design Decisions

- The 19-row header skip (`SBI_HEADER_ROWS = 19`) is hardcoded. If SBI changes its export format, ingestion silently breaks.
- When a row has both Debit and Credit populated, Debit wins (`debit if debit is not None else credit`).
- NEFT counterparty bank is derived from the first 4 characters of the IFSC code (IFSC = bank code + branch).
- `confidence=1.0` is set on Excel-ingested rows in `ingest_excel.py`, reflecting the assumption that a bank statement is authoritative.

## Known Gaps / Risks

- If `Debit` and `Credit` columns are both absent from the file, the row is silently dropped with no warning.
- Date parsing tries two formats and skips the row on both failures — no logging. An unusual SBI export variant would produce zero rows silently.
- `on_bad_lines="skip"` in `pd.read_csv` means malformed TSV rows are discarded without any log output.
- Only tested against one real-world statement. UPI narration format variations across banks that send to SBI have not been tested.
- `IMPS_RE` captures only the reference number; no counterparty name or VPA is extracted for IMPS transactions.
