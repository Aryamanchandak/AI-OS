# US-10 Handoff — Part 1: Complete Source Truth

## Purpose of this document
This is a raw, complete factual dump of every file, contract, and structure
an AI coding assistant needs to implement US-10 (`send()` orchestrator) in
the GLC v1 WhatsApp adapter. Nothing is paraphrased or summarised — exact
source is reproduced in full. Part 2 contains the task specification and
design decisions.

---

## 1. Project identity

- **Project:** GLC v1 — Gateway for LLMs and Channels
- **Course:** EAG V3, Session 11, The School of AI
- **Upstream repo:** `https://github.com/theschoolofai/glc_v1` (MIT, Python 3.11 + FastAPI)
- **Team fork:** `https://github.com/rraghu214/glc_v1_whatsapp`
- **Working branch:** `integration` (all team PRs target this; final PR targets upstream `main`)
- **Task branch:** `feature/us10-send-orchestrator` (already created, branched from `integration`)
- **Developer:** Aryaman Chandak, GitHub: `Aryamanchandak`
- **Group:** Group WhatsApp (G21)
- **Owned path:** `glc/channels/catalogue/whatsapp/` and everything under it — nothing else

---

## 2. Repo layout

```
glc_v1_whatsapp/
├── glc/
│   ├── channels/
│   │   ├── base.py               ← ABC — READ ONLY
│   │   ├── envelope.py           ← typed envelopes — READ ONLY
│   │   └── catalogue/
│   │       └── whatsapp/         ← ENTIRE OWNED PATH
│   │           ├── adapter.py    ← main file to edit
│   │           ├── schemas.py    ← optional pydantic wrappers
│   │           ├── __init__.py
│   │           ├── README.md
│   │           ├── tests/
│   │           │   └── test_twilio_path.py  ← US-11, self-authored, inside owned path
│   │           └── help_docs/
│   │               ├── Handoff.md
│   │               ├── pick_my_task.md
│   │               └── US1_meta_wiring/
│   ├── security/
│   │   ├── pairing.py            ← READ ONLY
│   │   ├── trust_level.py        ← READ ONLY
│   │   └── allowlists.py         ← READ ONLY
│   └── voice/                    ← not our concern
├── tests/
│   └── channels/
│       ├── test_whatsapp.py      ← FIXED, READ ONLY, Meta-only — confirmed does NOT exist yet
│       └── mocks/
│           └── whatsapp_mock.py  ← FIXED, READ ONLY
├── docs/
├── daemon/
├── scripts/
│   ├── check_pr_boundaries.py
│   ├── scorecard.py
│   └── validate_*.py
├── .github/workflows/
│   ├── ci.yml
│   └── adapter-pr.yml
├── pyproject.toml
├── uv.lock
├── README.md
├── GROUPS.md
└── VALIDATION.md
```

**Critical note on tests:** There is NO `tests/channels/test_whatsapp.py` yet.
The Handoff references it as "fixed" but it does not exist in the repo at this
point. The only test file for this slot is self-authored inside the owned path:
`glc/channels/catalogue/whatsapp/tests/test_twilio_path.py` (US-11).

---

## 3. Tech stack

- Python 3.11 (managed via uv)
- FastAPI (HTTP/WebSocket gateway)
- Pydantic v2 (`extra="forbid"` on all envelope models — cannot add fields)
- uv as package manager (`uv sync` to install, `uv run glc serve` to start on port 8111)
- pytest + pytest-asyncio for tests
- ruff for linting, mypy for type checking
- httpx (async HTTP client — already in deps at `httpx==0.28.1`)
- twilio SDK (`twilio.request_validator.RequestValidator`)
- **No** LangChain, CrewAI, AutoGen, or Open Interpreter

---

## 4. `glc/channels/base.py` — complete source

```python
"""ChannelAdapter ABC. Every adapter under glc/channels/catalogue/<name>/
subclasses this. Two methods: on_message (inbound) and send (outbound).
Both speak the typed envelopes from envelope.py."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from glc.channels.envelope import ChannelMessage, ChannelReply


class ChannelAdapter(ABC):
    name: str = ""

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self.config = config or {}

    @abstractmethod
    async def on_message(self, raw: Any) -> ChannelMessage:
        """Translate a native wire-format event into a ChannelMessage.

        The wire format is channel-specific (Telegram Update, Discord
        gateway dispatch, Slack event payload, ...). The translation
        includes classifying the trust level via
        glc.security.trust_level.classify().
        """
        raise NotImplementedError("Group assignment: implement on_message and send in this adapter.")

    @abstractmethod
    async def send(self, reply: ChannelReply) -> Any:
        """Translate a ChannelReply into a native wire-format payload and
        dispatch it. Returns whatever the native API returns (often the
        sent-message id, used for thread bookkeeping)."""
        raise NotImplementedError("Group assignment: implement on_message and send in this adapter.")
```

**Key facts from this file:**
- `on_message` return type is `ChannelMessage` (not `ChannelMessage | None`) in the ABC,
  but `adapter.py` overrides with `ChannelMessage | None` using `# type: ignore[override]`
- `config` is a plain dict, populated at init — `self.config.get("mock")` is the test intercept
- No other methods on the base class

---

## 5. `glc/channels/envelope.py` — complete source

