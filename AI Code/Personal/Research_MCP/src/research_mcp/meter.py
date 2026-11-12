"""Observable LLM wrapper. Every model call in the system goes through MeteredClient.

Dual storage per call:
  - JSONL audit file (audit/YYYY-MM-DD.jsonl) — one line per call, kept forever
  - SQLite model_calls table — for fast per-run queries
"""
from __future__ import annotations

import os
from datetime import date, datetime
from pathlib import Path
from typing import Any

from anthropic import AsyncAnthropic

from .contracts import ModelCallRecord
from .pricing import compute_cost

_REPO_ROOT = Path(__file__).parent.parent.parent
AUDIT_DIR = _REPO_ROOT / "audit"


def _audit_path() -> Path:
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    return AUDIT_DIR / f"{date.today().isoformat()}.jsonl"


class MeteredClient:
    def __init__(self, db_path: str | Path, api_key: str | None = None):
        self._db_path = str(db_path)
        self._client = AsyncAnthropic(api_key=api_key or os.environ.get("ANTHROPIC_API_KEY"))

    async def messages_create(
        self,
        *,
        model: str,
        stage: str,
        run_id: str,
        **kwargs: Any,
    ):
        """Wrap anthropic.messages.create with metering. Same kwargs as the SDK."""
        started_at = datetime.utcnow()
        status = "success"
        message = None
        try:
            message = await self._client.messages.create(model=model, **kwargs)
            return message
        except Exception:
            status = "error"
            raise
        finally:
            tokens_in = message.usage.input_tokens if message else 0
            tokens_out = message.usage.output_tokens if message else 0
            cost = compute_cost(model, tokens_in, tokens_out, date.today())

            record = ModelCallRecord(
                timestamp=started_at,
                model=model,
                stage=stage,  # type: ignore[arg-type]
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                cost_usd=cost,
                run_id=run_id,
                status=status,  # type: ignore[arg-type]
            )
            await self._persist(record)

    async def _persist(self, record: ModelCallRecord) -> None:
        # JSONL audit — append, never overwrite
        try:
            with open(_audit_path(), "a") as fh:
                fh.write(record.model_dump_json() + "\n")
        except OSError:
            pass

        # SQLite
        try:
            import aiosqlite  # local import to keep startup fast when DB not configured

            async with aiosqlite.connect(self._db_path) as db:
                await db.execute(
                    """INSERT OR IGNORE INTO model_calls
                       (timestamp, model, stage, tokens_in, tokens_out, cost_usd, run_id, status)
                       VALUES (?,?,?,?,?,?,?,?)""",
                    (
                        record.timestamp.isoformat(),
                        record.model,
                        record.stage,
                        record.tokens_in,
                        record.tokens_out,
                        record.cost_usd,
                        record.run_id,
                        record.status,
                    ),
                )
                await db.execute(
                    "UPDATE runs SET cost_usd = cost_usd + ? WHERE run_id = ?",
                    (record.cost_usd, record.run_id),
                )
                await db.commit()
        except Exception:
            pass
