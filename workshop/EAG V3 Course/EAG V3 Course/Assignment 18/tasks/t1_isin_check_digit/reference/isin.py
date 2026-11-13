"""ISIN validation (reference repair)."""
import re

_SHAPE = re.compile(r"[A-Z]{2}[A-Z0-9]{9}[0-9]")


def is_valid_isin(code):
    if not isinstance(code, str) or not _SHAPE.fullmatch(code):
        return False
    digits = "".join(str(int(ch, 36)) for ch in code)
    total = 0
    for position, ch in enumerate(reversed(digits)):
        n = int(ch)
        if position % 2 == 1:
            n *= 2
            if n > 9:
                n -= 9
        total += n
    return total % 10 == 0