```python
"""Channel envelope — the typed contract between adapters and the agent
runtime. Lecture §8 documents the shape. Adapters import these types and
the test suite asserts adapter output conforms.
"""
from __future__ import annotations
from datetime import datetime
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field

TrustLevel = Literal["owner_paired", "user_paired", "untrusted"]

class Attachment(BaseModel):
    """A non-text payload attached to a message. `ref` is either an
    art:... handle that the gateway can resolve to bytes via the artifact
    store, or an external URL the receiving side can fetch."""
    kind: Literal["image", "audio", "video", "file", "location"]
    ref: str
    mime: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    model_config = ConfigDict(extra="forbid")

class ChannelMessage(BaseModel):
    channel: str
    channel_user_id: str
    user_handle: str
    text: str | None = None
    attachments: list[Attachment] = Field(default_factory=list)
    voice_audio_ref: str | None = None
    thread_id: str | None = None
    trust_level: TrustLevel
    arrived_at: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)
    model_config = ConfigDict(extra="forbid")

class ChannelReply(BaseModel):
    channel: str
    channel_user_id: str
    text: str | None = None
    attachments: list[Attachment] = Field(default_factory=list)
    voice_audio_ref: str | None = None
    thread_id: str | None = None
    model_config = ConfigDict(extra="forbid")
```

**Critical facts from this file:**
- `ChannelReply` has `extra="forbid"` — you CANNOT add a `provider` field to it
- `ChannelReply.channel_user_id` is the recipient phone number (e.g. `"919999990000"`)
- `ChannelReply.text` can be `None` — `send()` must handle this (build functions raise ValueError on None text)
- `ChannelMessage.metadata` is a plain dict — this is where `{"provider": "meta"}` or `{"provider": "twilio"}` lives
- No `extra` fields allowed on either model under any circumstances

---

## 6. `glc/security/pairing.py` — complete source

```python
"""DM pairing flow.

A rotating six-digit code is issued per pairing request and expires after
five minutes. The owner enters the code through the WebUI to confirm.
Per-pairing trust levels live in ~/.glc/pairings.sqlite: owner_paired for
the installation owner, user_paired for explicitly-paired users.

The pairing store is sqlite-backed so it survives restarts.
"""

from __future__ import annotations

import os
import secrets
import sqlite3
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

DEFAULT_DIR = Path(os.path.expanduser("~/.glc"))
CODE_TTL_SECONDS = 5 * 60


def _resolve_path() -> str:
    return os.getenv("GLC_PAIRING_DB", str(DEFAULT_DIR / "pairings.sqlite"))


@contextmanager
def _conn():
    p = _resolve_path()
    Path(p).parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(p, isolation_level=None)
    c.row_factory = sqlite3.Row
    try:
        yield c
    finally:
        c.close()


@dataclass
class PairingRecord:
    channel: str
    channel_user_id: str
    user_handle: str
    trust_level: str       # "owner_paired" | "user_paired"
    paired_at: float       # unix timestamp


class PairingStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._init_schema()

    def _init_schema(self) -> None:
        with _conn() as c:
            c.execute("""CREATE TABLE IF NOT EXISTS pairings (
                    channel TEXT NOT NULL,
                    channel_user_id TEXT NOT NULL,
                    user_handle TEXT,
                    trust_level TEXT NOT NULL,
                    paired_at REAL NOT NULL,
                    PRIMARY KEY (channel, channel_user_id)
                )""")
            c.execute("""CREATE TABLE IF NOT EXISTS pending_codes (
                    code TEXT PRIMARY KEY,
                    channel TEXT NOT NULL,
                    channel_user_id TEXT NOT NULL,
                    user_handle TEXT,
                    requested_trust_level TEXT NOT NULL,
                    expires_at REAL NOT NULL
                )""")

    def issue_code(self, channel: str, channel_user_id: str,
                   user_handle: str = "", *, requested_trust_level: str = "user_paired"
    ) -> tuple[str, float]:
        code = f"{secrets.randbelow(1_000_000):06d}"
        expires_at = time.time() + CODE_TTL_SECONDS
        with _conn() as c:
            c.execute(
                """INSERT OR REPLACE INTO pending_codes
                   (code, channel, channel_user_id, user_handle,
                    requested_trust_level, expires_at) VALUES (?,?,?,?,?,?)""",
                (code, channel, channel_user_id, user_handle, requested_trust_level, expires_at),
            )
        return code, expires_at

    def confirm_code(self, code: str) -> PairingRecord | None:
        with _conn() as c:
            row = c.execute("SELECT * FROM pending_codes WHERE code=?", (code,)).fetchone()
            if row is None:
                return None
            if row["expires_at"] < time.time():
                c.execute("DELETE FROM pending_codes WHERE code=?", (code,))
                return None
            paired_at = time.time()
            c.execute(
                """INSERT OR REPLACE INTO pairings
                   (channel, channel_user_id, user_handle, trust_level, paired_at)
                   VALUES (?,?,?,?,?)""",
                (row["channel"], row["channel_user_id"], row["user_handle"],
                 row["requested_trust_level"], paired_at),
            )
            c.execute("DELETE FROM pending_codes WHERE code=?", (code,))
            return PairingRecord(
                channel=row["channel"], channel_user_id=row["channel_user_id"],
                user_handle=row["user_handle"] or "", trust_level=row["requested_trust_level"],
                paired_at=paired_at,
            )

    def lookup(self, channel: str, channel_user_id: str) -> PairingRecord | None:
        """Returns PairingRecord if this user is paired, None if not."""
        with _conn() as c:
            row = c.execute(
                "SELECT * FROM pairings WHERE channel=? AND channel_user_id=?",
                (channel, channel_user_id),
            ).fetchone()
            if row is None:
                return None
            return PairingRecord(
                channel=row["channel"], channel_user_id=row["channel_user_id"],
                user_handle=row["user_handle"] or "", trust_level=row["trust_level"],
                paired_at=float(row["paired_at"]),
            )

    def owners(self, channel: str | None = None) -> list[PairingRecord]:
        """Returns all owner_paired records, optionally filtered by channel."""
        q = "SELECT * FROM pairings WHERE trust_level='owner_paired'"
        args: list = []
        if channel:
            q += " AND channel=?"
            args.append(channel)
        with _conn() as c:
            return [
                PairingRecord(
                    channel=r["channel"], channel_user_id=r["channel_user_id"],
                    user_handle=r["user_handle"] or "", trust_level=r["trust_level"],
                    paired_at=float(r["paired_at"]),
                )
                for r in c.execute(q, args).fetchall()
            ]

    def all_pairings(self) -> list[PairingRecord]:
        with _conn() as c:
            rows = c.execute("SELECT * FROM pairings").fetchall()
            return [
                PairingRecord(
                    channel=r["channel"], channel_user_id=r["channel_user_id"],
                    user_handle=r["user_handle"] or "", trust_level=r["trust_level"],
                    paired_at=float(r["paired_at"]),
                )
                for r in rows
            ]

    def revoke(self, channel: str, channel_user_id: str) -> bool:
        with _conn() as c:
            cur = c.execute(
                "DELETE FROM pairings WHERE channel=? AND channel_user_id=?",
                (channel, channel_user_id),
            )
            return cur.rowcount > 0

    def force_pair_owner(self, channel: str, channel_user_id: str,
                         user_handle: str = "owner") -> PairingRecord:
        """Bootstrap the first owner identity. Not exposed through HTTP."""
        paired_at = time.time()
        with _conn() as c:
            c.execute(
                """INSERT OR REPLACE INTO pairings
                   (channel, channel_user_id, user_handle, trust_level, paired_at)
                   VALUES (?,?,?,?,?)""",
                (channel, channel_user_id, user_handle, "owner_paired", paired_at),
            )
        return PairingRecord(channel=channel, channel_user_id=channel_user_id,
                             user_handle=user_handle, trust_level="owner_paired",
                             paired_at=paired_at)


_singleton: PairingStore | None = None


def get_pairing_store() -> PairingStore:
    global _singleton
    if _singleton is None:
        _singleton = PairingStore()
    return _singleton
```

