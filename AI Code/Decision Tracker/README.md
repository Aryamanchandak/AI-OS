# Decision Tracker

Local-first decision capture, immutable event history, calibration, watcher alerts, recall, graph analysis, MCP fan-in, and a read-only dashboard.

## Run

```bash
uv sync --all-extras
uv run dt log "A falsifiable claim" --author AC2
uv run dt interrogate DR-2026-0001
uv run dt open
uv run dt retrospective
uv run dt watch
uv run dt verify
uv run dt void DR-2026-0001 --reason "abandoned after 14 days"
uv run dt supersede DR-2026-0001 DR-2026-0002 --reason "updated view"
uv run streamlit run src/decision_tracker/dashboard.py
uv run decision-tracker-mcp
uv run dt transcribe voice-note.m4a
uv run dt telegram-send CHAT_ID "Decision captured"
uv run dt whatsapp-send PHONE_NUMBER "Decision captured"
```

Set `DT_DB_PATH` to override `.decision-tracker/decision_tracker.db`. Structured drafts can be passed as JSON: `uv run dt log draft.json`. Commit only after the admission gate clears.

`FORECAST` records can only be resolved with `--automated --resolver-source adapter:NAME`; human-close remains available for other classes. Amendments are append-only through the service API, require a reason, and cannot change locked claim or reasoning fields.

Telegram (`TELEGRAM_BOT_TOKEN`) and WhatsApp Cloud (`WHATSAPP_ACCESS_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID`) require credentials. Voice uses local `faster-whisper`; its model is downloaded on first use. Market feeds require a configured observation adapter and otherwise degrade to human-close alerts. Never submit MNPI: `source_classification=blocked` is rejected without persistence. This tool is personal and non-firm; compliance approval remains the user's responsibility.
