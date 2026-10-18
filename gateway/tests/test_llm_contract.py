"""Route contract for the migrated LLM router.

Checks that every legacy GLC path still answers at its new `/api/llm` path and
that the `/v1` alias is the same router, not a second implementation.
`test_llm_streaming.py` covers the SSE half of the contract.
"""

from __future__ import annotations

from gateway.llm.api.routes import registration

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


def test_the_v1_alias_reuses_the_same_router_object() -> None:
    """Plan 07 deletes the alias; it must not be a second implementation."""
    from gateway.llm.api.routes import alias_registration

    alias = alias_registration()
    assert alias.router is registration().router
    assert alias.prefix == "/v1"
    assert alias.deprecated is True
