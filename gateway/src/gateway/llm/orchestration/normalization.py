from typing import Any

from gateway.llm.orchestration.context import PipelineContext
from fastapi import HTTPException


def _text(content: Any) -> str:
    if isinstance(content, str): return content
    if isinstance(content, list): return "".join(str(x.get("text", "")) for x in content if isinstance(x, dict) and x.get("type") == "text")
    return str(content or "")


class NormalizationStage:
    async def run(self, context: PipelineContext) -> None:
        request = context.request
        context.messages = list(request.messages or [{"role": "user", "content": request.prompt or ""}])
        for message in context.messages:
            content = message.get("content")
            if not isinstance(content, list):
                continue
            for block in content:
                if not isinstance(block, dict):
                    continue
                kind = block.get("type")
                if kind == "image_url":
                    image = block.get("image_url")
                    url = image.get("url") if isinstance(image, dict) else image
                elif kind in {"image", "input_image"}:
                    source = block.get("source") or {}
                    if isinstance(source, dict) and source.get("type") == "base64":
                        continue
                    url = block.get("url") or (source.get("url") if isinstance(source, dict) else None)
                else:
                    continue
                if not isinstance(url, str) or not url.startswith("data:"):
                    raise HTTPException(400, "Image links are not supported; send the image as a data: URL")
        context.system = request.system
        context.prompt_text = "".join(_text(x.get("content", "")) for x in context.messages)
        system_chars = len(str(request.system or "")); context.estimated_input_tokens = max(1, (len(context.prompt_text) + system_chars + 3) // 4)
