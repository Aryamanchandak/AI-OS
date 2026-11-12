"""
llm.py — Centralized Anthropic call with tenacity 429/5xx backoff.

All three Anthropic call sites (extract, synthesize, speaker-resolve) route through
call_anthropic() so the retry policy is applied consistently.
"""

import os
from typing import Optional

import anthropic
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)


@retry(
    retry=retry_if_exception_type(
        (anthropic.RateLimitError, anthropic.InternalServerError, anthropic.APIConnectionError)
    ),
    wait=wait_exponential(multiplier=1, min=4, max=60),
    stop=stop_after_attempt(5),
    reraise=True,
)
def call_anthropic(
    *,
    model: str,
    max_tokens: int,
    messages: list[dict],
    system: Optional[str] = None,
) -> str:
    """
    Call the Anthropic Messages API and return the text of the first content block.
    Retries on rate-limit (429), internal server errors (5xx), and connection errors
    with exponential backoff (4s → 60s, up to 5 attempts).
    """
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    kwargs: dict = {}
    if system is not None:
        kwargs["system"] = system
    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        messages=messages,
        **kwargs,
    )
    return response.content[0].text
