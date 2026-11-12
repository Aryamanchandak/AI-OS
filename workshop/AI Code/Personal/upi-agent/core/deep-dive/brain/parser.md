# parser.py — Technical Documentation

**Last updated:** 2026-05-03
**Lines of code:** 268
**Language:** Python

---

## What This File Does (Plain English)

This file extracts structured payment data from raw UPI SMS text. It is stateless and has no database interaction — it takes a raw SMS string and returns a `ParsedPayment` dataclass with best-effort field extraction. It uses a layered approach: first checks whether the message looks like a UPI transaction at all, then applies a series of independent regex patterns to extract each field. If a field can't be parsed, it is left `None` and the record is still returned. The calling code (`agent.py`) decides what to do with low-confidence results.

---

## How It Actually Works

### Entry Points

- `parse(text, sender_id="")` — the only function most callers need. Returns `Optional[ParsedPayment]`.
- `looks_like_upi(text)` — quick pre-filter, exposed for callers that want to skip the full parse.

### Data Flow

```
parse(text, sender_id)
  → looks_like_upi(text)          # check for UPI/VPA/UPI Ref keywords; return None if absent
  → parse_amount(text)            # AMOUNT_RE → float, fallback to AMOUNT_FALLBACK_RE
  → parse_direction(text)         # DEBIT_RE | CREDIT_RE → 'debit' | 'credit'
  → parse_vpa(text)               # VPA_RE → "something@handle"
  → parse_name(text)              # NAME_RE → "JOHN DOE", fallback AXIS_NAME_RE
  → parse_reference(text)         # REF_RE → 9+ digit string
  → parse_account(text)           # ACCOUNT_RE → 4-digit suffix
  → detect_bank(sender_id, vpa, text)  # sender header → VPA handle → text scan
  → compute confidence: (fields present) / 6
  → if amount is None AND direction is None: return None
  → return ParsedPayment(...)
```

### State Management

None. All regexes are compiled once at module load time (module-level constants). `parse()` is a pure function.

### Key Functions / Classes

| Name | What it actually does |
|---|---|
| `parse(text, sender_id)` | Orchestrates all sub-parsers; returns `ParsedPayment` or `None` |
| `looks_like_upi(text)` | Checks for UPI/VPA keyword presence — fast pre-filter |
| `detect_bank(sender_id, vpa, text)` | Three-tier bank detection: sender header → VPA handle → text keyword scan |
| `parse_amount(text)` | Extracts ₹/Rs./INR amount; falls back to "debited by N" pattern for SBI |
| `parse_direction(text)` | Returns `'debit'` or `'credit'`; debit takes precedence when both keywords appear |
| `parse_vpa(text)` | Extracts first `word@handle` pattern |
| `parse_name(text)` | Extracts counterparty name after "to"/"paid to" keywords; falls back to Axis `UPI/P2A/REF/NAME` format |
| `parse_reference(text)` | Extracts 9+ digit reference number near Ref/UPI/RRN/Txn keywords |
| `parse_account(text)` | Extracts 4-digit account suffix |

### ParsedPayment Dataclass

| Field | Type | Meaning |
|---|---|---|
| `amount` | `Optional[float]` | Transaction amount in INR |
| `direction` | `Optional[str]` | `'debit'` or `'credit'` |
| `bank` | `Optional[str]` | Canonical bank name (HDFC, SBI, etc.) |
| `counterparty_vpa` | `Optional[str]` | UPI VPA of the other party |
| `counterparty_name` | `Optional[str]` | Name of the other party |
| `reference` | `Optional[str]` | UPI reference / RRN number |
| `account_last4` | `Optional[str]` | Last 4 digits of the user's account |
| `confidence` | `float` | Fraction of 6 key fields successfully parsed (0.0–1.0) |
| `raw_text` | `str` | Original SMS text (always set) |
| `sender_id` | `str` | DLT sender header (e.g., "VM-HDFCBK") |

### External Dependencies

- `re`, `dataclasses`, `datetime` (stdlib only)
- No database. No config imports.

### Error Handling

- Individual sub-parsers return `None` on mismatch — they never raise.
- `float(raw)` in `parse_amount` is wrapped in a `try/except ValueError` returning `None`.
- If both `amount` and `direction` are `None` after all parsers run, `parse()` returns `None` — the caller treats this as "not a UPI transaction".
- No other error handling. A malformed regex in a compiled pattern would crash at module import time.

---

## Non-Technical Decisions Embedded in the Code

- Direction detection checks debit before credit explicitly because "many messages mention both 'debited from your account' and 'credited to VPA'". The debit interpretation reflects the user's perspective correctly in those cases.
- `parse_name()` filters out exact strings "VPA", "UPI", "A/C", "ACCOUNT" as false positives, and names shorter than 3 characters. This is a hardcoded list — any other common false positive that the name regex captures will pass through.
- Confidence is computed as `(fields present) / 6` across a fixed set of 6 fields. The counterparty slot uses `vpa or name` — if only a name is present (no VPA), that still counts as one field, not two.
- `BANK_SENDER_MAP` covers 26 DLT sender suffixes. `VPA_BANK_HINTS` covers 12 VPA handle substrings. The last-resort text scan covers 6 bank names. Any bank not in these lists will have `bank = None`.
- The Axis-specific `AXIS_NAME_RE` is a fallback inside `parse_name()`, not a separate function. It handles the `UPI/P2A/REF/NAME` format unique to Axis Bank SMS.

---

## Honest Gaps and Risks

- `parse_vpa()` returns the first VPA-shaped string found in the text. If a message contains both the user's own VPA and the counterparty's VPA, it will return whichever appears first — usually the counterparty's, but not guaranteed.
- `parse_direction()` treats "debit" as the user's perspective, but some banks phrase credit notifications as "credited to your account from X", which contains both directions. The code correctly returns "credit" in that case because `CREDIT_RE` does not match "credited to VPA" (which is phrased as a debit signal in DEBIT_RE). However, edge-case SMS wording could trip this.
- The amount regex allows commas in Indian number format (`1,23,456`) but does not validate the comma placement. An amount like `1,2345.00` would parse as `12345.0`.
- `parse_reference()` requires 9+ digits. A bank that uses shorter reference numbers will return `reference = None`.
- `detect_bank()` falls through to a raw text scan for 6 hardcoded bank names. This scan is `name.lower() in text.lower()` — not word-boundary-constrained — so "ICICI" in a merchant name like "ICICITOOLS" would incorrectly identify the bank as ICICI.
- `confidence` is computed as a fraction of 6 specific fields, not a semantic measure of parse quality. A message with amount + direction + VPA = confidence 0.5 may be fully usable for most downstream purposes, while a message with amount + direction + bank + account + reference (but no counterparty) = confidence 0.83 may be less useful for classification.

---

## Developer Notes

- To support a new bank's SMS format: add its DLT sender suffixes to `BANK_SENDER_MAP` and any distinctive VPA handles to `VPA_BANK_HINTS`. If the bank uses non-standard amount or direction phrasing, extend the relevant regex constants.
- The CLAUDE.md guide says new bank formats go in `brain/parser.py` in `BANK_PATTERNS` — but this file uses `BANK_SENDER_MAP`, not `BANK_PATTERNS`. The CLAUDE.md description is inaccurate for this specific constant name.
- This file has no imports from `config.py`. All thresholds are hardcoded (e.g., the 9-digit reference minimum, the 3-character name minimum). These are implicitly tunable only by editing this file directly.
- `ParsedPayment.to_row()` returns a dict suitable for `INSERT INTO payments`. Its keys must match the `payments` table column names — if the base agent renames columns, this breaks silently.
