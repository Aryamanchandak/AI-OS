from fastapi import HTTPException

from gateway.llm.orchestration.context import PipelineContext
from gateway.llm.profiles import ProfileError, ProfileRegistry


class ProfileResolutionStage:
    def __init__(self, profiles: ProfileRegistry) -> None: self.profiles = profiles
    async def run(self, context: PipelineContext) -> None:
        if not context.request.profile: return
        try: spec = self.profiles.resolve("chat", context.request.profile)
        except ProfileError as exc: raise HTTPException(400, str(exc)) from exc
        context.request.provider = spec["provider"]; context.request.model = spec["model"]
