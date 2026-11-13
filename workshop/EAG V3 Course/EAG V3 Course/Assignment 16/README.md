# Personal Watchlist Assistant

A local public-page screener: establish a baseline, record relevant or ignored changes, preserve unanswered questions, and write an evidence-backed Markdown brief. This implements the watchlist slice of `PLAN.md`; the five-channel assignment, liveness alarm and course bug-fix PR remain separate.

The assumed watch asks which new stable Python releases need compatibility review. It checks two selected Python.org pages no more often than daily, allows four total page-fetch attempts per UTC day and two million bytes per page, and spends $0. Attempts that fail or are interrupted still count. Running a command does one check; no background scheduler is installed.

From this folder:

```sh
uv run --python 3.11.15 python -m unittest discover -s tests -v
uv run --python 3.11.15 python -m watchlist check
uv run --python 3.11.15 python -m watchlist report
```

`check` fetches due pages and writes `.watchlist/brief.md`. `report` refreshes that brief without fetching. The SQLite database `.watchlist/watch.db` stores full source versions, decisions, observation times and questions. The brief shows changed evidence, ranked findings, ignore reasons, failures and each source's last successful capture. Return codes: 0 for a completed command (including not-due or capped checks), 1 for capture/assessment failure, 2 for invalid settings or commands.

Try the complete journey without network access:

```sh
uv run --python 3.11.15 python -m watchlist --state .watchlist-demo demo
uv run --python 3.11.15 python -m watchlist --state .watchlist-demo answer 4 --decision finding --answer 'Yes, evaluate the preview locally.'
```

These are separate processes: the answer completes item 4 from the first process. The demo includes a baseline, relevant release, repeated announcement, unrelated edit, pending preview, unchanged capture and fetch failure. Its report is labelled SIMULATED, and real checks refuse to reuse demo state.

Edit `watch.toml` for your URLs, question and limits, and `rules.csv` for the statements to recognise. A rule uses a regular expression (a text-matching pattern), importance 1–3, an interpretation, a suggested local task and an optional clarification question. Changing a subscription requires a new `--state` directory so old evidence keeps its original meaning. Reports include the question; the actual relevance test is the explicit rule, not free-form language understanding.

This version uses deterministic rules and your answers; it makes no model calls and refuses a nonzero spending ceiling. Unmatched edits are recorded as weak/unrelated, so configure rules for your question before relying on it. It recognises repeated matched statements, not arbitrary paraphrases. Semantic model assessment would need the AI OS gateway and separately confirmed budgets; no trunk changes were made here.

Answer any pending item locally with `answer ID --decision finding` or `--decision ignored`, plus `--answer 'your reasoning'`. An answer settles only that item; change the rules in a new watch to change future behaviour. Suggestions never send messages, create external tasks or execute page instructions. Source pages cannot modify settings. Only selected public HTTPS pages are fetched, redirects are refused, and JavaScript rendering is unsupported. No credentials are needed.

State and reports under `.watchlist*/` are ignored by Git. Keep any custom state directory out of commits too. There are no third-party dependencies; HTTP capture, HTML parsing, storage and process locking use Python's standard library on macOS/Linux. Concurrent writers are refused rather than racing over a baseline. Review changes and real-page output before committing.
