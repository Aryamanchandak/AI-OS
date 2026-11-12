# lib/diff.ts — Technical Documentation

**Last updated:** 2026-05-10
**Lines of code:** 41
**Language:** TypeScript

---

## What This File Does (Plain English)

This file implements a line-level diff algorithm using Longest Common Subsequence (LCS). Given two text strings, it returns an array of tagged lines indicating which lines are unchanged, added, or removed. This output is consumed by the UI to render before/after comparisons of section edits.

---

## How It Actually Works

### Entry Points

Two exports: the `DiffLine` interface and the `diffLines` function. `diffLines` is called from the UI layer when rendering the diff view for a selected section's most recent edit.

### Data Flow

```
diffLines(oldText, newText)
  → split each string on '\n' → oldLines[], newLines[]
  → build (m+1) × (n+1) LCS table using dynamic programming
  → walk back from dp[m][n] to dp[0][0]
  → at each cell:
      if oldLines[i-1] === newLines[j-1] → unshift { type: 'equal', text }
      elif j > 0 and dp[i][j-1] >= dp[i-1][j] → unshift { type: 'add', text }
      else → unshift { type: 'remove', text }
  → return DiffLine[]
```

The backtracking builds the result in reverse order using `unshift`, which reconstructs the diff in forward document order.

### State Management

None — pure function, no side effects, no module-level state.

### Key Functions / Classes

| Name | What it actually does |
|---|---|
| `diffLines(oldText, newText)` | Computes a line-level LCS diff between two strings; returns an annotated list of lines with type tags `'equal'`, `'add'`, or `'remove'` |

### External Dependencies

None — no imports, pure TypeScript.

### Error Handling

- Both `oldText` and `newText` are null-guarded with `(value || '')` before splitting, so `null` or `undefined` inputs produce an empty line array rather than throwing.
- No other error handling — if inputs are valid strings, the function always succeeds.

---

## Non-Technical Decisions Embedded in the Code

- **Line-level granularity only** — the diff operates on `\n`-split lines, not characters or words. Two lines that differ in one character appear as a full removal and full addition. This is intentional for readability at the cost of precision.
- **`unshift` rather than push + reverse** — the backtracking loop inserts each line at the front of the result array. This is slightly slower than push + reverse for large arrays because `unshift` is O(n) per call, making the reconstruction O(m·n) in the worst case. For typical section sizes this is not a problem.
- **No collapse of equal-line runs** — every unchanged line is included in the output individually. A UI rendering this output will display every equal line unless it adds its own context-collapse logic.
- **Tie-breaking in backtracking** favors additions over removals (`dp[i][j-1] >= dp[i-1][j]`). This means when both branches have equal LCS scores, an added line is chosen over a removed line. The choice is conventional but affects visual output when edits are ambiguous.

---

## Honest Gaps and Risks

- **O(m·n) time and space** — the LCS table allocates `(m+1) × (n+1)` integers and fills every cell. For sections of 200 lines each, this is ~40,000 cells — trivial. For very large documents (thousands of lines), memory and time grow quadratically. Document-level diffs on large plans could be noticeably slow.
- **Windows line endings** — `split('\n')` does not strip `\r`. A section with `\r\n` line endings will have `\r` attached to each line. Two logically identical lines where one has `\r` and one does not will be treated as different — producing spurious add/remove pairs.
- **Empty string edge case** — `''.split('\n')` returns `['']` (one empty string element), not `[]`. A completely empty `oldText` or `newText` produces a one-element array `['']`, which compares against the other input. This means diffing a non-empty string against an empty string produces `remove` entries plus possibly one `equal` entry for the trailing empty string — visually harmless but technically impure.

---

## Developer Notes

This file is a self-contained implementation with no dependencies. An identical implementation exists inline in `optimizer.jsx` — the two are equivalent. If you need character-level or word-level diffs (e.g., highlighting which specific words changed within a line), this implementation must be replaced or augmented — there is no word-diff mode. A common alternative is the `diff` npm package which provides Myers diff with word-level granularity.
