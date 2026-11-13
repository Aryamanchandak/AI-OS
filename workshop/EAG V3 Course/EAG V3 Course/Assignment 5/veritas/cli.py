"""Veritas CLI — scientific essay writer.

    python cli.py "Creatine supplementation improves cognitive performance in
                   sleep-deprived adults"

    python cli.py --topic "How does creatine affect the brain?"

Claims are checked (evidence gathered, a verdict reached) and topics are
explored (evidence gathered, no verdict) — either way the output is an
explanatory essay written from the evidence found, saved under runs/.
"""

from __future__ import annotations

import sys
import textwrap

from orchestrator import TopicExplorer, Veritas

W = 72


def _wrap(text: str, indent: str = "  ") -> str:
    return textwrap.fill(str(text), width=W, initial_indent=indent,
                         subsequent_indent=indent)


def _print_essay(r: dict) -> None:
    print("\n" + "=" * W)
    title = r.get("essay_title") or "ESSAY"
    print(f"  {title.upper()}")
    print("=" * W + "\n")
    for para in str(r.get("essay", "")).split("\n"):
        if para.strip():
            print(_wrap(para))
        else:
            print()
    if r.get("key_takeaway"):
        print("\n  TAKEAWAY")
        print(_wrap(r["key_takeaway"], "    "))
    print()


def report_claim(claim: str, r: dict) -> None:
    if r.get("essay"):
        _print_essay(r)
    else:
        print("\n" + _wrap(r.get("one_line_answer", "No essay could be produced.")) + "\n")

    print("=" * W)
    print("  DETAIL")
    print("=" * W)
    print(f"\n  Claim      {claim}")
    print(f"  Verdict    {str(r.get('verdict', '?')).upper()}")
    print(f"  Confidence {r.get('confidence', '—')}")
    print(f"  Sources    {r.get('sources_examined', 0)} examined "
          f"over {r.get('rounds', 1)} round(s)\n")

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

    _print_footer(r)


def report_topic(topic: str, r: dict) -> None:
    if r.get("essay"):
        _print_essay(r)
    else:
        print("\n" + _wrap(r.get("one_line_answer", "No essay could be produced.")) + "\n")

    print("=" * W)
    print("  DETAIL")
    print("=" * W)
    print(f"\n  Topic      {topic}")
    print(f"  Sources    {r.get('sources_examined', 0)} examined")
    check = r.get("citation_check") or {}
    if check:
        mark = "PASS" if check.get("result") == "pass" else "FAIL"
        print(f"  Citations  [{mark}] {check.get('reason')}")
    print()

    if r.get("open_questions"):
        print("  OPEN QUESTIONS")
        for q in r["open_questions"]:
            print(_wrap(f"- {q}", "    "))
        print()

    _print_footer(r)


def _print_footer(r: dict) -> None:
    tok = r.get("tokens", {})
    print(f"  Tokens     {tok.get('input', 0):,} in / {tok.get('output', 0):,} out")
    if tok.get("cache_read") or tok.get("cache_write"):
        print(f"  Cache      {tok.get('cache_read', 0):,} read / "
              f"{tok.get('cache_write', 0):,} written")
    print(f"  Trace      {r.get('trace_path')}")
    print("=" * W + "\n")


def main() -> int:
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        return 1

    topic_mode = args[0] in ("--topic", "-t")
    if topic_mode:
        args = args[1:]
    if not args:
        print(__doc__)
        return 1
    subject = " ".join(args)

    try:
        if topic_mode:
            report_topic(subject, TopicExplorer().run_topic(subject))
        else:
            report_claim(subject, Veritas().run(subject))
    except KeyboardInterrupt:
        print("\n  interrupted")
        return 130
    except Exception as exc:
        print(f"\n  ERROR: {type(exc).__name__}: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
