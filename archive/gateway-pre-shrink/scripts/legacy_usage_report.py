"""Count daily legacy-listener connections from retained process logs."""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import date, timedelta
from pathlib import Path
import re


LINE = re.compile(r"^(\d{4}-\d{2}-\d{2})\s.*legacy_connection protocol=(http|websocket)\b")


def counts(paths: list[Path]) -> Counter[tuple[date, str]]:
    result: Counter[tuple[date, str]] = Counter()
    for path in paths:
        for line in path.read_text(encoding="utf-8").splitlines():
            match = LINE.search(line)
            if match:
                result[(date.fromisoformat(match.group(1)), match.group(2))] += 1
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("logs", nargs="+", type=Path)
    parser.add_argument("--start", type=date.fromisoformat, required=True)
    parser.add_argument("--end", type=date.fromisoformat, required=True)
    args = parser.parse_args()
    if args.end < args.start:
        parser.error("--end must not precede --start")
    totals = counts(args.logs)
    print("date,http,websocket,total")
    day = args.start
    while day <= args.end:
        http = totals[(day, "http")]
        websocket = totals[(day, "websocket")]
        print(f"{day},{http},{websocket},{http + websocket}")
        day += timedelta(days=1)


if __name__ == "__main__":
    main()
