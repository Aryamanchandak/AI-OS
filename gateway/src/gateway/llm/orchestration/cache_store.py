from gateway.llm.cache import SemanticCache
from gateway.llm.orchestration.context import PipelineContext


class CacheStoreStage:
    def __init__(self, cache: SemanticCache | None) -> None: self.cache = cache
    async def run(self, context: PipelineContext) -> None:
        if self.cache and not context.cache_hit and context.output and context.cache_embedding is not None:
            self.cache.store(context.cache_fields, context.output, context.cache_embedding)
