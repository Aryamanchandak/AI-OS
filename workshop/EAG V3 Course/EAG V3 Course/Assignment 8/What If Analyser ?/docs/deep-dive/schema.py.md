# schema.py — Technical Documentation

**Last updated:** 2026-07-23  
**Lines of code:** 133  
**Language:** Python

---

## 1. What This File Does (Plain English)

This file defines the shapes of every causal object the application passes around. It is the shared dictionary that lets extraction, calculation, and writing agree on what a node, connection, uncertainty, and whole graph look like. It defines one editable in-memory form for the application and one stricter form for receiving structured model output.

---

## 2. The 30-Second Mental Model

Gemini fills the Pydantic `*In` classes; `extract.py` then copies that response into the mutable dataclasses `Node`, `Edge`, `Unknown`, and `Graph`; propagation updates the copied `Node` fields while the rest of the pipeline reads the same vocabulary.

---

## 3. Architecture at a Glance

```text
[Gemini JSON]
      │ validated/parses as
      ▼
[NodeIn / EdgeIn / UnknownIn / CausalGraphOut]
      │ copied by extract._build_graph()
      ▼
[Node / Edge / Unknown / Graph dataclasses]
      │
      ├──▶ propagate.py mutates a deep copy
      └──▶ main.py + synth.py read results
```

---

## 4. Execution Walkthrough — The Heart of This Document

### Layer 1 — The Story in Plain English

Nothing is actively calculated here. When Python imports the file, it registers a set of reusable containers. Later, the model-facing containers check the broad shape of Gemini's response, while the application-facing containers hold the graph and its changing scenario results.

### Layer 2 — The Same Story With More Detail

Importing `schema.py` defines three aliases, four dataclasses, and four Pydantic models. `Node` contains both extracted identity and resolved scenario state. `CausalGraphOut` nests `NodeIn`, `EdgeIn`, and `UnknownIn`, allowing the Google SDK to request and parse structured JSON. The module creates no instances and performs no I/O by itself.

### Layer 3 — The Full Technical Reality

The aliases at L21–25 are documentation rather than runtime validation: `Sign`, `Magnitude`, and `NodeType` are merely `int` or `str`. The dataclasses at L28–71 define mutable objects. In particular, `Node.sign`, `magnitude`, `contested`, and `trace` default at L37–42 and are later overwritten on a deep copy by `propagate()`. `field(default_factory=list)` at L42 prevents different `Node` instances from sharing one trace list.

The Pydantic layer begins at L86. `NodeIn.node_type` and `EdgeIn.strength` use `Literal` constraints (L93, L104), but `EdgeIn.sign` stays an unconstrained integer (L101–103) because the structured-output schema cannot reliably express the integer enum. `extract._validate()` is therefore the actual `-1/+1` gate. `CausalGraphOut` at L122–133 constrains nesting and types but does not encode the documented 8–15 node, one-intervention, 3–5 outcome, or exactly-two-unknown cardinalities.

---

## 5. Data Flow — What Comes In, What Comes Out

Plainly, a structured model response comes in and an application graph eventually comes out, although the conversion itself occurs in `extract.py`.

With names, Gemini returns a `CausalGraphOut` containing lists of `NodeIn`, `EdgeIn`, and `UnknownIn`; `model_dump()` turns it into dictionaries; `_build_graph()` creates `Graph(nodes=[Node(...)], edges=[Edge(...)], unknowns=[Unknown(...)])`.

Concretely, `{"id":"n1","label":"Repo rate","node_type":"intervention"}` satisfies `NodeIn` at L86–93. It becomes `Node("n1", "Repo rate", "intervention", sign=0, magnitude="med", contested=False, trace=[])` until propagation resolves it. An edge sign of `2` still passes `EdgeIn` and is rejected only later by `extract._validate()`.

---

## 6. State & Side Effects

This file remembers nothing globally beyond class and alias definitions, and it changes no external system.

