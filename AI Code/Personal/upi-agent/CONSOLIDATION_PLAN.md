# Brain + Tax Consolidation Plan

**Status:** proposal only — no files have been moved or edited.
**Goal:** collapse `upi-agent/brain/` and `upi-agent/tax/` into one package
(`upi-agent/core/`) organised into thematic subfolders that group files by
*role*, not by which of the two prior systems they came from.

The plan is derived from reading every per-file doc in `brain/deep-dive/` and
`tax/*.md`, plus the import graph across `agent.py`, `dashboard.py`, the two
packages, and `tests/`.

---

## 1. Why merge them at all

`brain/` and `tax/` are documented as two systems but they already share a
database, a column (`category_source`), a table (`category_rules`), and a
hand-off (`tax/ingest_excel.py` calls `brain.reactor.on_new_payments`). The
boundary is historical, not architectural. Concretely:

| Concern | brain has | tax has | Today |
|---|---|---|---|
| DB schema migrations | `brain/migrate.py` | `tax/migrate.py` | **Both** create `category_rules` and **both** add `payments.category_source`. Whichever runs first wins. |
| Categorisation rule store | `classifier.record_user_categorization` writes `category_rules` | `RuleBasedClassifier.learn` writes `category_rules` | Same table, two writers, two slightly different write shapes. |
| DB connection | `brain/db.py` (auto-commit, lazy migrate, FK on, Row factory) | `tax/routes.py:_db()` (raw `sqlite3.connect`) | Tax bypasses the helper everyone else uses. |
| `DB_PATH` | `brain/config.py` | Hard-coded as `Path.home() / ".upi-agent" / "data.db"` in **4 tax files** (called out in `tax/routes.md`) | Five sources of truth for one path. |
| `_money()` Indian-rupee formatter | `anomaly.py`, `goals.py`, `narrator.py` | — | Three copies inside brain alone. |
| Parsers | `brain/parser.py` (SMS regex) | `tax/sbi_parser.py` (Excel/TSV) | Same conceptual layer, different folders. |
| Classifier APIs | Ensemble of weighted signals (auto, reactor-driven) | `Classifier` Protocol + RuleBased + LocalLLM (manual, UI-driven) | Both legitimate, but they should sit next to each other and share the rule-store layer. |

A single package makes the duplications visible and forces the obvious fixes.

---

## 2. Proposed layout

One top-level package, `upi-agent/core/`, with subfolders grouped by *role in
the pipeline*. The deep-dive docs move with their code so the per-file
documentation stays adjacent.

