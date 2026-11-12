# podcasts.yaml — Technical Documentation

**Last updated:** 2026-05-10
**Lines of code:** 15
**Language:** YAML

---

## What This File Does (Plain English)

Defines the list of podcast RSS feeds the application knows about. Both the CLI (`orchestrator.py` when run directly) and the Streamlit UI (`app.py`) read this file at startup to populate the podcast selector. Editing this file is the only supported way to add or remove podcasts — there is no UI for it.

---

## Structure

```yaml
podcasts:
  - name: "<Display name shown in the UI>"
    rss:  "<Full RSS feed URL>"
```

Each entry requires exactly two keys: `name` and `rss`. The `name` is used in filenames (slugged to alphanumeric) and as display text. The `rss` URL is passed directly to `feedparser` to fetch the latest episode.

---

## Current Contents (as of last update)

| Name | RSS Host |
|---|---|
| Lex Fridman Podcast | lexfridman.com |
| The Tim Ferriss Show | feeds.megaphone.fm |
| Acquired | feeds.simplecast.com |
| My First Million | feeds.megaphone.fm |
| Huberman Lab | feeds.megaphone.fm |

---

## How It Is Read

`orchestrator.py:load_podcasts()` opens this file with `yaml.safe_load()` and returns the `podcasts` list. If the file does not exist, it returns an empty list — the UI then halts with an error message rather than crashing.

---

## Honest Gaps and Risks

- No validation of the `rss` field. A malformed URL, a dead feed, or an RSS feed with no audio enclosures will only surface as an error when the pipeline runs, not when the file is loaded.
- The `name` field is used in output file slugs. Names with only non-alphanumeric characters (e.g. `"!!! Test !!!"`) would produce an empty slug, which the `_slug()` function in `orchestrator.py` catches with a fallback to `"file"` — but the output filename would be unhelpful.
- There is no `episode_limit` or `offset` field — the pipeline always takes `feed.entries[0]`, the first (most recent) entry in the RSS feed. There is no way to pick a specific episode from the config.

---

## Developer Notes

- To add a podcast: append a `- name: / rss:` block and reload the app (Streamlit auto-reloads on file changes in dev mode).
- RSS URLs can drift. Megaphone, Simplecast, and direct feeds occasionally change; the error will surface at runtime as an `RSSError`.
- The file is read fresh on every Streamlit page load (inside `load_podcasts()` which is called at module scope in `app.py`). Edits take effect without restarting the server.