**Key facts from this file:**
- `get_pairing_store()` returns a process-level singleton backed by SQLite at `~/.glc/pairings.sqlite`
- `lookup(channel, channel_user_id)` → `PairingRecord | None` — the guard check for `send()`
- `owners(channel)` → `list[PairingRecord]` — used by `on_message` to classify trust
- `PairingRecord.trust_level` is a plain string: `"owner_paired"` or `"user_paired"`
- `force_pair_owner()` is the bootstrap method tests use to register a user before testing `send()`
- The store is sqlite-backed and survives restarts — the provider cache in contrast is in-memory only

---

## 7. `glc/channels/catalogue/whatsapp/adapter.py` — complete current source

This is the exact file as of commit `4eb8d9c` on `integration`
("docs: update US-9 and US-10 spec with provider cache design"):

```python
"""WhatsApp adapter for Twilio Sandbox and Meta Cloud API."""
from __future__ import annotations
import hashlib
import hmac
import json
import os
from datetime import UTC, datetime
from typing import Any
from urllib.parse import parse_qs
from twilio.request_validator import RequestValidator
from glc.channels.base import ChannelAdapter
from glc.channels.envelope import ChannelMessage, ChannelReply
from glc.security.allowlists import allowed
from glc.security.pairing import get_pairing_store
from glc.security.trust_level import TrustLevel, classify


def verify_meta_signature(raw_body: bytes, headers: dict) -> bool:
    """Verify Meta X-Hub-Signature-256 (HMAC-SHA256) over raw_body."""
    secret = os.environ.get("WHATSAPP_APP_SECRET", "")
    sig_header = headers.get("x-hub-signature-256") or headers.get("X-Hub-Signature-256") or ""
    if not secret or not sig_header.startswith("sha256="):
        return False
    expected = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, sig_header.removeprefix("sha256="))


def verify_twilio_signature(url: str, params: dict, signature: str, auth_token: str) -> bool:
    """Verifies the Twilio signature of an incoming webhook."""
    if not auth_token or not signature:
        return False
    try:
        validator = RequestValidator(auth_token)
        return validator.validate(url, params, signature)
    except Exception:
        return False


def parse_meta_payload(body: dict) -> dict[str, Any] | None:
    try:
        value = body["entry"][0]["changes"][0]["value"]
    except (KeyError, IndexError):
        return None
    messages = value.get("messages")
    if not messages:
        return None
    msg = messages[0]
    contacts = value.get("contacts") or []
    profile_name = contacts[0].get("profile", {}).get("name") if contacts else None
    text: str | None = None
    if msg.get("type") == "text":
        text = msg.get("text", {}).get("body")
    try:
        return {
            "from_id": msg["from"],
            "text": text,
            "message_id": msg["id"],
            "timestamp": msg["timestamp"],
            "profile_name": profile_name,
        }
    except (KeyError, TypeError):
        return None


def parse_twilio_payload(payload: dict, received_at: datetime) -> dict[str, Any] | None:
    """US-7: Parse Twilio Sandbox webhook payload."""
    from_id = payload.get("WaId")
    if not from_id:
        return None
    text = payload.get("Body") if payload.get("NumMedia", "0") == "0" else None
    return {
        "from_id": from_id,
        "text": text,
        "message_id": payload.get("MessageSid"),
        "timestamp": received_at,
        "profile_name": payload.get("ProfileName") or None,
    }


def build_twilio_send_payload(to_phone: str, bot_phone: str, text: str | None) -> dict[str, str]:
    """US-8: Build Twilio Sandbox outbound payload."""
    if not text:
        raise ValueError("build_twilio_send_payload: text must be a non-empty string")
    if not bot_phone.startswith("whatsapp:"):
        bot_phone = f"whatsapp:{bot_phone}"
    if not to_phone.startswith("whatsapp:"):
        to_phone = f"whatsapp:{to_phone}"
    return {
        "To": to_phone,
        "From": bot_phone,
        "Body": text,
    }


def build_meta_send_payload(reply: ChannelReply) -> dict[str, Any]:
    if not reply.text:
        raise ValueError("build_meta_send_payload: reply.text must be a non-empty string")
    return {
        "messaging_product": "whatsapp",
        "to": reply.channel_user_id,
        "type": "text",
        "text": {"body": reply.text},
    }


def _parse_form_body(raw_body: bytes) -> dict[str, str]:
    try:
        parsed = parse_qs(raw_body.decode("utf-8"), keep_blank_values=True)
    except UnicodeDecodeError:
        return {}
    return {k: v[0] if v else "" for k, v in parsed.items()}


def _headers(raw: Any) -> dict[str, str]:
    if isinstance(raw, dict):
        headers = raw.get("headers") or {}
        return {str(k).lower(): str(v) for k, v in headers.items()}
    return {}


def _to_channel_message(
    parsed: dict[str, Any],
    *,
    provider: str,
    trust: TrustLevel,
) -> ChannelMessage:
    if provider == "meta":
        arrived_at = datetime.fromtimestamp(int(float(parsed["timestamp"])), tz=UTC)
    else:
        arrived_at = parsed["timestamp"]
    return ChannelMessage(
        channel="whatsapp",
        channel_user_id=parsed["from_id"],
        user_handle=parsed["profile_name"] or parsed["from_id"],
        text=parsed["text"],
        trust_level=trust,
        arrived_at=arrived_at,
        metadata={"provider": provider, "message_id": parsed["message_id"]},
    )


class Adapter(ChannelAdapter):
    name = "whatsapp"

    async def on_message(self, raw: Any) -> ChannelMessage | None:  # type: ignore[override]
        mock = self.config.get("mock")
        if mock is not None:
            mock.pop_disconnect()
        headers = _headers(raw)
        is_public = bool(self.config.get("is_public_channel", False))
        parsed: dict[str, Any] | None = None
        provider = "meta"
        if isinstance(raw, dict) and "raw_body" in raw:
            raw_body = raw["raw_body"]
            if not isinstance(raw_body, bytes):
                return None
            twilio_sig = headers.get("x-twilio-signature", "")
            if twilio_sig:
                params = _parse_form_body(raw_body)
                url = os.environ.get("TWILIO_WEBHOOK_URL", "")
                auth_token = os.environ.get("TWILIO_AUTH_TOKEN", "")
                if not verify_twilio_signature(url, params, twilio_sig, auth_token):
                    return None
                parsed = parse_twilio_payload(params, datetime.now(UTC))
                provider = "twilio"
            elif headers.get("x-hub-signature-256"):
                if not verify_meta_signature(raw_body, headers):
                    return None
                try:
                    body = json.loads(raw_body)
                except json.JSONDecodeError:
                    return None
                parsed = parse_meta_payload(body)
                provider = "meta"
            else:
                return None
        elif isinstance(raw, dict) and raw.get("entry"):
            parsed = parse_meta_payload(raw)
            provider = "meta"
        elif isinstance(raw, dict) and "From" in raw and "Body" in raw:
            parsed = parse_twilio_payload(raw, datetime.now(UTC))
            provider = "twilio"
        else:
            return None
        if parsed is None:
            return None
        owner_ids = [r.channel_user_id for r in get_pairing_store().owners("whatsapp")]
        trust = classify("whatsapp", parsed["from_id"])
        ok, _ = allowed(
            "whatsapp",
            parsed["from_id"],
            owner_ids=owner_ids,
            is_public_channel=is_public,
            was_mentioned=False,
        )
        if not ok:
            if is_public and trust == "untrusted":
                return None
        return _to_channel_message(parsed, provider=provider, trust=trust)

    async def send(self, reply: ChannelReply) -> Any:
        # CURRENT STUB — this is what US-10 must replace
        body = build_meta_send_payload(reply)
        mock = self.config.get("mock")
        if mock is not None:
            return await mock.send(body)
        return body
```

