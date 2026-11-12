import base64
from typing import Any

from gateway.llm.orchestration.context import PipelineContext
from gateway.security.ssrf import fetch_bytes


def _text(content: Any) -> str:
    if isinstance(content, str): return content
    if isinstance(content, list): return "".join(str(x.get("text", "")) for x in content if isinstance(x, dict) and x.get("type") == "text")
    return str(content or "")


class NormalizationStage:
    async def run(self, context: PipelineContext) -> None:
        request = context.request
        context.messages = list(request.messages or [{"role": "user", "content": request.prompt or ""}])
        resolved: list[dict[str, Any]] = []
        for message in context.messages:
            content = message.get("content")
            if not isinstance(content, list):
                resolved.append(message); continue
            blocks: list[Any] = []
            for block in content:
                image = block.get("image_url") if isinstance(block, dict) and block.get("type") == "image_url" else None
                url = image.get("url") if isinstance(image, dict) else image
                if isinstance(url, str) and url.startswith(("http://", "https://")):
                    payload, media_type = await fetch_bytes(url)
                    blocks.append({"type": "image_url", "image_url": {"url": f"data:{media_type};base64,{base64.b64encode(payload).decode()}"}})
                else:
                    blocks.append(block)
            resolved.append({**message, "content": blocks})
        context.messages = resolved
        context.system = request.system
        context.prompt_text = "".join(_text(x.get("content", "")) for x in context.messages)
        system_chars = len(str(request.system or "")); context.estimated_input_tokens = max(1, (len(context.prompt_text) + system_chars + 3) // 4)
