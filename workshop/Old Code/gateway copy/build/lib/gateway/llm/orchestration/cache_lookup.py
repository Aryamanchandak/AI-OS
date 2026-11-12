from gateway.llm.cache import SemanticCache
from gateway.llm.orchestration.context import PipelineContext


class CacheLookupStage:
    def __init__(self, cache: SemanticCache | None) -> None: self.cache = cache
    async def run(self, context: PipelineContext) -> None:
        request = context.request
        context.cache_fields = {"model": request.model, "provider": request.provider, "profile": request.profile, "system": request.system, "tools": [x.model_dump() for x in request.tools or []], "response_format": request.response_format.model_dump(by_alias=True) if request.response_format else None, "temperature": request.temperature}
        if self.cache is None: return
        lookup = await self.cache.lookup(
            context.prompt_text,
            context.cache_fields,
            principal=context.principal.present(),
            opt_in=request.semantic_cache,
            temperature=request.temperature,
            has_tools=bool(request.tools),
            stream=request.stream,
        )
        context.cache_embedding = lookup.embedding
        if lookup.hit and lookup.response:
            context.cache_hit = True; context.output = dict(lookup.response); context.output["cache"] = lookup.as_dict(); context.output["cost"] = {"total_usd": 0.0, "price_source": "semantic-cache-hit"}
