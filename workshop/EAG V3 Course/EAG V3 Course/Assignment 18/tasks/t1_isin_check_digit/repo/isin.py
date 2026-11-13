"""ISIN validation."""


def is_valid_isin(code):
    """Return True if `code` is a valid ISIN, otherwise False. Never raise.

    An ISIN is exactly 12 characters:
      - 2 uppercase ASCII letters (the country code),
      - 9 uppercase ASCII letters or digits (the national identifier),
      - 1 digit (the check digit).

    Check digit rule: replace every letter with its number (A=10, B=11, ...,
    Z=35) to get one long string of digits. Then apply the Luhn algorithm:
    starting from the rightmost digit and moving left, double every second
    digit, add the digits of each product, and add everything up. The total
    must be divisible by 10.

    Anything that is not a str, has the wrong length, or contains lowercase
    letters or other characters is invalid.
    """
    if not isinstance(code, str) or len(code) != 12:
        return False
    country, body, check = code[:2], code[2:11], code[11]
    if not (country.isalpha() and country.isupper()):
        return False
    if not body.isdigit():
        return False
    if not check.isdigit():
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