```
upi-agent/
├── agent.py                      ← unchanged in role; one import line updates (§4)
├── dashboard.py                  ← unchanged in role; ~5 import lines update (§4)
├── requirements.txt
├── README.md, CLAUDE.md          ← edit to describe core/ instead of brain/+tax/
├── INTEGRATION.md                ← retire (its install steps collapse into README)
├── launchd/
├── tests/                        ← stays at root; imports rewrite to core.* (§4)
│
└── core/                         ← unified package (replaces brain/ and tax/)
    ├── __init__.py               ← merged from the two trivial __init__.py docstrings
    ├── config.py                 ← from brain/config.py; absorbs the 4 hard-coded
    │                                DB_PATH copies in tax + the hard-coded narrator
    │                                30% gap + the hard-coded classifier heuristics
    │                                (the `# tunables live in config.py` rule the
    │                                brain README claims becomes actually true)
    │
    ├── schema/                   ← all DB lifecycle in one place
    │   ├── __init__.py
    │   ├── db.py                 ← from brain/db.py (THE connection helper, used
    │   │                            by every module; tax/routes.py:_db() goes away)
    │   └── migrate.py            ← MERGED brain/migrate.py + tax/migrate.py:
    │                                resolves the duplicate `category_rules` create,
    │                                the duplicate `payments.category_source` add,
    │                                and the silent "whichever runs first wins" race.
    │                                Single ordered migration that creates payments
    │                                additions, agent_events, goals, goal_status_cache,
    │                                category_rules, recurring_payments, buckets, and
    │                                tax_settings.
    │
    ├── parsers/                  ← raw bank source → ParsedPayment
    │   ├── __init__.py
    │   ├── sms.py                ← from brain/parser.py
    │   └── sbi_excel.py          ← from tax/sbi_parser.py
    │   (future: hdfc_excel.py, icici_excel.py — dispatch in ingest/)
    │
    ├── ingest/                   ← parsed rows → payments table
    │   ├── __init__.py
    │   └── excel.py              ← from tax/ingest_excel.py
    │   (SMS ingest currently lives in agent.py — out of scope for this
    │    consolidation; a follow-up could move it here as `ingest/sms.py`.)
    │
    ├── classify/                 ← all categorisation logic
    │   ├── __init__.py
    │   ├── auto.py               ← from brain/classifier.py — 4-classifier
    │   │                            ensemble, reactor-driven, writes category_source='agent'
    │   ├── manual.py             ← from tax/classifier.py — Classifier Protocol +
    │   │                            RuleBasedClassifier + LocalLLMClassifier, UI-driven
    │   └── rules.py              ← NEW: shared category_rules read/write.
    │                                Extracts brain.classifier.record_user_categorization
    │                                and tax.classifier.RuleBasedClassifier.learn into
    │                                one upsert helper so the two paths can't drift.
    │
    ├── detect/                   ← per-payment analysis after ingest
    │   ├── __init__.py
    │   ├── anomaly.py            ← from brain/anomaly.py
    │   ├── goals.py              ← from brain/goals.py
    │   └── recurring.py          ← from brain/recurring.py
    │
    ├── orchestration/
    │   ├── __init__.py
    │   └── reactor.py            ← from brain/reactor.py (logic unchanged; imports
    │                                rewritten to core.classify.auto, core.detect.*).
    │                                Optionally extends to also receive the new
    │                                payment IDs returned by ingest/excel.py — same
    │                                hook either way.
    │
    ├── output/                   ← human-facing artifacts
    │   ├── __init__.py
    │   ├── narrator.py           ← from brain/narrator.py — weekly markdown story
    │   └── excel_export.py       ← from tax/exporter.py — CA-ready .xlsx
    │
    ├── notify/
    │   ├── __init__.py
    │   └── macos.py              ← from brain/notifier.py
    │
    ├── web/                      ← FastAPI surface
    │   ├── __init__.py
    │   ├── routes.py             ← from tax/routes.py
    │   └── templates.py          ← from tax/templates.py
    │   (long-term: the /, /feed, /triage routes in dashboard.py also belong
    │    here; out of scope for this consolidation.)
    │
    ├── cli/
    │   ├── __init__.py
    │   └── main.py               ← from brain/cli.py.
    │                                Entry point becomes `python -m core.cli`.
    │                                README + launchd plist update accordingly.
    │
    ├── utils/                    ← shared helpers, de-duplicated
    │   ├── __init__.py
    │   ├── money.py              ← single _money() Indian-rupee formatter,
    │   │                            consuming the 3 copies in anomaly/goals/narrator
    │   └── tokens.py             ← name_tokens() + NAME_STOP_TOKENS, currently
    │                                only in brain/classifier.py but needed by
    │                                classify/manual.py once they share rules.py
    │
    └── deep-dive/                ← per-file docs travel with their code
        ├── config.md
        ├── schema/
        │   ├── db.md
        │   └── migrate.md        ← merged from brain/deep-dive/migrate.md + tax/migrate.md
        ├── parsers/
        │   ├── sms.md            ← was brain/deep-dive/parser.md
        │   └── sbi_excel.md      ← was tax/sbi_parser.md
        ├── ingest/excel.md
        ├── classify/
        │   ├── auto.md           ← was brain/deep-dive/classifier.md
        │   ├── manual.md         ← was tax/classifier.md
        │   └── rules.md          ← NEW
        ├── detect/{anomaly,goals,recurring}.md
        ├── orchestration/reactor.md
        ├── output/{narrator,excel_export.md}
        ├── notify/macos.md       ← was brain/deep-dive/notifier.md
        ├── web/{routes,templates}.md
        ├── cli/main.md           ← was brain/deep-dive/cli.md
        └── utils/{money,tokens}.md  ← NEW
