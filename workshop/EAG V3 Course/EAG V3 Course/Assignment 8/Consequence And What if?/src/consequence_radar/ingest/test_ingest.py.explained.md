# `ingest/test_ingest.py`

One test, `test_normalise_assigns_stable_ids_and_removes_tracking_duplicates`, covering `normalize_batch` (it does not exercise `pre_read` at all — that function is untested in this file).

It builds a `NewsBatch` with two `NewsItem`s that point at the same page: `https://example.com/x?utm_source=a` and `https://example.com/x`. After `normalize_batch`, it asserts the result has exactly one item and that item's `id` starts with `"N"`.

This verifies two things the module promises: URL canonicalization treats a tracking-parameter variant as the same item as the bare URL (so a batch that accidentally contains both a shared link and a tracked link doesn't create two graph nodes for one news event), and every surviving item gets a generated, prefixed ID rather than depending on caller-supplied IDs. It does not check the ID's stability across separate calls (i.e. it never calls `stable_item_id` directly to compare against `result.items[0].id`), so a regression that changed the hash algorithm but kept the `"N"` prefix would pass this test undetected.
