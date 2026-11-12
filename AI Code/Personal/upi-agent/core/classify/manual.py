"""
Classifier protocol + two implementations for manual/UI-driven classification.

RuleBasedClassifier: deterministic rule lookup against the category_rules
  table. Built up by every triage-queue confirmation. No network calls ever.

LocalLLMClassifier: posts to a user-configured local LLM endpoint
  (Ollama, llama.cpp, LM Studio, vLLM — all expose OpenAI-compatible
  /v1/chat/completions). Falls back to RuleBasedClassifier if endpoint
  is unset or unreachable. Cloud is never an option.

The pipeline:
  1. Auto-classify any row where rules give confidence >= CONFIDENCE_AUTO_APPLY.
  2. Everything else hits the triage queue at /tax.
  3. In the queue, the active classifier (rules OR rules+LLM) provides a
     suggestion for one-click confirmation.
  4. User confirmation calls .learn() to update category_rules.
"""
from __future__ import annotations

import json
import sqlite3
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Optional, Protocol, List

from core import config
from core.classify.rules import upsert_rule


@dataclass
class Suggestion:
    bucket: Optional[str]
    confidence: float
    reason: str


class Classifier(Protocol):
    def suggest(self, payment: dict) -> Suggestion: ...
    def learn(self, payment: dict, bucket: str) -> None: ...


# ---------------------------------------------------------------------------
# Rule-based: deterministic, no network, reads/writes category_rules
# ---------------------------------------------------------------------------

class RuleBasedClassifier:
    """
    Lookup order (first hit wins, return immediately):
      1. Exact VPA in category_rules                     → conf 1.0
      2. Exact name in category_rules                    → conf 0.9
      3. Substring overlap on name                       → conf 0.6
      4. Same-merchant pattern in past payments.category → conf 0.5
      5. Calendar event title keyword (planned)          → conf 0.3
    """

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def suggest(self, payment: dict) -> Suggestion:
        c = self.conn.cursor()
        vpa = payment.get("counterparty_vpa")
        name = payment.get("counterparty_name")

        if vpa:
            row = c.execute(
                "SELECT category, hits FROM category_rules "
                "WHERE key_kind='vpa' AND key_value=? "
                "ORDER BY hits DESC LIMIT 1",
                (vpa,),
            ).fetchone()
            if row:
                return Suggestion(row[0], 1.0,
                                  f"Exact VPA match ({row[1]} prior hits)")

        if name:
            row = c.execute(
                "SELECT category, hits FROM category_rules "
                "WHERE key_kind='name' AND key_value=? "
                "ORDER BY hits DESC LIMIT 1",
                (name,),
            ).fetchone()
            if row:
                return Suggestion(row[0], 0.9,
                                  f"Exact merchant name match ({row[1]} prior hits)")

        if name:
            row = c.execute(
                "SELECT category, hits, key_value FROM category_rules "
                "WHERE key_kind='name' "
                "  AND (? LIKE '%' || key_value || '%' "
                "    OR key_value LIKE '%' || ? || '%') "
                "ORDER BY hits DESC LIMIT 1",
                (name, name),
            ).fetchone()
            if row:
                return Suggestion(row[0], 0.6,
                                  f"Substring match: '{row[2]}'")

        if vpa or name:
            row = c.execute("""
                SELECT category, COUNT(*) AS n
                FROM payments
                WHERE category IS NOT NULL AND category != ''
                  AND ((counterparty_vpa = ? AND counterparty_vpa IS NOT NULL)
                    OR (counterparty_name = ? AND counterparty_name IS NOT NULL))
                GROUP BY category
                ORDER BY n DESC
                LIMIT 1
            """, (vpa, name)).fetchone()
            if row and row[1] >= 2:
                return Suggestion(row[0], 0.5,
                                  f"Pattern in {row[1]} past txns")

        return Suggestion(None, 0.0, "No matching rule")

    def learn(self, payment: dict, bucket: str) -> None:
        """Upsert a rule per (vpa, name) → bucket. Called after every confirm."""
        vpa = payment.get("counterparty_vpa")
        name = payment.get("counterparty_name")
        if vpa:
            upsert_rule(self.conn, key_kind="vpa", key_value=vpa, category=bucket)
        if name:
            upsert_rule(self.conn, key_kind="name", key_value=name, category=bucket)
        self.conn.commit()


