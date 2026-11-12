# overlay/ — Phase 2 seam (holdings join)

Deliberately empty in Phase 1. The Phase 2 portfolio overlay lives here:
joining firm holdings / security master onto transmission chains.

The join key is `node_id`, which is already present on every `ChainStep`
(`src/mirfish/schemas.py`). Nothing in Phase 1 code may import from this
module, and nothing here may be built in Phase 1 — no firm data, no holdings.
