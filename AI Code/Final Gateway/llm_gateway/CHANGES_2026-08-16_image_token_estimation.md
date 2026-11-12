# Fix image token estimation (T57) — 2026-08-16

`_est_tokens` in `main.py` used to stringify each message's entire `content`
value and divide the character count by 4, including any base64 image
payload embedded in a canonical `{"type": "image", "data": ...}` block. A
2.2 MB cover photo (~2.9M base64 characters) inflated the estimate to
~700K "tokens," which `router.py`'s `max_ctx` check rejected before the
request ever reached a provider — even for `cover-vision-local`, whose
`max_ctx` is 262144 and comfortably fits the real image content.

`_est_tokens` now reuses `providers._split_content_blocks` (the same
canonical text/image split every provider's `_translate_messages` already
uses) to separate list-shaped `content`: `text`-type blocks still count
`len(text) // 4` toward the estimate, and `image`-type blocks are excluded
from the character count and instead contribute a fixed
`_EST_TOKENS_PER_IMAGE = 1500` tokens each. Plain-string `content` (the
common non-image path) is unchanged. `system_blocks` handling is unchanged
(text-only in all current call sites).

`1500` is a conservative placeholder, not a measured value — it can
under-estimate a genuinely large/high-resolution image on some providers,
trading "early local rejection" for "possible provider-side overflow
later." Revisit if practice disagrees.

Regression coverage (`tests/test_token_estimation.py`):

```text
.venv/bin/python -m pytest -q

45 passed
```

(baseline before this change: 42 passed; 3 new tests added, no existing
test needed to change.)
