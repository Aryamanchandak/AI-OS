"""Exchange symbol file loader."""


def load_symbols(path):
    """Read an exchange symbol file and return a dict of {SYMBOL: ISIN}.

    The file is UTF-8 CSV text with two columns: symbol, isin. Rules:
      - Blank lines (empty or only whitespace) are ignored, wherever they are.
      - The first line that is not blank is a header and is skipped.
      - Whitespace around each field is removed.
      - Symbols are returned in upper case.
      - A data row that does not have exactly two fields raises ValueError.
    """
    out = {}
    with open(path, encoding="utf-8") as fh:
        for line in fh.read().split("\n")[1:]:
            symbol, isin = line.split(",")
            out[symbol] = isin
    return out
