"""Veritas CLI.

    python cli.py "Creatine supplementation improves cognitive performance in
                   sleep-deprived adults"
"""

from __future__ import annotations

import sys
import textwrap

from orchestrator import Veritas

W = 72


def _wrap(text: str, indent: str = "  ") -> str:
    return textwrap.fill(str(text), width=W, initial_indent=indent,
                         subsequent_indent=indent)


def report(claim: str, r: dict) -> None:
    print("\n" + "=" * W)
    print("  VERDICT")
    print("=" * W)
    print(f"\n  Claim      {claim}")
    print(f"  Verdict    {str(r.get('verdict', '?')).upper()}")
    print(f"  Confidence {r.get('confidence', '—')}")
    print(f"  Sources    {r.get('sources_examined', 0)} examined "
          f"over {r.get('rounds', 1)} round(s)\n")

    if r.get("one_line_answer"):
        print(_wrap(r["one_line_answer"]) + "\n")

    if r.get("verdict_rationale"):
        print("  RATIONALE")
        print(_wrap(r["verdict_rationale"], "    ") + "\n")

    for label, key in [("SUPPORTING", "supporting_evidence"),
                       ("CONTRADICTING", "contradicting_evidence")]:
        items = r.get(key) or []
        if items:
            print(f"  {label} ({len(items)})")
            for e in items:
                print(_wrap(f"[{e.get('source_id')}] {e.get('point')}", "    "))
            print()

    if r.get("open_gaps"):
        print("  OPEN GAPS")
        for g in r["open_gaps"]:
            print(_wrap(f"- {g}", "    "))
        print()

    audit = r.get("audit") or {}
    if audit:
        print(f"  AUDIT      {audit.get('verdict', '—')}")
        failed = [c for c in audit.get("checks", []) if c.get("result") != "pass"]
        print(f"  Checks     {len(audit.get('checks', [])) - len(failed)}"
              f"/{len(audit.get('checks', []))} passed")
        for c in failed:
            print(_wrap(f"FAIL {c.get('id')} {c.get('name')}: {c.get('reason')}", "    "))
        if audit.get("weakest_link"):
            print("  Weakest link")
            print(_wrap(audit["weakest_link"], "    "))
        print()

    tok = r.get("tokens", {})
    print(f"  Tokens     {tok.get('input', 0):,} in / {tok.get('output', 0):,} out")
    print(f"  Trace      {r.get('trace_path')}")
    print("=" * W + "\n")


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    claim = " ".join(sys.argv[1:])
    try:
        report(claim, Veritas().run(claim))
    except KeyboardInterrupt:
        print("\n  interrupted")
        return 130
    except Exception as exc:
        print(f"\n  ERROR: {type(exc).__name__}: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
