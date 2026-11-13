"""Exchange symbol file loader (reference repair)."""


def load_symbols(path):
    out = {}
    with open(path, encoding="utf-8") as fh:
        lines = [line for line in fh.read().splitlines() if line.strip()]
    for line in lines[1:]:
        fields = [field.strip() for field in line.split(",")]
        if len(fields) != 2:
            raise ValueError(f"expected 2 fields, got {len(fields)}: {line!r}")
        out[fields[0].upper()] = fields[1]
    return out
