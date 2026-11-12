"""Golden-set regression check (Phase 2).

Runs the live process pipeline (load → OCR → mask → intersect → group → noise
floor) over the pages in golden/answers.json and reports, per passage, the
character-edit distance between the extracted text and the human-confirmed
known-correct text. Re-run after any threshold/logic change: if the deltas grow,
something regressed.

  .venv/bin/python golden/check.py

Pass bar (spec §Phase2 exit): each clean passage within 1–2 normalized char edits.
Alignment is best-match (each golden passage → the system passage with the
smallest edit distance) so it is robust to grouping differences.
"""

from __future__ import annotations

import json
import sys
import unicodedata
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core import detect, images, ocr  # noqa: E402
import process as P                   # noqa: E402

PASS_EDITS = 2   # spec exit bar: within 1–2 char edits per passage


def normalize(s: str) -> str:
    """Fold the cosmetic differences that aren't OCR errors: curly→straight
    quotes, em/en-dash→hyphen, collapse whitespace, strip. Case is kept."""
    s = unicodedata.normalize("NFKC", s)
    for a, b in [("—", "-"), ("–", "-"), ("‑", "-"),
                 ("’", "'"), ("‘", "'"),
                 ("“", '"'), ("”", '"')]:
        s = s.replace(a, b)
    return " ".join(s.split()).strip()


def levenshtein(a: str, b: str) -> int:
    """Classic DP edit distance (insert/delete/substitute = 1)."""
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def extract_passages(image_path: Path) -> list[str]:
    """The exact Phase 1/2 pipeline, minus storage — returns passage texts."""
    pil = images.load_image(image_path)
    rgb = np.asarray(pil)
    words = ocr.ocr_page(pil)
    mask = detect.yellow_mask(rgb, None)
    kept = P._keep_words(words, mask, pil.size[0])
    groups = [g for g in P._group_passages(kept) if len(g) >= P.MIN_PASSAGE_WORDS]
    return [P._passage_text(g) for g in groups]


def main() -> int:
    answers = json.loads((ROOT / "golden" / "answers.json").read_text())
    pages = answers["pages"]
    inbox = ROOT / "data" / "inbox"

    total = passed = 0
    worst = 0.0
    print(f"Golden-set regression — pass bar ≤{PASS_EDITS} normalized char edits\n")
    for fname, golden_list in pages.items():
        img = inbox / fname
        if not img.exists():
            print(f"{fname}: MISSING from inbox — skipped")
            continue
        system = [normalize(t) for t in extract_passages(img)]
        print(f"{fname}  ({len(golden_list)} golden / {len(system)} extracted)")
        for gi, gtext in enumerate(golden_list, 1):
            g = normalize(gtext)
            if system:
                dists = [(levenshtein(g, s), s) for s in system]
                edits, match = min(dists, key=lambda d: d[0])
            else:
                edits, match = len(g), ""
            total += 1
            pct = 100 * (1 - edits / max(len(g), 1))
            ok = edits <= PASS_EDITS
            passed += ok
            worst = max(worst, edits / max(len(g), 1))
            flag = "PASS" if ok else "····"
            print(f"  p{gi}: {edits:>3} edits  ({pct:5.1f}% match)  [{flag}]")
            if not ok:
                # show a short diff hint
                print(f"        golden : {g[:72]}{'…' if len(g) > 72 else ''}")
                print(f"        system : {match[:72]}{'…' if len(match) > 72 else ''}")
        print()

    print("-" * 56)
    print(f"passages: {total}   within ≤{PASS_EDITS} edits: {passed}   "
          f"worst error rate: {worst*100:.1f}%")
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