# ---------------------------------------------------------------------------
# Local LLM: rules first, LLM only if rules low-confidence and endpoint set
# ---------------------------------------------------------------------------

class LocalLLMClassifier:
    """
    Wraps a local LLM behind the rule-based classifier.

    Behavior:
      1. Run the rule-based suggestion first.
      2. If rule confidence >= CONFIDENCE_AUTO_APPLY, accept it (no LLM call).
      3. If endpoint is empty/unreachable, return rule suggestion (graceful).
      4. Otherwise, ask the LLM. If it returns a known bucket, return it
         with confidence 0.7. If not, return the rule suggestion.

    Endpoint contract: OpenAI-compatible POST /v1/chat/completions.
    Supported by Ollama, llama.cpp server, LM Studio, vLLM. Nothing leaves
    the user's machine.
    """

    def __init__(self, conn: sqlite3.Connection,
                 endpoint: str = "", model: str = "",
                 buckets: Optional[List[str]] = None,
                 timeout: float = 10.0):
        self.conn = conn
        self.endpoint = endpoint.rstrip("/")
        self.model = model
        self.buckets = buckets or []
        self.timeout = timeout
        self.fallback = RuleBasedClassifier(conn)

    def suggest(self, payment: dict) -> Suggestion:
        rule_sugg = self.fallback.suggest(payment)
        if rule_sugg.confidence >= config.CONFIDENCE_AUTO_APPLY:
            return rule_sugg
        if not self.endpoint or not self.buckets:
            return rule_sugg

        try:
            data = json.dumps({
                "model": self.model,
                "messages": [
                    {"role": "system", "content":
                     "You classify Indian bank transactions into one of "
                     "the listed buckets. Reply with ONLY the bucket name, "
                     "verbatim. If no bucket fits, reply 'unknown'."},
                    {"role": "user", "content": self._build_prompt(payment)},
                ],
                "temperature": 0.0,
                "max_tokens": 16,
            }).encode()
            req = urllib.request.Request(
                f"{self.endpoint}/v1/chat/completions",
                data=data,
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                result = json.loads(resp.read())
                guess = result["choices"][0]["message"]["content"].strip()
        except (urllib.error.URLError, urllib.error.HTTPError,
                KeyError, json.JSONDecodeError, TimeoutError, OSError):
            return rule_sugg

        bucket_map = {b.lower(): b for b in self.buckets}
        if guess.lower() in bucket_map:
            return Suggestion(bucket_map[guess.lower()], 0.7,
                              f"Local LLM ({self.model})")
        return rule_sugg

    def learn(self, payment: dict, bucket: str) -> None:
        self.fallback.learn(payment, bucket)

    def _build_prompt(self, p: dict) -> str:
        return (
            f"Transaction:\n"
            f"  Direction: {p.get('direction')}\n"
            f"  Amount: ₹{p.get('amount')}\n"
            f"  Counterparty: {p.get('counterparty_name') or '?'}\n"
            f"  VPA: {p.get('counterparty_vpa') or '?'}\n"
            f"  Narration: {p.get('narration') or p.get('raw_text') or '?'}\n"
            f"  Kind: {p.get('txn_kind')}\n\n"
            f"Available buckets: {', '.join(self.buckets)}\n\n"
            f"Reply with one bucket name only."
        )


# ---------------------------------------------------------------------------
# Factory: read tax_settings, return the right classifier
# ---------------------------------------------------------------------------

def get_active_classifier(conn: sqlite3.Connection) -> Classifier:
    c = conn.cursor()
    settings = dict(c.execute("SELECT key, value FROM tax_settings").fetchall())
    if (settings.get("mode") == "ai"
            and settings.get("llm_endpoint")
            and settings["llm_endpoint"].strip()):
        buckets = [r[0] for r in c.execute(
            "SELECT name FROM buckets WHERE archived_at IS NULL"
        )]
        return LocalLLMClassifier(
            conn,
            endpoint=settings["llm_endpoint"],
            model=settings.get("llm_model", "") or "",
            buckets=buckets,
        )
    return RuleBasedClassifier(conn)