```

---

## 3. File-by-file destination map

### From `brain/`

| Source | Destination | Notes |
|---|---|---|
| `brain/__init__.py` | `core/__init__.py` (merged) | Trivial. Combine the two docstrings. |
| `brain/config.py` | `core/config.py` | Absorbs `DB_PATH` literals from 4 tax files. Add the narrator's hard-coded 30% calendar-correlation gap and classifier's hard-coded morning-hour / small-amount thresholds (called out in `brain/deep-dive/classifier.md` and `narrator.md` as design-rule violations). |
| `brain/db.py` | `core/schema/db.py` | Unchanged behaviour. Becomes the single connection factory used by `web/routes.py` too (replacing tax's `_db()`). |
| `brain/migrate.py` | `core/schema/migrate.py` (merged) | See §5 below — this is the most substantive merge. |
| `brain/parser.py` | `core/parsers/sms.py` | Note: `CLAUDE.md` claims new bank patterns go in `BANK_PATTERNS` — actually `BANK_SENDER_MAP`. Worth fixing in the new CLAUDE.md while we're here. |
| `brain/classifier.py` | `core/classify/auto.py` | Extract `record_user_categorization` and `name_tokens` into `core/classify/rules.py` and `core/utils/tokens.py` respectively. |
| `brain/anomaly.py` | `core/detect/anomaly.py` | Replace local `_money()` with `core.utils.money`. |
| `brain/goals.py` | `core/detect/goals.py` | Replace local `_money()` with `core.utils.money`. Reactor's reach into `goals._matches_pattern` (private API) — opportunity to either expose it as `match_pattern()` or absorb the call back into `goals.evaluate()` as the deep-dive doc suggests. |
| `brain/recurring.py` | `core/detect/recurring.py` | No structural change. |
| `brain/reactor.py` | `core/orchestration/reactor.py` | Imports rewrite. Logic unchanged. |
| `brain/narrator.py` | `core/output/narrator.py` | Replace local `_money()`. Pull the hard-coded 30% gap into `core/config.py`. Drop dead imports (`Counter`, `field`) per the deep-dive doc. |
| `brain/notifier.py` | `core/notify/macos.py` | Drop the unused `shlex` import per the deep-dive doc. |
| `brain/cli.py` | `core/cli/main.py` | Entry point string changes from `python -m brain.cli` to `python -m core.cli`. README, launchd plist, and CLAUDE.md update. |
| `brain/deep-dive/*.md` | `core/deep-dive/<thematic>/<name>.md` | Move alongside the code. |

### From `tax/`

| Source | Destination | Notes |
|---|---|---|
| `tax/__init__.py` | merged into `core/__init__.py` | Trivial. |
| `tax/migrate.py` | merged into `core/schema/migrate.py` | See §5. |
| `tax/sbi_parser.py` | `core/parsers/sbi_excel.py` | Rename communicates "this is the SBI Excel variant" — leaves room for `hdfc_excel.py`. |
| `tax/ingest_excel.py` | `core/ingest/excel.py` | Update the `from brain.reactor import on_new_payments` site to `from core.orchestration.reactor import on_new_payments`. The `except Exception: pass` swallow stays — that's a known design gap noted in the doc, out of scope here. |
| `tax/classifier.py` | `core/classify/manual.py` | Move `RuleBasedClassifier.learn`'s upsert into `core/classify/rules.py` so brain's `record_user_categorization` and tax's `learn` share one writer. |
| `tax/exporter.py` | `core/output/excel_export.py` | Drop the local `DB_PATH` literal — read `core.config.DB_PATH`. |
| `tax/routes.py` | `core/web/routes.py` | Drop `_db()`; use `core.schema.db.connect`. Drop the local `DB_PATH`. Imports rewrite. |
| `tax/templates.py` | `core/web/templates.py` | No code change. The XSS / `<dialog>` polyfill / fetch-error gaps documented in `tax/templates.md` stay as known issues — out of scope. |
| `tax/*.md` | `core/deep-dive/<thematic>/*.md` | Move alongside the code. |

---

## 4. Imports that need updating outside `core/`

These are the only call sites that touch `brain.*` or `tax.*` from outside the
two packages, so they're the full set of edits required to keep the project
running after the move.

| File | Current | After |
|---|---|---|
| `agent.py:369` | `from brain.reactor import on_new_payments` | `from core.orchestration.reactor import on_new_payments` |
| `dashboard.py:152` | `from brain.classifier import record_user_categorization` | `from core.classify.rules import record_user_categorization` |
| `dashboard.py:270` | `from brain.goals import create_goal` | `from core.detect.goals import create_goal` |
| `dashboard.py:335` | `from brain.config import TRIAGE_CONFIDENCE_THRESHOLD` | `from core.config import TRIAGE_CONFIDENCE_THRESHOLD` |
| `dashboard.py` (per `INTEGRATION.md`) | `from tax import migrate as tax_migrate` / `from tax.routes import router as tax_router` | `from core.schema import migrate as run_migrations` / `from core.web.routes import router` (and the redundant `tax_migrate.migrate()` call goes away — `core.schema.db.connect` already runs migrations on first connect) |
| `tests/test_parser.py` | n/a | parser tests rewrite `from brain.parser` → `from core.parsers.sms` |
| `tests/test_classifier.py:10` | `from brain import classifier, config` | `from core.classify import auto as classifier; from core import config` |
| `tests/test_anomaly.py:10` | `from brain import anomaly, recurring, config` | `from core.detect import anomaly, recurring; from core import config` |
| `tests/test_goals.py:11` | `from brain import goals` | `from core.detect import goals` |
| `tests/test_reactor.py:19` | `from brain import goals, reactor` | `from core.detect import goals; from core.orchestration import reactor` |
| `tests/test_narrator.py:12` | `from brain import narrator, goals, reactor` | `from core.output import narrator; from core.detect import goals; from core.orchestration import reactor` |
| `tests/test_tax.py:18` | `from tax import migrate, sbi_parser, ingest_excel, classifier, exporter` | `from core.schema import migrate; from core.parsers import sbi_excel as sbi_parser; from core.ingest import excel as ingest_excel; from core.classify import manual as classifier; from core.output import excel_export as exporter` |
| `launchd/com.you.upi-agent-story.plist` | `python -m brain.cli story weekly` | `python -m core.cli story weekly` |
| `README.md` + `CLAUDE.md` | references to `brain/` and `tax/` | rewrite paragraphs about layout, CLI invocation, "where new files go" table |
| `INTEGRATION.md` | the whole file | retire — its install steps reduce to "import is automatic; nothing to drop in" |

That's 11 source files + 4 docs + 1 plist. No further callers exist.

---

## 5. The merges that are not pure moves

Most of the work is `git mv` + import-rewrite. These four are the parts that
need actual code judgement; calling them out so they're not glossed over.

### 5.1 `core/schema/migrate.py` — merge of `brain/migrate.py` + `tax/migrate.py`

Today both files independently:

- add `payments.category_source` (brain calls it "owned by base agent",
  tax calls it "used by base + brain") — the `tax/migrate.md` doc explicitly
  says "implicit dependency direction that runs the wrong way"
- create `category_rules` with `IF NOT EXISTS` — race condition on first run

The merged file does both, in one ordered pass, with one truth about the
schema:

1. PRAGMA `foreign_keys = ON`.
2. Verify `payments` table exists (raise instead of `sys.exit(1)` per the
   tax migrate gap — the doc flags `sys.exit` from a library function as
   wrong, and we agree).
3. Add three columns to `payments` if missing: `source`, `txn_kind`,
   `category_source`.
4. `CREATE TABLE IF NOT EXISTS` for: `agent_events`, `goals`,
   `goal_status_cache`, `category_rules` (one definition only),
   `recurring_payments`, `buckets`, `tax_settings`.
5. Seed defaults for `tax_settings`.
6. Create the indexes from `tax/migrate.py` (`payments(ref_no)`,
   `payments(category)`, `payments(txn_kind)`).

Behaviour stays idempotent. Risk: the union of the two `category_rules`
schemas — confirm both sides expect identical columns before merging. If
they differ (the docs imply they're compatible but don't spell out the
schema), the merge needs a `PRAGMA table_info` reconciliation step.

### 5.2 `core/classify/rules.py` — new shared rule writer

Today brain's `record_user_categorization` writes both VPA and name-token
rows; tax's `RuleBasedClassifier.learn` writes both VPA and name rows. They
target the same table and they're conceptually the same operation. Extract
one `upsert_rule(conn, *, vpa, name, category)` and have both classifiers
call it. Two payoffs:

- A schema change to `category_rules` is one edit, not two.
- The brain doc's gap "name-token learning pollutes rules with personal
  names" can be fixed in one place once we want to address it.

### 5.3 `core/utils/money.py` — single Indian-rupee formatter

`_money()` exists in `brain/anomaly.py`, `brain/goals.py`, and
`brain/narrator.py` — three copies of the same `₹1,23,456` formatter (called
out explicitly in `brain/deep-dive/anomaly.md`). Pull it into
`core/utils/money.py` and import. No behaviour change.

### 5.4 `core/config.py` — absorb the literals that escaped the rule

The brain README says "no magic numbers buried in code" and the deep-dive
docs flag the violations:

- `brain/classifier.py`: hardcoded morning-hour band (07:00–11:00),
  small-amount band (₹50–₹400), large-amount thresholds (₹5,000 / ₹10,000),
  round-amount check (`amount % 100 == 0`)
- `brain/narrator.py`: hardcoded 30% gap for calendar correlations
- `brain/notifier.py`: hardcoded 240-character truncation
- `tax/`: `DB_PATH` hardcoded in 4 files

This is a tidy moment to fold them all into `core/config.py` so the
discipline the README claims actually holds.

---

## 6. Risks, and what stays out of scope

- **Schema reconciliation for `category_rules`.** Both packages define this
  table; the merged `migrate.py` needs to be sure the column sets match
  exactly. If they don't, the first migration to run "wins" today —
  silently. The merge surfaces this and forces a single definition.
- **`tax/ingest_excel.py`'s silent brain-failure swallow** (`except
  Exception: pass`) is preserved as-is. The deep-dive doc flags it as a
  gap; fixing it is its own change.
- **`tax/templates.py` XSS** is preserved as-is. Documented gap, separate
  change.
- **No SMS-side ingest move.** `agent.py` still owns SMS ingest. Moving it
  into `core/ingest/sms.py` is a sensible follow-up but is a bigger
  refactor (it touches macOS Messages access, Calendar enrichment, and the
  state file). Not part of this consolidation.
- **No dashboard route move.** The base `/`, `/feed`, `/triage` routes in
  `dashboard.py` would naturally live in `core/web/routes.py` next to the
  tax routes. That's a sensible follow-up; not part of this
  consolidation.
- **`__init__.py` explicit exports.** Each thematic subfolder gets a
  `__init__.py` that re-exports the public surface used by tests
  (e.g. `core.detect.__init__` re-exports `anomaly`, `goals`, `recurring`)
  so test imports stay short. Worth deciding upfront whether to expose
  symbols at the package level or keep `from core.detect.anomaly import …`
  style. Recommend the former for tests, the latter for production code.
- **Process name in `brain.reactor` logger.** Loggers named `brain.reactor`
  and `brain.cli` show up in any consumer that configures logging; renaming
  to `core.orchestration.reactor` and `core.cli` is correct but anyone
  filtering by logger name needs to update.

---

## 7. Suggested execution order

If/when you decide to actually do this:

1. Create `core/` skeleton with empty `__init__.py` files and the thematic
   subfolders, but copy nothing yet.
2. Move + rename files in this order so each step keeps the project
   importable:
   1. `core/config.py`
   2. `core/utils/{money,tokens}.py` (extract from brain originals)
   3. `core/schema/{db,migrate}.py` (merged migrate)
   4. `core/parsers/{sms,sbi_excel}.py`
   5. `core/classify/{rules,auto,manual}.py`
   6. `core/detect/{anomaly,goals,recurring}.py`
   7. `core/output/{narrator,excel_export}.py`
   8. `core/notify/macos.py`
   9. `core/orchestration/reactor.py`
   10. `core/web/{routes,templates}.py`
   11. `core/cli/main.py`
3. Update `agent.py`, `dashboard.py`, every test file, the launchd plist.
4. Delete `brain/` and `tax/` folders.
5. Run `pytest tests/ -v` — the existing 74 tests (60 brain + 14 tax) are
   the regression suite for this refactor. No new tests required; if any
   fail, the move broke an import or assumption.
6. Rewrite README.md, CLAUDE.md; retire INTEGRATION.md.

End state: one package, one set of constants, one connection factory, one
migration runner, one rule-store writer, one rupee formatter — and brain +
tax behaviours both intact.
