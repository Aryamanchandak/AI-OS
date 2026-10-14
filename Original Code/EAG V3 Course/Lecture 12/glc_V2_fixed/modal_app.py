"""Modal deployment for glc_v2 — Session 12 Part-1 hardening (process separation).

Unlike the Part-0 wrapper (which ran the ENTIRE gateway + all adapters as ONE
Modal Function, with ONE Secret holding every provider key and the config Volume
mounted on everything), this file splits the system along its real trust
boundary:

  ┌────────────────────────── gateway (trusted) ──────────────────────────┐
  │  Function: fastapi_app                                                 │
  │    • full `glc` image (policy, db, pairing, providers all importable)  │
  │    • config/audit Volume mounted at /data                              │
  │    • Secrets: glc-control (install token) + glc-llm-keys (provider keys)│
  │    • serves glc.main:app; in-process webhook adapters DISABLED         │
  └───────────────────────────────────────────────────────────────────────┘
  ┌───────────────────────── adapter (untrusted) ─────────────────────────┐
  │  Functions: adapter_verify_sandboxed, adapter_relay_sandboxed         │
  │    • PRUNED image: glc.policy / glc.db / glc.security.pairing and every │
  │      provider module are NOT present → cannot be imported at all       │
  │    • NO Volume mount                                                    │
  │    • Secret: glc-channel-<name> ONLY — a per-channel token, NOT the    │
  │      control-plane install token. See glc/security/adapter_auth.py.    │
  │    • talks to the gateway only over its public WS/HTTP API             │
  └───────────────────────────────────────────────────────────────────────┘

This is the architectural fix for Leaks 1/2/3/4/5/8/10: they stop being
reachable from adapter code by construction, not by per-method patching.

Post-audit hardening: adapters originally mounted `glc-control` (the SAME
Secret as the gateway's control-plane token), so a compromised adapter
could call `/v1/control/pair` with `trust_level="owner_paired"` and
self-confirm it — Leak 3 reopened via HTTP instead of an import. Adapter
Functions now mount a per-channel Secret containing only `GLC_CHANNEL_TOKEN`,
derived from the install token via `glc.security.adapter_auth` but not
reversible to it and not valid for any other channel or for
`/v1/control/*`. Provision a channel's secret with:

    GLC_INSTALL_TOKEN=<gateway's raw install token> \
      uv run modal run modal_app.py::derive_channel_token_cli --channel relay_echo

which prints the derived token and the exact `modal secret create` command.

Deploy:   uv run modal deploy modal_app.py
Verify:   uv run modal run modal_app.py::main              # real isolation proof (adapter_verify_sandboxed)

Note: this file now has TWO local_entrypoints (`main` and
`derive_channel_token_cli`) — bare `uv run modal run modal_app.py` is
ambiguous once there's more than one, always name the entrypoint
explicitly (`::main` or `::derive_channel_token_cli`).

Keys MUST be mock/dummy (ASSIGNMENT.md). The v1 monolith app (`glc-v1-gateway`)
is left deployed on purpose as the "before" comparison surface.
"""

from pathlib import Path

import modal

app = modal.App("glc-v2-gateway")

LOCAL_GLC = Path(__file__).parent / "glc"

# The gateway's public WS base. Filled in after the first deploy prints the
# fastapi_app URL; the adapter uses it to reach the gateway and NOTHING else.
GATEWAY_WS_URL = "wss://aryamanchandak7--glc-v2-gateway-fastapi-app.modal.run"

# Phase 3 (Leak 6 — unbounded egress): the ONLY host an adapter Sandbox is
# allowed to reach outbound. Same host as GATEWAY_WS_URL, just without the
# wss:// scheme (outbound_domain_allowlist takes bare domain names).
GATEWAY_HOSTNAME = "aryamanchandak7--glc-v2-gateway-fastapi-app.modal.run"

# --------------------------------------------------------------------------- #
# Images
# --------------------------------------------------------------------------- #

