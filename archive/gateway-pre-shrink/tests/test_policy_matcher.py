"""Policy matcher bypasses, ported from GLC's `test_policy_matcher_hardening.py`.

Each test here is a way to get a deny rule to not fire. They share one shape:
the matcher is handed something it does not expect, quietly reports "no
match", the rule is skipped, and evaluation falls through to default-allow
for an owner_paired caller. The engine must fail closed instead.

These are the characterization tests Plan 03 Work Package C called for
before the matcher moved; they were not carried over during the move, which
is how two regressions (list-valued conditions, backslash path separators —
see `test_list_valued_condition_still_matches` and
`test_backslash_path_matches_tilde_rule` below) went undetected until a
differential run against the original `glc.policy.engine` module caught
them.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from gateway.policy.engine import PolicyEngine
from gateway.policy.schemas import PolicyConfig, PolicyRule

OWNER = {"channel": "telegram", "trust_level": "owner_paired"}
_FAKE_PATH = Path("<test>")


def _engine(rule: PolicyRule) -> PolicyEngine:
    return PolicyEngine(_FAKE_PATH, PolicyConfig(rules=[rule]))


def test_nonstring_glob_arg_does_not_skip_deny() -> None:
    """A dict where a path string was expected must not skip the deny rule."""
    eng = _engine(
        PolicyRule(
            tool="file.delete",
            trust_level="*",
            action="deny",
            reason="no deleting Documents",
            condition={"path_glob": "~/Documents/**"},
        )
    )
    v = eng.evaluate({"name": "file.delete", "arguments": {"path": {"$ne": None}}}, OWNER)
    assert v.action == "deny", v


def test_nonstring_command_does_not_skip_deny() -> None:
    eng = _engine(
        PolicyRule(
            tool="shell.run",
            trust_level="*",
            action="deny",
            reason="no sudo",
            condition={"command_matches": ["sudo"]},
        )
    )
    v = eng.evaluate({"name": "shell.run", "arguments": {"command": ["sudo", "rm"]}}, OWNER)
    assert v.action == "deny", v


def test_command_match_is_case_insensitive() -> None:
    """`SUDO` must not walk past a lowercase deny rule."""
    eng = _engine(
        PolicyRule(
            tool="shell.run",
            trust_level="*",
            action="deny",
            reason="no sudo",
            condition={"command_matches": ["sudo"]},
        )
    )
    v = eng.evaluate({"name": "shell.run", "arguments": {"command": "SUDO rm -rf /"}}, OWNER)
    assert v.action == "deny", v


def test_absolute_path_matches_tilde_rule() -> None:
    """The same file spelled absolutely must hit a ``~/`` deny rule."""
    eng = _engine(
        PolicyRule(
            tool="file.delete",
            trust_level="*",
            action="deny",
            reason="no deleting Documents",
            condition={"path_glob": "~/Documents/**"},
        )
    )
    absolute = os.path.expanduser("~/Documents/taxes.pdf")
    v = eng.evaluate({"name": "file.delete", "arguments": {"path": absolute}}, OWNER)
    assert v.action == "deny", v


def test_backslash_path_matches_tilde_rule() -> None:
    """The same file spelled with backslashes must also hit the deny rule."""
    eng = _engine(
        PolicyRule(
            tool="file.delete",
            trust_level="*",
            action="deny",
            reason="no deleting Documents",
            condition={"path_glob": "/home/u/Documents/**"},
        )
    )
    v = eng.evaluate(
        {"name": "file.delete", "arguments": {"path": "\\home\\u\\Documents\\taxes.pdf"}}, OWNER
    )
    assert v.action == "deny", v


def test_newline_in_value_does_not_evade_glob() -> None:
    """A trailing newline must not truncate the match and evade the rule."""
    eng = _engine(
        PolicyRule(
            tool="file.delete",
            trust_level="*",
            action="deny",
            reason="no deleting Documents",
            condition={"path_glob": "~/Documents/**"},
        )
    )
    sneaky = os.path.expanduser("~/Documents/taxes.pdf") + "\nnot-a-real-suffix"
    v = eng.evaluate({"name": "file.delete", "arguments": {"path": sneaky}}, OWNER)
    assert v.action == "deny", v


def test_ordinary_allow_still_works() -> None:
    """Failing closed must not turn unrelated allowed calls into denials."""
    eng = _engine(
        PolicyRule(
            tool="file.delete",
            trust_level="*",
            action="deny",
            reason="no deleting Documents",
            condition={"path_glob": "~/Documents/**"},
        )
    )
    v = eng.evaluate({"name": "file.read", "arguments": {"path": "/tmp/ok.txt"}}, OWNER)
    assert v.action == "allow", v


@pytest.mark.parametrize("bad", [123, None, {"a": 1}, ["x"]])
def test_nonstring_regex_arg_does_not_skip_deny(bad: object) -> None:
    eng = _engine(
        PolicyRule(
            tool="email.send",
            trust_level="*",
            action="deny",
            reason="no external recipients",
            condition={"to_regex": r".*@external\.com"},
        )
    )
    v = eng.evaluate({"name": "email.send", "arguments": {"to": bad}}, OWNER)
    assert v.action == "deny", v


def test_list_valued_condition_still_matches() -> None:
    """A bare (non-suffixed) condition key may hold a list of accepted
    values, e.g. ``{tier: [gold, platinum]}``. This must match membership,
    not equality against the whole list."""
    eng = _engine(
        PolicyRule(
            tool="shell.exec",
            trust_level="*",
            action="deny",
            reason="no rm/del",
            condition={"mode": ["rm", "del"]},
        )
    )
    v = eng.evaluate({"name": "shell.exec", "arguments": {"mode": "rm"}}, OWNER)
    assert v.action == "deny", v
    v = eng.evaluate({"name": "shell.exec", "arguments": {"mode": "mv"}}, OWNER)
    assert v.action == "allow", v


def test_denied_rule_without_reason_uses_stable_default_message() -> None:
    """A deny rule with no explicit ``reason`` must produce the same
    refusal text as before the move, so WP C's "identical refusal"
    requirement holds even for unauthored reasons."""
    eng = _engine(PolicyRule(tool="ping", trust_level="*", action="deny"))
    v = eng.evaluate({"name": "ping", "arguments": {}}, OWNER)
    assert v.action == "deny"
    assert v.reason == "denied by policy"
