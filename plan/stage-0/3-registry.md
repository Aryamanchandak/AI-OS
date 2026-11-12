# Bite 3: Tool registry (I3) [AGAIN NOT REALLY SURE WHAT THIS IS ABOUT]

## For you

**What already exists.** Nothing for AI OS. `gateway/src/gateway/providers.py` has a `ProviderRegistry`, which is a different thing: the gateway's internal list of model providers. The registries in `archive/` and `coursework/` come from the EAG course apps and aren't being reused.

**What's being built.** `core/registry.py`, about 100 lines. You mark a function as a "tool" with a name, and the system can then list every tool and call one by name. Bad input gets refused before the function runs. Later, the orchestrator picks from this list to answer your questions. In this bite it's tested with a fake `echo` tool only, so no real tools yet.

**Your input** (write under each one):

1. Build this now, or move it to Stage 1, when the first real tool exists? My recommendation: move it.
   - Your answer:
2. Should the first real tool be "grade a recall answer" (Stage 1)?
   - Your answer:

---

**Goal:** one list of typed tools that anything can call by name (see `nodes/orch.md`).
**Builder:** Claude. **After:** bite 2's project setup. It can run alongside bite 1. **Budget:** about 100 lines.

**Write the tests first:** `tests/contracts/test_i3.py`, with a fake `echo` tool whose input and output are Pydantic models.

- After `@tool("echo")`, the tool appears in `list_tools()` with its name, description and JSON schema.
- `call("echo", good_payload)` returns a dict that matches the output model.
- `call("echo", bad_payload)` is refused, and the function never runs.
- Calling an unknown name is refused.
- Registering the same name twice is refused.

**Build:** `core/registry.py` with `tool`, `call` and `list_tools`, as written in I3.

**Done when:** `pytest tests/contracts/test_i3.py` passes.
**Out of scope:** the assistant loop (Stage 5), the scheduler (Stage 3), the MCP door, and async tools.