# A5 — reproducible base image: `debian_slim(python_version="3.11")` floats
# on whatever "python:3.11-slim" resolves to on the day of the build, and
# the old `pip_install(">=x")` ranges let every rebuild silently pick up a
# newer, unreviewed release. Pin the base by the immutable manifest-list
# digest instead of the mutable tag (digest resolved 2026-07-16 from the
# Docker Hub registry API for `library/python:3.11-slim`; bump deliberately,
# not implicitly, when a base-image update is actually wanted), and install
# dependencies via `uv sync --frozen` (uv_sync's default) against the
# checked-in `pyproject.toml` + `uv.lock` instead of loose ranges — a build
# now reproduces the exact locked, hashed dependency set or fails, it never
# silently drifts. pyproject.toml's `[project.dependencies]` is exactly this
# image's runtime set (fastapi/uvicorn/httpx/... + modal itself), so nothing
# beyond what the gateway actually uses gets pulled in.
_PYTHON_311_SLIM_DIGEST = "sha256:db3ff2e1800a8581e2c48a27c3995339d47bdf046da21c7627accd3d51053a93"

# Gateway image: the whole application.
gateway_image = (
    modal.Image.from_registry(f"python:3.11-slim@{_PYTHON_311_SLIM_DIGEST}")
    .uv_sync()
    # GLC_ENV=production (Phase 4 / A2): disables /docs, /redoc, /openapi.json
    # on the deployed gateway — see glc/main.py's _PRODUCTION flag. Local dev
    # (plain `uvicorn`/pytest, no GLC_ENV set) keeps them on by default.
    .env({"GLC_CONFIG_DIR": "/data/glc", "GLC_ENV": "production"})
    .add_local_dir(str(LOCAL_GLC), remote_path="/root/glc")
)

# Adapter image: a PRUNED copy of glc. Everything on the gateway's trust
# boundary is excluded, so `import glc.policy` (etc.) raises ImportError inside
# an adapter container — the isolation is a property of the image, not a check
# that code could skip. `ignore` patterns are relative to LOCAL_GLC.
_ADAPTER_IGNORE = [
    # gateway trust boundary — the forbidden imports (Leaks 3/5/10)
    "policy/**",
    "db.py",
    "security/**",
    # provider keys / LLM plumbing (Leak 1)
    "providers.py",
    "embedders.py",
    "pricing.py",
    "cache.py",
    "llm_schemas.py",
    "routing.py",
    # gateway-only surfaces
    "main.py",
    "cli.py",
    "config.py",
    "routes/**",
    "audit/**",
    "voice/**",
    # every existing catalogue adapter still imports gateway internals; keep the
    # package dir (its __init__) but none of the coupled adapter subpackages.
    # The clean reference adapter lives in glc/channels/runner.py instead.
    "channels/catalogue/*/**",
    "**/__pycache__/**",
    "**/tests/**",
]

# A5 (adapter side): same digest-pinned base as the gateway. Dependencies are
# NOT synced from the full uv.lock here on purpose — `uv_sync()` installs
# every package in `pyproject.toml`'s main dependency group, which would
# silently re-bloat this image with everything the gateway needs (fastapi,
# jsonschema, twilio, ...) and defeat the whole point of a pruned adapter
# image. Instead pin its three actual deps to the exact versions `uv.lock`
# resolved for the gateway build, so the two images agree on versions
# without the adapter gaining anything it doesn't use.
_ADAPTER_PINNED_DEPS = [
    "pydantic==2.13.4",
    "httpx==0.28.1",
    "websockets==16.0",
]

adapter_image = (
    modal.Image.from_registry(f"python:3.11-slim@{_PYTHON_311_SLIM_DIGEST}")
    .pip_install(*_ADAPTER_PINNED_DEPS)
    .env({"GLC_GATEWAY_WS_URL": GATEWAY_WS_URL})
    # copy=True (bake into the image layer at build time) rather than the
    # default copy=False (mount at container startup): the startup-mount path
    # is wired into Modal's Function entrypoint specifically, and a raw
    # modal.Sandbox (Phase 3) built from this image does NOT go through that
    # entrypoint, so with copy=False the sandbox container had no /root/glc
    # at all — ModuleNotFoundError: No module named 'glc', confirmed by a
    # real deploy+run before this was set. copy=True makes /root/glc part of
    # the image regardless of how the container is started.
    .add_local_dir(str(LOCAL_GLC), remote_path="/root/glc", ignore=_ADAPTER_IGNORE, copy=True)
    # Leak 7 — subprocess/shell access. Tried and reverted: a
    # useradd/chown/chmod-a-w/`USER` dockerfile_commands block, meant to make
    # the adapter run non-root with a read-only /root/glc. Deployed evidence
    # (`adapter_verify`, both before and after adding it) showed
    # `leak7_running_as_uid: 0` in both cases and `leak7_source_tree_writable:
    # true` in both cases — Modal 1.5.1 always runs container entrypoints as
    # root and silently skips `USER` ("Skipping USER instruction, it is
    # unsupported by Modal container images"), so root ignores the chmod too.
    # There's no non-root/read-only knob on `app.function` or `Sandbox.create`
    # either (checked both signatures). This is a platform limitation, not a
    # config mistake — see FINDINGS.md Leak 7 for the residual-risk writeup
    # and what separation (Phase 1) still buys despite it.
)

