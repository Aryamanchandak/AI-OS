"""Pairwise contract check against the Plan 01 baseline.

Plan 04a §7 asks for a *pairwise* comparison: a bare path-set diff shows every
route as removed-and-added because the prefix changed, which proves nothing.
This walks the old→new mapping instead.

Scope, stated plainly: this compares **paths, methods and request bodies**. It
cannot compare response bodies, because none of the legacy LLM routes declares a
`response_model`, so the baseline OpenAPI carries `"schema": {}` for every 200
on both sides. Closing that needs recorded response fixtures, which Plan 01 owes
and which do not exist in this tree. `test_llm_streaming.py` covers the SSE half
of the contract directly instead of through OpenAPI.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from gateway.llm.api.routes import registration

BASELINE = Path(__file__).resolve().parents[2] / "migration" / "baseline" / "contracts" / "glc-openapi.json"

#: The old→new mapping from Plan 04a §7. Left side is a legacy GLC path; right
#: side is where it must now answer.
ROUTE_MAPPING = {
    "/v1/chat": "/api/llm/chat",
    "/v1/chat/batch": "/api/llm/chat/batch",
    "/v1/vision": "/api/llm/vision",
    "/v1/embed": "/api/llm/embed",
    "/v1/embedders": "/api/llm/embedders",
    "/v1/providers": "/api/llm/providers",
    "/v1/capabilities": "/api/llm/capabilities",
    "/v1/status": "/api/llm/status",
    "/v1/budget": "/api/llm/budget",
    "/v1/cost/by_principal": "/api/llm/cost/by_principal",
    "/v1/cache/stats": "/api/llm/cache/stats",
    "/v1/pricing": "/api/llm/pricing",
}

#: LLM-domain routes that exist in the baseline beyond the mapped twelve. They
#: are carried across at the same suffix, so nothing in the baseline is
#: unaccounted for.
ALSO_CARRIED = {
    "/v1/calls": "/api/llm/calls",
    "/v1/routers": "/api/llm/routers",
    "/v1/telemetry": "/api/llm/telemetry",
    "/v1/cache/purge": "/api/llm/cache/purge",
    "/v1/cost/by_agent": "/api/llm/cost/by_agent",
    "/v1/chat/profiles/{profile}": "/api/llm/chat/profiles/{profile}",
    "/v1/budget/{principal}": "/api/llm/budget/{principal:path}",
}

#: Baseline prefixes owned by other plans, so their absence from the LLM router
#: is correct rather than a gap. Listed by owner so an unexpected addition to the
#: baseline fails this test instead of being silently swept up.
OTHER_DOMAINS = (
    "/v1/control/",        # Plan 03 — platform security and control
    "/v1/channels",        # Plan 05 — channels
    "/v1/channel-admin/",  # Plan 05 — channels
    "/v1/speak",           # Plan 05 — voice
    "/v1/transcribe",      # Plan 05 — voice
    "/v1/traces",          # observability, not the LLM domain
    "/v1/observability/",
    "/v1/preflight",
    "/v1/refusals",
)


def baseline() -> dict[str, Any]:
    if not BASELINE.exists():
        pytest.skip(f"Plan 01 baseline missing at {BASELINE}")
    return json.loads(BASELINE.read_text(encoding="utf-8"))


def migrated_paths() -> dict[str, set[str]]:
    """Every path the LLM router registers, with the methods it answers."""
    reg = registration()
    out: dict[str, set[str]] = {}
    for route in reg.router.routes:
        path = f"{reg.prefix}{route.path}"
        out.setdefault(path, set()).update(m for m in route.methods if m not in {"HEAD", "OPTIONS"})
    return out


def test_every_mapped_route_exists_at_its_new_path() -> None:
    paths = migrated_paths()
    missing = [f"{old} -> {new}" for old, new in ROUTE_MAPPING.items() if new not in paths]
    assert missing == [], f"mapped routes absent from the migrated router: {missing}"


def test_every_mapped_route_keeps_its_methods() -> None:
    spec, paths = baseline()["paths"], migrated_paths()
    mismatched = []
    for old, new in ROUTE_MAPPING.items():
        if old not in spec:
            continue
        legacy = {m.upper() for m in spec[old] if m in {"get", "post", "put", "patch", "delete"}}
        if not legacy <= paths.get(new, set()):
            mismatched.append((old, new, sorted(legacy), sorted(paths.get(new, set()))))
    assert mismatched == [], f"method drift: {mismatched}"


def test_every_mapped_route_keeps_its_request_body_schema() -> None:
    spec, drift = baseline()["paths"], []
    components = baseline().get("components", {}).get("schemas", {})
    from gateway.app.main import create_app

    migrated = create_app().openapi()
    for old, new in ROUTE_MAPPING.items():
        legacy_op = (spec.get(old) or {}).get("post")
        new_op = (migrated["paths"].get(new) or {}).get("post")
        if not legacy_op or not new_op:
            continue
        legacy_ref = _body_ref(legacy_op)
        new_ref = _body_ref(new_op)
        if legacy_ref is None and new_ref is None:
            continue
        if _resolve(legacy_ref, components) != _resolve(new_ref, migrated.get("components", {}).get("schemas", {})):
            drift.append((old, new, legacy_ref, new_ref))
    assert drift == [], f"request body drift: {drift}"


def test_no_llm_route_in_the_baseline_is_unaccounted_for() -> None:
    spec, paths = baseline()["paths"], migrated_paths()
    known = {**ROUTE_MAPPING, **ALSO_CARRIED}
    unaccounted = [
        old for old in spec
        if old.startswith("/v1/") and old not in known
        and not old.startswith(OTHER_DOMAINS)
    ]
    assert unaccounted == [], f"baseline LLM routes with no migrated counterpart: {unaccounted}"
    absent = [new for new in known.values() if new not in paths]
    assert absent == [], f"carried routes missing from the migrated router: {absent}"


def test_the_v1_alias_reuses_the_same_router_object() -> None:
    """Plan 07 deletes the alias; it must not be a second implementation."""
    from gateway.llm.api.routes import alias_registration

    alias = alias_registration()
    assert alias.router is registration().router
    assert alias.prefix == "/v1"
    assert alias.deprecated is True


def _body_ref(operation: dict[str, Any]) -> str | None:
    content = (operation.get("requestBody") or {}).get("content") or {}
    schema = (content.get("application/json") or {}).get("schema") or {}
    return schema.get("$ref")


def _resolve(ref: str | None, schemas: dict[str, Any]) -> Any:
    if ref is None:
        return None
    return schemas.get(ref.rsplit("/", 1)[-1])