**What the current `send()` stub does wrong:**
- Only builds a Meta payload — no Twilio path at all
- No provider cache — no awareness of which provider a user came from
- No pairing guard — will attempt to send to anyone
- No actual HTTP call — just returns the payload dict
- Mock check is correct in principle but positioned wrong (should check after provider resolution)

---

## 8. Environment variables used by the adapter

```bash
# Meta Cloud API
WHATSAPP_APP_SECRET         # HMAC-SHA256 signing secret for inbound webhook verification
WHATSAPP_PHONE_NUMBER_ID    # Meta phone number ID for outbound sends
WHATSAPP_TOKEN              # Meta Graph API bearer token (60-day token)
WHATSAPP_VERIFY_TOKEN       # Hub challenge verification token
WHATSAPP_WABA_ID            # WhatsApp Business Account ID
WHATSAPP_APP_ID             # Meta App ID

# Twilio Sandbox
TWILIO_AUTH_TOKEN           # Twilio auth token (for inbound signature validation)
TWILIO_ACCOUNT_SID          # Twilio account SID (for outbound sends)
TWILIO_WEBHOOK_URL          # Full public webhook URL — must match exactly what Twilio has configured
TWILIO_WHATSAPP_FROM        # Twilio sandbox sender number e.g. "+14155238886"

# Gateway
GLC_PAIRING_DB              # Optional: override path to pairings.sqlite (default: ~/.glc/pairings.sqlite)
```

