"""Single canonical Indian-rupee formatter."""


def _money(x: float) -> str:
    """Format ₹ amount Indian-style: 1,23,456. Handles negatives."""
    n = int(round(x))
    s = str(abs(n))
    if len(s) <= 3:
        out = s
    else:
        out = s[-3:]
        s = s[:-3]
        while len(s) > 2:
            out = s[-2:] + "," + out
            s = s[:-2]
        out = s + "," + out
    return f"₹{out}" if n >= 0 else f"-₹{out}"
