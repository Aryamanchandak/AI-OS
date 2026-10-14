from __future__ import annotations

import sys
from pathlib import Path


HERE = Path(__file__).parent.parent
sys.path.insert(0, str(HERE))

import main as M


def test_large_base64_image_block_does_not_inflate_estimate():
    huge_image_data = "A" * 2_900_000  # ~2.2 MB image, base64-encoded
    messages = [{
        "role": "user",
        "content": [
            {"type": "text", "text": "Is this a book cover?"},
            {"type": "image", "media_type": "image/jpeg", "data": huge_image_data},
        ],
    }]

    est = M._est_tokens(messages, None, max_tokens=512)

    assert est < 3000


def test_plain_string_content_estimate_is_unchanged():
    messages = [{"role": "user", "content": "hello world, this is a prompt"}]

    est = M._est_tokens(messages, None, max_tokens=100)

    assert est == len("hello world, this is a prompt") // 4 + 100


def test_text_and_image_blocks_both_contribute_without_double_counting():
    text = "Describe this cover in detail." * 10
    messages = [{
        "role": "user",
        "content": [
            {"type": "text", "text": text},
            {"type": "image", "media_type": "image/jpeg", "data": "B" * 500_000},
        ],
    }]

    est = M._est_tokens(messages, None, max_tokens=0)

    assert est == len(text) // 4 + M._EST_TOKENS_PER_IMAGE