Its mutable state lives only in instances created elsewhere. `Node.trace` is per instance, while `Graph.nodes`, `edges`, and `unknowns` are ordinary caller-owned lists (L69–71). There is no file access, network access, environment lookup, cache, or singleton.

Technically, class definitions are installed in Python's module cache on first import. Instance lifetimes are controlled by callers; loss of a `Graph` loses all in-memory analysis because there is no persistence layer.

---

## 7. Control Flow Map

There are no runtime branches or loops after import-time class construction.

The only conditional behavior is delegated to Pydantic validation when instances are created: `Literal` fields reject values outside their allowed strings, required fields reject omissions, and plain `int`/`str` aliases remain permissive.

Import execution is linear: imports (L14–19), aliases (L21–25), dataclasses (L28–71), then Pydantic schemas (L86–133). There are no early returns or entry-point blocks.

---

## 8. Function & Class Reference

| Name | Lines | What it actually does (2–3 honest sentences) |
|---|---|---|
| `Node` | L28–42 | Stores one causal variable plus mutable scenario results. Its defaults are unresolved placeholders, not a computed baseline. |
| `Edge` | L45–53 | Stores a signed directed link and its model-written mechanism. It does not validate endpoints, sign, strength, or sentence count. |
| `Unknown` | L56–62 | Associates a binary question with the node whose sign it overrides. It does not enforce binary answers. |
| `Graph` | L65–71 | Bundles lists of nodes, edges, and unknowns. It does not itself guarantee a DAG or any cardinality rule. |
| `NodeIn` | L86–93 | Validates the model-facing node shape and node-type literal. |
| `EdgeIn` | L96–107 | Validates basic edge field types and the strength literal; sign semantics remain externally validated. |
| `UnknownIn` | L110–119 | Validates presence and string types for an uncertainty. |
| `CausalGraphOut` | L122–133 | Defines the nested response type sent to Gemini as `response_schema`; documented count rules are not Pydantic validators. |

---

## 9. External Dependencies

`dataclasses` and `typing.Literal` are standard-library dependencies used at L16–17. Pydantic's `BaseModel` and `Field` are imported at L19 and used at L86–133; if Pydantic is missing, every application path importing `schema.py` fails immediately. No external API is contacted.

---

## 10. Error Handling Reality

There is no local error handling. Import errors and Pydantic validation errors propagate to the caller.

Invalid `Literal` values fail when model instances are created, but invalid graph topology and semantic constraints do not. Dataclass construction accepts malformed values without complaint.

There are no `try` blocks. A missing Pydantic installation crashes at L19; shared-schema mismatches surface wherever construction or attribute access occurs rather than being normalized here.

---

## 11. Non-Technical Decisions Embedded in the Code

- **Mutable internal representation** (L28–71) — scenario resolution is designed to write onto copied nodes rather than create immutable results.
- **Three coarse magnitude buckets** (L24) — the system intentionally avoids numeric confidence.
- **Validation split across layers** (L79–82) — schema parsing handles shape; `extract.py` owns semantic graph rules.
- **Defaults imply “unresolved,” not “neutral forecast”** (L37–42) — callers must propagate before presenting results.

---

## 12. Honest Gaps and Risks

- `Sign`, `Magnitude`, and `NodeType` (L23–25) do not constrain runtime dataclass values.
- `Graph.unknowns` says “exactly 2” only in a comment (L71); hand-built graphs can violate it.
- Pydantic descriptions such as “ONE sentence” (L105–107) guide the model but do not validate sentence count.
- Duplicate node IDs, self-edges, missing endpoints, and cycles are all representable here.

---

## 13. Developer Notes — Read Before Editing

Changes to field names or types must be coordinated with `extract._build_graph()`, propagation mutations, Streamlit rendering, tests, and Gemini's response schema. Adding a required Pydantic field changes the model contract immediately. Adding mutable dataclass defaults requires `default_factory`, not a shared list/dict literal.