---

## 9. Meta outbound HTTP call spec

```
POST https://graph.facebook.com/v19.0/{WHATSAPP_PHONE_NUMBER_ID}/messages
Authorization: Bearer {WHATSAPP_TOKEN}
Content-Type: application/json

{
  "messaging_product": "whatsapp",
  "to": "{recipient_phone_number}",
  "type": "text",
  "text": {"body": "{message_text}"}
}
```

**Meta error 131030** — recipient not in allowed list (free tier sandbox limitation):
```json
{
  "error": {
    "message": "...",
    "type": "OAuthException",
    "code": 131030,
    "fbtrace_id": "..."
  }
}
```
Check `response_json["error"]["code"] == 131030` exactly. Do not match on message string.

**Meta error 131047** — 24-hour re-engagement window closed. Do NOT fall back to Twilio on this.
It means the user exists on Meta but cannot receive free-form messages right now.

---

## 10. Twilio outbound HTTP call spec

```
POST https://api.twilio.com/2010-04-01/Accounts/{TWILIO_ACCOUNT_SID}/Messages.json
Authorization: Basic {base64(TWILIO_ACCOUNT_SID:TWILIO_AUTH_TOKEN)}
Content-Type: application/x-www-form-urlencoded

To=whatsapp%3A%2B{recipient}&From=whatsapp%3A%2B{TWILIO_WHATSAPP_FROM}&Body={text}
```

`build_twilio_send_payload(to_phone, bot_phone, text)` already builds the form dict.
Use `httpx.AsyncClient` for the async HTTP call — it is already in the project dependencies.

**Twilio error 63016** — 24-hour window closed on Twilio side. Do NOT retry on Meta.

---

## 11. Mock pattern (how tests intercept send())

When `self.config.get("mock")` is not None, the adapter is running in test mode.
The mock object has an async `send(payload)` method that logs to `mock.send_log`
and can be configured to return a fake 429.

The mock check must be positioned **after** provider resolution and payload
building but **before** the real HTTP call. The mock receives the final
payload dict that would have been sent to the real API.

Pattern:
```python
payload = build_meta_send_payload(reply)   # or build_twilio_send_payload(...)
mock = self.config.get("mock")
if mock is not None:
    return await mock.send(payload)
# ... real HTTP call here
```

---

## 12. CI pipeline — what your PR must pass

**`adapter-pr.yml`** (runs on every PR to integration):
1. **boundary** — diff must only touch `glc/channels/catalogue/whatsapp/**`
2. **test-changed-slot** — runs the whatsapp test suite + ruff + mypy on the slot dir
3. **scorecard** — auto-comments rubric score (10 pts × 200 scale)

**`ci.yml`** (runs on every push):
- `ruff check .` and `ruff format --check .`
- `mypy glc tests`
- `pytest tests/ --cov=glc --cov-fail-under=80 -m "not requires_live_api"`
- `scripts/validate_envelope.py` — envelope shape must not change
- `scripts/validate_policy.py` — policy.yaml must parse
- `scripts/validate_claims.py` — no duplicate group rows in GROUPS.md

**PR description must include (exact text):**
```
# Group: Group WhatsApp
# Slot: whatsapp
```

---

## 13. How to run locally

```bash
# From repo root, on branch feature/us10-send-orchestrator
uv sync                                                    # install deps
uv run glc serve                                           # start server on port 8111
uv run pytest glc/channels/catalogue/whatsapp/tests/ -v   # run slot tests
uv run ruff check glc/channels/catalogue/whatsapp/        # lint
uv run mypy glc/channels/catalogue/whatsapp/              # type check
```

# US-10 Handoff — Part 2: Task Specification & Implementation Guide

## Purpose of this document
Part 1 contains all source files verbatim. This document tells you exactly
what to build, every design decision that has been made, every constraint,
every edge case, and the exact shape the finished code must take.
An AI assistant reading both parts should be able to write correct,
CI-passing code with no further clarification needed — except for one
open decision flagged in §5.

---

## 1. What US-10 is

**US-10: `send()` orchestrator — dual-provider with outbound guard**

The `send()` method on the `Adapter` class is the gateway's outbound path.
When the agent runtime wants to reply to a WhatsApp user, it calls
`adapter.send(reply: ChannelReply)`. The current implementation is a stub
(Meta-only, no HTTP call, no guard, no cache). US-10 replaces it entirely.

**One sentence:** given a `ChannelReply`, figure out which provider (Meta
or Twilio) to use, check the recipient is allowed, make the HTTP call,
and return the result.

---

## 2. The provider cache — definition and ownership

