---
id: orch
stage: 0
part: trunk
provides: [I3]
uses: []
builder: claude
reviewer: codex
line_budget: 100 (registry only)
existing: rewrite (nothing suitable found yet)
status: detailed (registry part); assistant part is Stage 5
---

# Loop, registry and assistant: registry part

**Job (Stage 0):** one list of typed tools that anything can call by name.

**Done when:**
1. A fake tool registers.
2. It shows up in `list_tools()` with its JSON schema.
3. A call with good input returns a validated output.
4. A call with bad input is refused before the function runs.

**Build:** `core/registry.py`, as described in I3.

It uses Pydantic for the schemas. Pydantic is already used by the gateway, but it is still a new dependency for this folder.

The shape matches what an agent's tool list and FastMCP expect, so Stage 5 adds callers without changing the registry.

**Delayed:**
- The free-form assistant (Stage 5).
- The scheduler (Stage 3).
- The MCP door (after submission).
- The LangGraph swap (after the capstone is submitted).

The capstone rules ban third-party orchestration frameworks, so the registry and loop stay hand-written until then.
