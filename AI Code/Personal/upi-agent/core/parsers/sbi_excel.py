"""
SBI bank statement parser.

The file SBI calls "Excel download" is actually a TSV with .xls extension.
Format:
  - 19 rows of account metadata header
  - Tab-separated transaction table with columns:
      Txn Date | Value Date | Description | Ref No./Cheque No. | Debit | Credit | Balance
  - A footer row beginning with '**' that summarizes the statement

The Description field embeds structured data:
  UPI:    "TO TRANSFER-UPI/DR/<12-digit ref>/<n>/<bank>/<vpa>/<narration>"
          "BY TRANSFER-UPI/CR/<12-digit ref>/<n>/<bank>/<vpa>/<narration>"
          "BY REVERSAL-UPI/REV/<ref>/..."
  NEFT:   "BY TRANSFER-NEFT*<IFSC>*<UTR>*<sender name>"
  Other:  Free-form text for interest, charges, insurance debits, POS, etc.

Tested against real SBI statement: 710 rows, 685 UPI / 16 NEFT / 8 other.
702/710 produce a dedup key (UPI ref or NEFT UTR).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional, List

import pandas as pd


SBI_HEADER_ROWS = 19

UPI_RE = re.compile(
    r'UPI/(?P<dir>DR|CR|REV)/(?P<ref>\d+)'
    r'(?:/(?P<n>[^/]*)/(?P<bank>[A-Z]+)/(?P<vpa>[^/]+)/(?P<narr>[^-]*))?'
)
NEFT_RE = re.compile(
    r'NEFT\*(?P<ifsc>[A-Z0-9]+)\*(?P<utr>[A-Z0-9]+)\*(?P<n>[^-]+)'
)
IMPS_RE = re.compile(r'IMPS[/-](?P<ref>[A-Z0-9]+)')


@dataclass
class ParsedRow:
    occurred_at: str
    amount: float
    direction: str
    txn_kind: str
    ref_no: Optional[str]
    counterparty_name: Optional[str]
    counterparty_vpa: Optional[str]
    counterparty_bank: Optional[str]
    narration: Optional[str]
    raw_description: str
    balance_after: Optional[float]

    def to_dict(self) -> dict:
        return asdict(self)


def _clean_amount(x) -> Optional[float]:
    if pd.isna(x):
        return None
    s = str(x).strip()
    if s == "" or s.lower() == "nan":
        return None
    s = s.replace(",", "")
    try:
        return float(s)
    except ValueError:
        return None


def _classify_kind(desc: str) -> str:
    d = desc.upper()
    if "UPI/REV" in d:
        return "reversal"
    if "UPI/" in d:
        return "upi"
    if "NEFT" in d:
        return "neft"
    if "IMPS" in d:
        return "imps"
    if "RTGS" in d:
        return "rtgs"
    if "CREDIT INTEREST" in d or "INT.PD" in d:
        return "interest"
    if "COMM " in d or "CHARGES" in d or "CHRG" in d or "GST " in d:
        return "charges"
    if "PMJJBY" in d or "PMSBY" in d or "INSURANCE PREMIUM" in d:
        return "insurance"
    if "DEBIT CARD" in d or "OTHPG" in d or "POS " in d:
        return "pos"
    if "ATM-" in d or "ATM CASH" in d or "ATM WD" in d:
        return "atm"
    return "other"


def parse_sbi_file(path: str | Path) -> List[ParsedRow]:
    """
    Parse an SBI 'Excel' (TSV) export. Returns parsed rows in chronological
    order. Skips header metadata and footer summary rows.
    """
    try:
        df = pd.read_csv(
            path, sep="\t", skiprows=SBI_HEADER_ROWS,
            encoding="utf-8", engine="python", on_bad_lines="skip",
        )
    except Exception as e:
        raise ValueError(f"Could not parse as SBI TSV: {e}") from e

    df.columns = [c.strip() for c in df.columns]
    expected = {"Txn Date", "Description"}
    if not expected.issubset(df.columns):
        raise ValueError(
            f"Doesn't look like an SBI statement. Got columns: {list(df.columns)}"
        )

    df = df.dropna(subset=["Txn Date"])
    df = df[~df["Txn Date"].astype(str).str.startswith("**")].reset_index(drop=True)

    out: List[ParsedRow] = []
    for _, row in df.iterrows():
        debit = _clean_amount(row.get("Debit"))
        credit = _clean_amount(row.get("Credit"))
        if debit is None and credit is None:
            continue
        amount = debit if debit is not None else credit
        direction = "debit" if debit is not None else "credit"

        desc = str(row.get("Description", "")).strip()
        kind = _classify_kind(desc)

        ref_no = None
        cp_name = None
        cp_vpa = None
        cp_bank = None
        narration = None

        m = UPI_RE.search(desc)
        if m:
            ref_no = m.group("ref")
            if m.group("n"):
                cp_name = m.group("n").strip() or None
                cp_bank = m.group("bank")
                cp_vpa = m.group("vpa").strip() or None
                narration = (m.group("narr") or "").strip() or None
        else:
            m = NEFT_RE.search(desc)
            if m:
                ref_no = m.group("utr")
                cp_name = m.group("n").strip() or None
                cp_bank = m.group("ifsc")[:4]
            else:
                m = IMPS_RE.search(desc)
                if m:
                    ref_no = m.group("ref")

        try:
            occurred_at = datetime.strptime(
                str(row["Txn Date"]).strip(), "%d-%b-%y"
            ).date().isoformat()
        except ValueError:
            try:
                occurred_at = datetime.strptime(
                    str(row["Txn Date"]).strip(), "%d %b %Y"
                ).date().isoformat()
            except ValueError:
                continue

        out.append(ParsedRow(
            occurred_at=occurred_at, amount=amount, direction=direction,
            txn_kind=kind, ref_no=ref_no,
            counterparty_name=cp_name, counterparty_vpa=cp_vpa,
            counterparty_bank=cp_bank, narration=narration,
            raw_description=desc, balance_after=_clean_amount(row.get("Balance")),
        ))

    return out


if __name__ == "__main__":
    import sys
    rows = parse_sbi_file(sys.argv[1])
    print(f"Parsed {len(rows)} rows")
    from collections import Counter
    print("By kind:", Counter(r.txn_kind for r in rows))
    print("With ref_no:", sum(1 for r in rows if r.ref_no))