Because `ChannelReply` has `extra="forbid"` on its Pydantic model, there is
no way to attach provider information to the reply object. The cache is the
only mechanism for `send()` to know which provider a contact uses.

**Define these at module level in `adapter.py`**, outside the `Adapter` class,
so both `on_message` (US-9) and `send` (US-10) share the same objects:

```python
USE_PROVIDER_CACHE: bool = True          # set False to disable entirely

provider_cache: dict[str, str] = {}      # {channel_user_id: "meta" | "twilio"}
_PROVIDER_CACHE_MAX: int = 100


def _remember_provider(channel_user_id: str, provider: str) -> None:
    """Write/update provider preference. FIFO eviction at _PROVIDER_CACHE_MAX."""
    if len(provider_cache) >= _PROVIDER_CACHE_MAX:
        provider_cache.pop(next(iter(provider_cache)))   # oldest entry, insertion order
    provider_cache[channel_user_id] = provider
```

**Why module-level and not instance-level (`self._cache`):**
The gateway may create multiple `Adapter` instances (e.g. for tests). A
module-level dict is shared across all instances, meaning a user who
messaged in on one instance is still cached when a different instance's
`send()` is called. This matches how the gateway works in production.

**`on_message` (US-9) writes to the cache** — after every inbound message
that passes signature verification:
```python
# In on_message, after parsed is confirmed not None, before returning:
_remember_provider(parsed["from_id"], provider)
```
This is US-9's responsibility (Mohit's code, already merged). US-10
implements `_remember_provider` as a shared utility. US-9 calls it.
Confirm with Raghu that US-9 has been updated to call `_remember_provider`
before merging US-10.

**Cache write semantics:**
- Unconditional overwrite — always replaces whatever was there
- No merge logic, no comparison — last inbound provider always wins
- Not persisted to disk — cleared on every server restart
- FIFO eviction at 100 entries using Python dict insertion-order guarantee

---

## 3. The complete `send()` logic — step by step

### Step 1: Provider resolution (first, before the guard)

```python
# Check cache first
if USE_PROVIDER_CACHE and reply.channel_user_id in provider_cache:
    provider = provider_cache[reply.channel_user_id]
else:
    provider = None   # will be resolved after trying Meta
```

### Step 2: Pairing guard

```python
rec = get_pairing_store().lookup("whatsapp", reply.channel_user_id)
if rec is None:
    return {"error": "recipient not paired", "code": "outbound_blocked"}
```

This guard exists because nothing in the shared gateway code validates
`send()`'s recipient — `glc/routes/channels.py` only guards inbound.
A prompt injection attack could cause the agent to call `send()` with an
arbitrary phone number. This check ensures only paired users can receive
messages regardless of what the agent decides.

**Open decision (document in README):** should this restrict to
`owner_paired` only, or allow any paired contact (`owner_paired` OR
`user_paired`)? The Handoff recommends documenting the choice. For a
conservative default, check `rec.trust_level == "owner_paired"` only.
For a permissive default, allow any non-None record. Either is valid —
pick one and state it clearly in the README.

### Step 3a: Cache hit path — send directly via known provider

```python
if provider == "meta":
    payload = build_meta_send_payload(reply)
    mock = self.config.get("mock")
    if mock is not None:
        return await mock.send(payload)
    # make real Meta HTTP call (see §4)
    return result

elif provider == "twilio":
    bot_phone = os.environ.get("TWILIO_WHATSAPP_FROM", "")
    payload = build_twilio_send_payload(reply.channel_user_id, bot_phone, reply.text)
    mock = self.config.get("mock")
    if mock is not None:
        return await mock.send(payload)
    # make real Twilio HTTP call (see §5)
    return result
```

### Step 3b: Cache miss path — try Meta first, fall back on 131030 only

```python
# Try Meta
meta_payload = build_meta_send_payload(reply)
mock = self.config.get("mock")
if mock is not None:
    result = await mock.send(meta_payload)
    # mocks don't return real error codes — treat as success, cache as meta
    _remember_provider(reply.channel_user_id, "meta")
    return result

# Real HTTP call to Meta
meta_result = await _send_meta(meta_payload)

if meta_result.get("error", {}).get("code") == 131030:
    # Recipient not on Meta — try Twilio
    bot_phone = os.environ.get("TWILIO_WHATSAPP_FROM", "")
    twilio_payload = build_twilio_send_payload(reply.channel_user_id, bot_phone, reply.text)
    twilio_result = await _send_twilio(twilio_payload)
    if USE_PROVIDER_CACHE:
        _remember_provider(reply.channel_user_id, "twilio")
    return twilio_result

# Any other Meta error (429, 131047, auth error, 5xx) — propagate as-is, NO Twilio retry
if "error" in meta_result:
    return meta_result   # or raise — do not attempt Twilio

# Meta succeeded
if USE_PROVIDER_CACHE:
    _remember_provider(reply.channel_user_id, "meta")
return meta_result
```

---

## 4. The Meta HTTP call implementation

```python
import httpx

async def _send_meta(payload: dict) -> dict:
    phone_number_id = os.environ.get("WHATSAPP_PHONE_NUMBER_ID", "")
    token = os.environ.get("WHATSAPP_TOKEN", "")
    url = f"https://graph.facebook.com/v19.0/{phone_number_id}/messages"
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            url,
            json=payload,
            headers={"Authorization": f"Bearer {token}",
                     "Content-Type": "application/json"},
        )
    return resp.json()
```