# --------------------------------------------------------------------------- #
# Volume + Secrets
# --------------------------------------------------------------------------- #

data_volume = modal.Volume.from_name("glc-data", create_if_missing=True)

# Control-plane secret: the install token. GATEWAY ONLY now — see the
# module docstring's "Post-audit hardening" note. Never mounted on an
# adapter Function; adapters get a per-channel secret instead (below).
control_secret = modal.Secret.from_name("glc-control")

# Provider keys — GATEWAY ONLY. Never mounted on an adapter Function.
llm_secret = modal.Secret.from_name("glc-llm-keys")

# Per-channel adapter secret: holds only GLC_CHANNEL_TOKEN, a value derived
# from (but not reversible to) the install token via
# glc.security.adapter_auth.derive_channel_token, scoped to exactly one
# channel name. Provision with `derive_channel_token_cli` below. Only the
# reference EchoIngressAdapter (channel "relay_echo") is deployed today.
relay_echo_channel_secret = modal.Secret.from_name("glc-channel-relay-echo")


# --------------------------------------------------------------------------- #
# Gateway Function
# --------------------------------------------------------------------------- #
@app.function(
    image=gateway_image,
    volumes={"/data": data_volume},
    secrets=[control_secret, llm_secret],
    # A6: the audit/pairing DB is a single SQLite file on the Volume. With
    # autoscaling (min_containers=0 and no cap) more than one gateway
    # container can come up under load, each opening its own connection to
    # the same file — concurrent writers with no serialization, which is
    # exactly how you split/corrupt an audit trail (and defeats Phase 2's
    # hash chain, which assumes one writer appending in order). Pinning to
    # exactly one container makes the gateway itself the single serialized
    # writer Phase 2 already assumes.
    min_containers=1,
    max_containers=1,
)
@modal.asgi_app()
def fastapi_app():
    """Serve the glc gateway. In-process webhook adapters are turned OFF so the
    gateway runs no adapter code; ingress arrives over WS from adapter Functions."""
    import os

    os.makedirs("/data/glc", exist_ok=True)
    os.environ["GLC_INPROC_ADAPTERS"] = "0"  # gateway never runs adapter code

    from glc.main import app as web
    return web


# --------------------------------------------------------------------------- #
# Adapter Functions (untrusted, pruned image, per-channel secret only, NO Volume)
#
# Post-audit removal: this file used to ALSO deploy `adapter_verify` /
# `adapter_relay` as plain `@app.function`s with no egress control, kept
# around only to produce a one-time "before" comparison for the Leak 6
# writeup in FINDINGS.md. That comparison is already captured there; leaving
# an unrestricted-egress Function permanently live in the deployed app for a
# one-time demo was itself flagged (Codex review) as unnecessary standing
# risk with no ongoing purpose — deleted. Only the Sandboxed variants below,
# which are also the production-shaped path (egress-restricted, same as the
# real adapter relay), remain deployed.
# --------------------------------------------------------------------------- #


# --------------------------------------------------------------------------- #
# Phase 3 — egress allowlist (Leak 6). A plain `@app.function` Modal Function
# has NO outbound network control (proved once, historically, in FINDINGS.md's
# Phase 3 writeup — an unsandboxed Function reached an attacker domain).
# `modal.Sandbox` does, via `outbound_domain_allowlist`. These wrap the SAME
# pruned adapter image + a per-channel secret in a Sandbox scoped to reach
# only the gateway host — nothing else, verified below by literally
# attempting the attacker POST.
# --------------------------------------------------------------------------- #


def _adapter_sandbox() -> modal.Sandbox:
    # workdir="/root" matters: unlike @app.function, a raw Sandbox doesn't go
    # through Modal's function-call entrypoint that puts the mounted source
    # tree on sys.path automatically. `python -c` inserts the empty string
    # (cwd) as sys.path[0], so cwd=/root is what makes `import glc` resolve
    # to /root/glc (the add_local_dir target) inside the sandbox.
    return modal.Sandbox.create(
        app=app,
        image=adapter_image,
        secrets=[relay_echo_channel_secret],
        outbound_domain_allowlist=[GATEWAY_HOSTNAME],
        workdir="/root",
        timeout=120,
    )


