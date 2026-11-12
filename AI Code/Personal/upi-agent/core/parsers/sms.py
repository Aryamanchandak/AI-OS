"""
UPI SMS parser.

Indian bank UPI messages are formulaic. Regex handles ~95% of them cleanly.
We extract: amount, direction (debit/credit), date, counterparty (VPA or name),
reference number, and bank.

Designed to be liberal in what it accepts — if a field can't be parsed it's left
None and the row is still stored (so you can triage unknowns from the dashboard).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Optional


# Sender header patterns from DLT system. The suffix after hyphen identifies bank.
BANK_SENDER_MAP = {
    "HDFCBK": "HDFC", "HDFC": "HDFC",
    "SBIUPI": "SBI", "SBIINB": "SBI", "SBI": "SBI", "SBIPSG": "SBI",
    "ICICIB": "ICICI", "ICICI": "ICICI", "ICICIT": "ICICI",
    "AXISBK": "Axis", "AXIS": "Axis",
    "KOTAKB": "Kotak", "KOTAK": "Kotak",
    "PNBSMS": "PNB", "PNB": "PNB",
    "BOIIND": "BOI",
    "CANBNK": "Canara",
    "YESBNK": "Yes", "YESBK": "Yes",
    "IDFCFB": "IDFC", "IDFC": "IDFC",
    "INDBNK": "Indian",
    "IOBCHN": "IOB",
    "PYTMUP": "Paytm", "PAYTMB": "Paytm",
    "GPAYAP": "GPay",
    "PHNPEP": "PhonePe",
    "BOBIBK": "BOB", "BOB": "BOB",
    "UNIONB": "Union",
}

VPA_BANK_HINTS = {
    "okhdfcbank": "HDFC", "hdfcbank": "HDFC",
    "oksbi": "SBI", "sbi": "SBI",
    "okicici": "ICICI", "icici": "ICICI",
    "okaxis": "Axis", "axis": "Axis",
    "paytm": "Paytm",
    "ybl": "PhonePe",
    "upi": "NPCI",
    "ibl": "IndusInd",
    "axl": "Axis",
    "kotak": "Kotak",
}

UPI_KEYWORDS = re.compile(
    r"\b(UPI|VPA|UPI Ref|UPI Id|UPI/)\b", re.IGNORECASE
)

AMOUNT_RE = re.compile(
    r"(?:Rs\.?|INR|₹)\s*([0-9]{1,3}(?:,[0-9]{2,3})*(?:\.\d{1,2})?|\d+(?:\.\d{1,2})?)",
    re.IGNORECASE,
)

DEBIT_RE = re.compile(r"\b(debited|debit|sent|paid|deducted|withdrawn|trf to|transferred to)\b", re.IGNORECASE)
CREDIT_RE = re.compile(r"\b(credited|credit|received|deposited)\b", re.IGNORECASE)

VPA_RE = re.compile(r"\b([a-zA-Z0-9][a-zA-Z0-9._-]{1,63}@[a-zA-Z][a-zA-Z0-9]{1,30})\b")

REF_RE = re.compile(
    r"(?:Ref(?:erence)?(?:\s*No)?\.?|UPI(?:\s*Ref(?:\s*No)?)?\.?|RRN|Txn(?:\s*Id)?\.?)"
    r"[\s:/.]*(?:[A-Z0-9]+/)*([0-9]{9,})",
    re.IGNORECASE,
)

NAME_RE = re.compile(
    r"\b(?:to|trf to|paid to|sent to)\s+([A-Z][A-Z\s.&'-]{2,40}?)"
    r"(?=\s+(?:on|vpa|upi|ref|via|at|from|not\s|$|[.,;]))",
    re.IGNORECASE,
)

AXIS_NAME_RE = re.compile(
    r"UPI/[A-Z0-9]+/\d+/([A-Z][A-Z .&'-]+?)(?=\.|$|\s+Call\b|\s+Not\s+[Yy]ou)"
)

AMOUNT_FALLBACK_RE = re.compile(
    r"(?:debited\s+by|credited\s+by|debit\s+of|credit\s+of)\s+([0-9]+(?:\.\d{1,2})?)",
    re.IGNORECASE,
)

ACCOUNT_RE = re.compile(
    r"(?:A/[Cc](?:\s*No\.?|ount)?|Acct|a/c|from\s+A/C)\s*[Xx*.]*\s*(\d{4})",
    re.IGNORECASE,
)

DATE_PATTERNS = [
    (r"\b(\d{1,2})[-/](\d{1,2})[-/](\d{2,4})\b", "%d-%m-%Y"),
    (r"\b(\d{1,2})[-\s]?([A-Za-z]{3})[-\s]?(\d{2,4})\b", "%d-%b-%Y"),
]


@dataclass
class ParsedPayment:
    """Structured payment extracted from one SMS."""
    amount: Optional[float]
    direction: Optional[str]  # 'debit' | 'credit'
    bank: Optional[str]
    counterparty_vpa: Optional[str]
    counterparty_name: Optional[str]
    reference: Optional[str]
    account_last4: Optional[str]
    confidence: float
    raw_text: str
    sender_id: str

    def to_row(self) -> dict:
        return {
            "amount": self.amount,
            "direction": self.direction,
            "bank": self.bank,
            "counterparty_vpa": self.counterparty_vpa,
            "counterparty_name": self.counterparty_name,
            "reference": self.reference,
            "account_last4": self.account_last4,
            "confidence": self.confidence,
            "raw_text": self.raw_text,
            "sender_id": self.sender_id,
        }


def looks_like_upi(text: str) -> bool:
    """Quick pre-filter to avoid parsing non-UPI messages."""
    return bool(UPI_KEYWORDS.search(text))


def detect_bank(sender_id: str, vpa: Optional[str], text: str) -> Optional[str]:
    """Try in order: sender header → VPA handle hint → text mention."""
    if sender_id:
        s = sender_id.upper().split("-")[-1]
        if s in BANK_SENDER_MAP:
            return BANK_SENDER_MAP[s]
    if vpa:
        handle = vpa.split("@")[-1].lower()
        for key, bank in VPA_BANK_HINTS.items():
            if key in handle:
                return bank
    for name in ("HDFC", "SBI", "ICICI", "Axis", "Kotak", "PNB"):
        if name.lower() in text.lower():
            return name
    return None


def parse_amount(text: str) -> Optional[float]:
    m = AMOUNT_RE.search(text)
    if not m:
        m = AMOUNT_FALLBACK_RE.search(text)
        if not m:
            return None
    raw = m.group(1).replace(",", "")
    try:
        return float(raw)
    except ValueError:
        return None


def parse_direction(text: str) -> Optional[str]:
    if DEBIT_RE.search(text):
        return "debit"
    if CREDIT_RE.search(text):
        return "credit"
    return None


def parse_vpa(text: str) -> Optional[str]:
    m = VPA_RE.search(text)
    return m.group(1) if m else None


def parse_name(text: str) -> Optional[str]:
    m = NAME_RE.search(text)
    if not m:
        m = AXIS_NAME_RE.search(text)
        if not m:
            return None
    name = m.group(1).strip().rstrip(".,;")
    if name.upper() in {"VPA", "UPI", "A/C", "ACCOUNT"}:
        return None
    if len(name) < 3:
        return None
    return name


def parse_reference(text: str) -> Optional[str]:
    m = REF_RE.search(text)
    return m.group(1) if m else None


def parse_account(text: str) -> Optional[str]:
    m = ACCOUNT_RE.search(text)
    return m.group(1) if m else None


def parse(text: str, sender_id: str = "") -> Optional[ParsedPayment]:
    """
    Parse one SMS. Returns None if it doesn't look like a UPI message.
    Otherwise returns a ParsedPayment with best-effort field extraction.
    """
    if not text or not looks_like_upi(text):
        return None

    amount = parse_amount(text)
    direction = parse_direction(text)
    vpa = parse_vpa(text)
    name = parse_name(text)
    reference = parse_reference(text)
    account = parse_account(text)
    bank = detect_bank(sender_id, vpa, text)

    fields = [amount, direction, vpa or name, reference, bank, account]
    confidence = sum(1 for f in fields if f) / len(fields)

    if amount is None and direction is None:
        return None

    return ParsedPayment(
        amount=amount,
        direction=direction,
        bank=bank,
        counterparty_vpa=vpa,
        counterparty_name=name,
        reference=reference,
        account_last4=account,
        confidence=confidence,
        raw_text=text,
        sender_id=sender_id,
    )