**Error detection:**
```python
result = await _send_meta(payload)
error_code = result.get("error", {}).get("code")
if error_code == 131030:
    # fall back to Twilio
elif error_code is not None:
    # some other Meta error — propagate, do NOT retry on Twilio
```

---

## 5. The Twilio HTTP call implementation

```python
import httpx
import base64

async def _send_twilio(payload: dict) -> dict:
    account_sid = os.environ.get("TWILIO_ACCOUNT_SID", "")
    auth_token = os.environ.get("TWILIO_AUTH_TOKEN", "")
    url = f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json"
    credentials = base64.b64encode(f"{account_sid}:{auth_token}".encode()).decode()
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            url,
            data=payload,   # form-urlencoded, NOT json=
            headers={"Authorization": f"Basic {credentials}"},
        )
    return resp.json()
```

Note: `data=payload` sends as `application/x-www-form-urlencoded`.
`json=payload` would send as JSON and Twilio would reject it.

---

## 6. The 429 requirement

Both the Handoff and the existing test stub (`test_rate_limit_propagates_429`)
require that 429 responses are propagated as-is, not swallowed or raised as
exceptions. This means:

```python
# Do NOT do this:
resp.raise_for_status()

# DO do this:
return resp.json()   # return the 429 body as a dict to the caller
```

The existing test passes a mock configured to return a fake 429. The mock's
`send()` returns the 429 dict. Your code must return it, not raise.

---

## 7. Errors that must NOT trigger a Twilio fallback