def _exec_in_sandbox(sb: modal.Sandbox, code: str) -> str:
    # `workdir` on Sandbox.exec() is independent of the one passed to
    # Sandbox.create() — it must be repeated here, or `python -c` runs from
    # whatever the container's default cwd is (not /root) and `import glc`
    # fails with ModuleNotFoundError despite the source tree being present.
    proc = sb.exec("python", "-c", code, workdir="/root")
    out = proc.stdout.read()
    err = proc.stderr.read()
    rc = proc.wait()
    if rc != 0:
        raise RuntimeError(f"sandboxed exec failed (rc={rc}): {err}")
    return out


@app.function(image=adapter_image, secrets=[relay_echo_channel_secret])
def adapter_verify_sandboxed() -> dict:
    """Phase 3 'after' for Leak 6: run the identical `verify_isolation()`
    probe, but from inside a modal.Sandbox whose outbound_domain_allowlist is
    just the gateway host. Leaks 1/2/3/4/5/8/10 should still read closed
    (same pruned image); leak6_egress_to_attacker_domain should now read
    'blocked', not 'REACHED'."""
    import json

    sb = _adapter_sandbox()
    try:
        out = _exec_in_sandbox(
            sb,
            "import json; from glc.channels.runner import verify_isolation; "
            "print(json.dumps(verify_isolation()))",
        )
        return json.loads(out)
    finally:
        sb.terminate()


@app.function(image=adapter_image, secrets=[relay_echo_channel_secret])
def adapter_relay_sandboxed(text: str = "hello from a sandboxed adapter") -> dict:
    """Production-shaped Phase 3 path: the real adapter relay, run inside the
    same egress-restricted Sandbox, proving the allowlist doesn't break the
    one thing the adapter is actually supposed to reach — the gateway WS.
    Sync, not async: all the work happens inside the sandboxed subprocess via
    `sb.exec`, so there's nothing here worth awaiting (using the blocking
    Sandbox API from an async def just triggers Modal's AsyncUsageWarning for
    no benefit)."""
    import json

    sb = _adapter_sandbox()
    try:
        code = (
            "import asyncio, json; "
            "from glc.channels.runner import EchoIngressAdapter, relay; "
            f"raw = {{'channel_user_id': 'demo-user', 'text': {text!r}}}; "
            "print(json.dumps(asyncio.run(relay(EchoIngressAdapter(), raw))))"
        )
        out = _exec_in_sandbox(sb, code)
        return json.loads(out)
    finally:
        sb.terminate()


@app.local_entrypoint()
def main():
    """`modal run modal_app.py` → run the full isolation + egress-restriction
    proof inside the Sandboxed adapter (the only adapter shape now deployed):
    provider keys absent, gateway internals unimportable, no Volume, egress
    blocked outside the gateway host, and the new control-plane-rejection
    probe (channel token cannot authenticate /v1/control/pair)."""
    import json

    print("=== adapter as a modal.Sandbox (outbound_domain_allowlist=[gateway]) ===")
    result = adapter_verify_sandboxed.remote()
    print(json.dumps(result, indent=2))


@app.local_entrypoint()
def derive_channel_token_cli(channel: str = "relay_echo"):
    """Operator helper — run OUTSIDE any Modal Function, locally, with the
    gateway's raw install token in the environment (never inside an adapter,
    which must never hold it):

        GLC_INSTALL_TOKEN=<gateway's raw install token> \\
          uv run modal run modal_app.py::derive_channel_token_cli --channel relay_echo

    Prints the derived per-channel token and the exact `modal secret create`
    command to provision the Secret that channel's adapter Function mounts.
    """
    import os
    import sys

    sys.path.insert(0, str(Path(__file__).parent))
    from glc.security.adapter_auth import derive_channel_token

    raw = os.environ.get("GLC_INSTALL_TOKEN", "").strip()
    if not raw:
        raise SystemExit(
            "set GLC_INSTALL_TOKEN to the gateway's raw install token before running this"
        )
    token = derive_channel_token(raw, channel)
    secret_name = f"glc-channel-{channel.replace('_', '-')}"
    print(f"channel={channel!r}")
    print(f"token={token}")
    print("\nProvision it:")
    print(f"  modal secret create {secret_name} GLC_CHANNEL_TOKEN={token}")
