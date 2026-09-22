"""OpenAI adapter, isolated from compatible providers for independent evolution."""

import httpx

from gateway.llm.providers.openai_compatible import OpenAICompatibleProvider


class OpenAIProvider(OpenAICompatibleProvider):
    def __init__(self, name: str, api_key: str, model: str, client: httpx.AsyncClient) -> None:
        super().__init__(name, api_key, model, "https://api.openai.com/v1", client, vision=True)
