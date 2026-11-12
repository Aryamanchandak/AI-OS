from __future__ import annotations

import sys
from pathlib import Path


HERE = Path(__file__).parent.parent
sys.path.insert(0, str(HERE))

import providers


IMAGE_CONTENT = [
    {"type": "text", "text": "Describe this cover."},
    {"type": "image", "media_type": "image/jpeg", "data": "aW1hZ2U="},
]
MESSAGES = [{"role": "user", "content": IMAGE_CONTENT}]


def test_split_content_blocks_returns_canonical_text_and_images():
    text, images = providers._split_content_blocks(IMAGE_CONTENT)

    assert text == ["Describe this cover."]
    assert images == [
        {"type": "image", "media_type": "image/jpeg", "data": "aW1hZ2U="}
    ]


def test_openai_translates_canonical_image_content():
    translated = providers.OpenAIProvider("key", "gpt-test")._translate_messages(
        MESSAGES, ""
    )

    assert translated == [{
        "role": "user",
        "content": [
            {"type": "text", "text": "Describe this cover."},
            {
                "type": "image_url",
                "image_url": {
                    "url": "data:image/jpeg;base64,aW1hZ2U="
                },
            },
        ],
    }]


def test_anthropic_translates_canonical_image_content():
    translated = providers.AnthropicProvider(
        "key", "claude-test"
    )._translate_messages(MESSAGES)

    assert translated == [{
        "role": "user",
        "content": [
            {"type": "text", "text": "Describe this cover."},
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/jpeg",
                    "data": "aW1hZ2U=",
                },
            },
        ],
    }]


def test_gemini_translates_canonical_image_content():
    translated = providers.GeminiProvider(
        "key", "gemini-test", cache_store=None
    )._translate_messages(MESSAGES)

    assert translated == [{
        "role": "user",
        "parts": [
            {"text": "Describe this cover."},
            {
                "inline_data": {
                    "mime_type": "image/jpeg",
                    "data": "aW1hZ2U=",
                }
            },
        ],
    }]


def test_ollama_moves_images_to_message_sibling_field():
    provider = providers.OllamaProvider("gemma4:12b")

    assert provider._translate_messages(MESSAGES, "") == [{
        "role": "user",
        "content": "Describe this cover.",
        "images": ["aW1hZ2U="],
    }]
    assert provider.capabilities["images"] is True


def test_text_only_messages_remain_strings_for_all_providers():
    messages = [{"role": "user", "content": "hello"}]

    assert providers.OpenAIProvider("key", "gpt-test")._translate_messages(
        messages, ""
    ) == messages
    assert providers.OllamaProvider("gemma4:12b")._translate_messages(
        messages, ""
    ) == messages
