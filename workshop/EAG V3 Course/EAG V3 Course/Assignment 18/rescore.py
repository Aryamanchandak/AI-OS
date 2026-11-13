"""Score every saved journal with both scorer versions. Calls no model.

    uv run python rescore.py

Writes results/scores_v1.json and results/scores_v2.json, prints the v2 rows,
the counts per task, and every row the scoring change altered.
"""
import json
from collections import Counter
from pathlib import Path

from scorer import VERSIONS, score

ROOT = Path(__file__).resolve().parent
FIELDS = ("outcome", "integrity", "verification")


def main(journals_dir=ROOT / "journals", results_dir=ROOT / "results"):
    journals = [json.loads(p.read_text()) for p in sorted(Path(journals_dir).glob("*.json"))]
    if not journals:
        print(f"no journals in {journals_dir}")
        return {}
    rows = {v: [score(j, v) for j in journals] for v in VERSIONS}
    Path(results_dir).mkdir(exist_ok=True)
    for version, scored in rows.items():
        (Path(results_dir) / f"scores_{version}.json").write_text(json.dumps(scored, indent=2))

    latest = rows[VERSIONS[-1]]
    print(f"{len(journals)} journals, scorer {VERSIONS[-1]}\n")
    print(f"{'run':<26}{'outcome':<36}{'integrity':<26}{'verification':<17}calls  steps  seconds  tokens")
    for r in latest:
        c = r["cost"]
        print(f"{r['run_id']:<26}{r['outcome']:<36}{r['integrity']:<26}{r['verification']:<17}"
              f"{c['model_calls']:>5}  {c['tool_steps']:>5}  {c['seconds']:>7}  {c['prompt_tokens'] + c['completion_tokens']:>6}")

    print("\nCounts per task (raw, out of runs attempted):")
    for task in sorted({r["task"] for r in latest}):
        mine = [r for r in latest if r["task"] == task]
        for field in FIELDS:
            counts = ", ".join(f"{value} {n}/{len(mine)}" for value, n in sorted(Counter(r[field] for r in mine).items()))
            print(f"  {task:<24}{field:<14}{counts}")

    print(f"\nScoring change {VERSIONS[0]} -> {VERSIONS[-1]} (same journals, no model calls):")
    changed = 0
    for old, new in zip(rows[VERSIONS[0]], latest):
        for field in FIELDS:
            if old[field] != new[field]:
                changed += 1
                print(f"  {old['run_id']}: {field} {old[field]} -> {new[field]}")
    print(f"  {changed} field(s) changed across {len(journals)} runs")
    return rows


if __name__ == "__main__":
    main()