These Meta errors must be propagated directly to the caller with no Twilio
retry:
- **429** — rate limit hit
- **131047** — 24-hour re-engagement window closed (user exists on Meta,
  just can't receive free-form messages now)
- **Any auth error** (invalid token, etc.)
- **Any 5xx / network error** — risk of double-send if original succeeded
  and only the response read failed
- **Any error code that is NOT 131030**

Only `131030` ("Recipient phone number not in allowed list") means the user
genuinely does not exist on Meta and Twilio should be tried.

---

## 8. What the complete finished `adapter.py` diff looks like

You are modifying `adapter.py`. The functions above the `Adapter` class do
NOT change. The additions are:

**At module level (after imports, before `verify_meta_signature`):**
```python
# --- Provider cache (shared by on_message and send) ---
USE_PROVIDER_CACHE: bool = True
provider_cache: dict[str, str] = {}
_PROVIDER_CACHE_MAX: int = 100


def _remember_provider(channel_user_id: str, provider: str) -> None:
    if len(provider_cache) >= _PROVIDER_CACHE_MAX:
        provider_cache.pop(next(iter(provider_cache)))
    provider_cache[channel_user_id] = provider
```

**Two new private async functions (before the `Adapter` class):**
```python
async def _send_meta(payload: dict[str, Any]) -> dict[str, Any]:
    phone_number_id = os.environ.get("WHATSAPP_PHONE_NUMBER_ID", "")
    token = os.environ.get("WHATSAPP_TOKEN", "")
    url = f"https://graph.facebook.com/v19.0/{phone_number_id}/messages"
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            url, json=payload,
            headers={"Authorization": f"Bearer {token}",
                     "Content-Type": "application/json"},
        )
    return resp.json()


async def _send_twilio(payload: dict[str, str]) -> dict[str, Any]:
    account_sid = os.environ.get("TWILIO_ACCOUNT_SID", "")
    auth_token_val = os.environ.get("TWILIO_AUTH_TOKEN", "")
    url = f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json"
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            url, data=payload,
            headers={"Authorization":
                     f"Basic {base64.b64encode(f'{account_sid}:{auth_token_val}'.encode()).decode()}"},
        )
    return resp.json()
```

**New imports to add at the top of the file:**
```python
import base64
import httpx
```

**The new `send()` method replacing the stub:**
```python
async def send(self, reply: ChannelReply) -> Any:
    # Step 1: resolve provider from cache
    provider: str | None = None
    if USE_PROVIDER_CACHE and reply.channel_user_id in provider_cache:
        provider = provider_cache[reply.channel_user_id]

    # Step 2: pairing guard
    rec = get_pairing_store().lookup("whatsapp", reply.channel_user_id)
    if rec is None:
        return {"error": "recipient not paired", "code": "outbound_blocked"}

    mock = self.config.get("mock")

    # Step 3a: cache hit — send directly via known provider
    if provider == "meta":
        payload = build_meta_send_payload(reply)
        if mock is not None:
            return await mock.send(payload)
        result = await _send_meta(payload)
        return result

    if provider == "twilio":
        bot_phone = os.environ.get("TWILIO_WHATSAPP_FROM", "")
        payload = build_twilio_send_payload(reply.channel_user_id, bot_phone, reply.text)
        if mock is not None:
            return await mock.send(payload)
        result = await _send_twilio(payload)
        return result

    # Step 3b: cache miss — try Meta first
    meta_payload = build_meta_send_payload(reply)
    if mock is not None:
        # In test mode, mock doesn't distinguish providers — treat as Meta success
        result = await mock.send(meta_payload)
        if USE_PROVIDER_CACHE:
            _remember_provider(reply.channel_user_id, "meta")
        return result

    meta_result = await _send_meta(meta_payload)

    # 131030 only: recipient not on Meta, fall back to Twilio
    if meta_result.get("error", {}).get("code") == 131030:
        bot_phone = os.environ.get("TWILIO_WHATSAPP_FROM", "")
        twilio_payload = build_twilio_send_payload(
            reply.channel_user_id, bot_phone, reply.text
        )
        twilio_result = await _send_twilio(twilio_payload)
        if USE_PROVIDER_CACHE:
            _remember_provider(reply.channel_user_id, "twilio")
        return twilio_result

    # Any other error or success — return as-is, no Twilio retry
    if "error" not in meta_result and USE_PROVIDER_CACHE:
        _remember_provider(reply.channel_user_id, "meta")
    return meta_result
```

---

## 9. Team state as of June 28 2026

| Story | Owner | Status | Notes |
|---|---|---|---|
| US-1 Meta wiring | Raghu | ✅ Merged | Real Meta account set up |
| US-2 Twilio wiring | Jeet | ✅ Merged | Real Twilio sandbox set up |
| US-3 verify_meta_signature | Raghu | ✅ In adapter.py | |
| US-4 parse_meta_payload | Raghu | ✅ In adapter.py | |
| US-5 build_meta_send_payload | Raghu | ✅ In adapter.py | |
| US-6 verify_twilio_signature | Jeet | ✅ In adapter.py (via PR-2) | |
| US-7 parse_twilio_payload | Ranjay | ✅ Merged | |
| US-8 build_twilio_send_payload | Ranjay | ✅ Merged | |
| US-9 on_message orchestrator | Mohit | ✅ Merged — **needs cache write update** | Must call `_remember_provider` |
| **US-10 send() orchestrator** | **Aryaman** | 🔴 Not started | **This task** |
| US-11 Twilio test suite | Narasimhan | 🟡 In progress | Phase 1 started |
| US-12 QA gate | Team | ⏳ Waiting on US-10/11 | |
| US-13 Demo recording | Team | ⏳ Waiting on US-12 | |
| US-14 README | Team | ⏳ Waiting on US-13 | |
| US-15 Final PR | Raghu | ⏳ Waiting on US-14 | Deadline ~Jul 1 |

**Critical dependency before merging US-10:**
US-9's `on_message` must call `_remember_provider(parsed["from_id"], provider)`.
This call is in US-10's code (the function definition), so US-10 must be
merged first OR the function must be agreed upon before US-9 is updated.
Confirm with Raghu that the module-level `_remember_provider` definition is
agreed, then coordinate the update to US-9's `on_message`.

---

## 10. What the mock object looks like (for test writing)

From `tests/channels/mocks/whatsapp_mock.py` (read-only, cannot be edited):

```
OWNER_WA_ID = "919999990000"
STRANGER_WA_ID = "917777770000"
PHONE_NUMBER_ID = "10987654321"
DEFAULT_APP_SECRET = "test-app-secret"

mock.send_log          # list of payloads passed to mock.send()
mock.send(payload)     # async, logs payload, returns success or fake 429
mock.force_disconnect()
mock.pop_disconnect()
mock.queue_owner_message(text)       # Meta-shaped inbound from OWNER_WA_ID
mock.queue_stranger_message(text)    # Meta-shaped inbound from STRANGER_WA_ID
mock.queue_signed_webhook(...)       # returns (raw_bytes, headers)
mock.queue_unsigned_webhook(...)
mock.queue_tampered_webhook(...)
```

The mock's `send()` intercepts at the payload level — it does not care
whether the payload is Meta or Twilio shaped. Your `send()` must pass
the mock the final payload dict before the real HTTP call would happen.

**For existing tests that call `send()` (e.g. `test_send_emits_valid_wire_payload`
and `test_rate_limit_propagates_429`):** these tests use the `pair_owner` fixture
which registers `OWNER_WA_ID` in the pairing store before calling `send()`.
This means the pairing guard (`lookup()` returning non-None) will pass for those
tests without any change needed.

---

## 11. mypy and ruff requirements

- All function signatures must have full type annotations
- `_send_meta` and `_send_twilio` return `dict[str, Any]`
- `_remember_provider` returns `None`
- `provider_cache` is typed as `dict[str, str]`
- `USE_PROVIDER_CACHE` is typed as `bool`
- No `# type: ignore` except the existing one on `on_message`'s signature
- ruff: no unused imports, no f-strings that can be simplified

---

## 12. Things that must NOT happen

- Do not add a `provider` field to `ChannelReply` — `extra="forbid"` will
  cause a Pydantic validation error at runtime
- Do not create two Adapter subclasses (one per provider) — the ABC
  expects a single class named `Adapter` with `name = "whatsapp"`
- Do not use `requests` — use `httpx.AsyncClient` for async compatibility
- Do not call `resp.raise_for_status()` — 429s must be returned, not raised
- Do not persist the provider cache to disk — in-memory only
- Do not touch any file outside `glc/channels/catalogue/whatsapp/`
- Do not retry on any Meta error other than code 131030
- Do not retry on Twilio error 63016 (24-hour window) — propagate it
- Do not hardcode any credentials — all secrets come from env vars
- Do not import `langchain`, `crewai`, `autogen`, or `open_interpreter`

---

## 13. Git steps to submit

```bash
# You are already on feature/us10-send-orchestrator, branched from integration
# Make your changes to adapter.py, then:

git add glc/channels/catalogue/whatsapp/adapter.py
git commit -m "US-10: send() orchestrator — dual-provider cache + outbound guard"
git push -u origin feature/us10-send-orchestrator

# Then open a PR on GitHub:
# base: rraghu214/glc_v1_whatsapp integration
# compare: feature/us10-send-orchestrator
# PR description must include:
# Group: Group WhatsApp
# Slot: whatsapp
```