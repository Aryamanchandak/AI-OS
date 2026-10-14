from __future__ import annotations

from enum import StrEnum


class DomainPack(StrEnum):
    GENERAL = "general"
    RATES_MACRO = "rates/macro"
    CREDIT = "credit"
    FORENSIC = "forensic accounting"


DOMAIN_LENSES = {
    DomainPack.GENERAL: "Identify the real-world mechanism, scope, base rate, and falsifier.",
    DomainPack.RATES_MACRO: "Test reaction functions, inflation/growth paths, curve transmission, lags, and policy credibility.",
    DomainPack.CREDIT: "Test issuer liquidity, covenants, refinancing, recovery value, management defense, and the short thesis.",
    DomainPack.FORENSIC: "Test the benign management explanation, accounting mechanics, disclosure quality, and residual fraud risk.",
}

