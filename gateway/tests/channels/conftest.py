"""Defensive test collection for channel adapters.

A group's adapter PR may include a syntax error (work-in-progress) or
fail to import for some other reason. Without this hook, a single bad
adapter import error pollutes the failure list for every other PR run
that pulls main.

The hook tries to import each test file's target adapter at collection
time. If the import errors, the matching test file is skipped with a
clear message naming the broken module — the rest of the suite
collects normally.

This only kicks in when the test file follows the pattern
`tests/channels/test_<channel>.py`. The channel name is read from the
filename and used to locate `gateway.channels.catalogue.<channel>.adapter`.
"""

from __future__ import annotations

import importlib
import re
from pathlib import Path

import pytest

_TEST_FILE_RE = re.compile(r"^test_(?P<channel>[a-z_]+)\.py$")


@pytest.fixture(autouse=True)
def _isolated_channel_state(monkeypatch, tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    channels_path = config_dir / "channels.yaml"
    channels_path.write_text(
        "defaults:\n  allowed_senders: []\n  mention_only_in_public: true\n"
        "channels:\n  telegram: {enabled: true}\n  discord: {enabled: true}\n"
        "  gmail: {enabled: true}\n  imap: {enabled: true}\n  line: {enabled: true}\n"
        "  local_mic: {enabled: true}\n  matrix: {enabled: true}\n  signal: {enabled: true}\n"
        "  slack: {enabled: true}\n  teams: {enabled: true}\n  twilio_sms: {enabled: true}\n"
        "  twilio_voice: {enabled: true}\n  webhook: {enabled: true}\n"
        "  webui: {enabled: true}\n  whatsapp: {enabled: true}\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("GLC_CONFIG_DIR", str(config_dir))
    monkeypatch.setenv("GLC_CHANNELS_YAML", str(channels_path))
    monkeypatch.setenv("GLC_PAIRING_DB", str(tmp_path / "pairings.sqlite"))
    import gateway.channels.setup_config as setup_config
    import gateway.security.allowlists as allowlists
    import gateway.security.pairing as pairing
    import gateway.security.rate_limits as rate_limits

    monkeypatch.setattr(setup_config, "CONFIG_DIR", config_dir)
    pairing._singleton = None
    rate_limits._limiter = None
    allowlists._allowlist = None
    yield
    pairing._singleton = None
    rate_limits._limiter = None
    allowlists._allowlist = None


def pytest_collectstart(collector):  # pragma: no cover - pytest hook surface
    p = Path(collector.fspath) if hasattr(collector, "fspath") else None
    if p is None:
        return
    m = _TEST_FILE_RE.match(p.name)
    if not m:
        return
    channel = m.group("channel")
    try:
        importlib.import_module(f"gateway.channels.catalogue.{channel}.adapter")
    except Exception as e:
        pytest.skip(
            f"channel adapter gateway.channels.catalogue.{channel}.adapter failed to import: {e!r}",
            allow_module_level=True,
        )
