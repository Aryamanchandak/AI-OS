class SourceUnavailableError(RuntimeError):
    """Raised when a configured research source cannot serve a query."""


class UnavailableClient:
    source_name = "research source"

    async def search(self, *args, **kwargs):
        raise SourceUnavailableError(
            f"{self.source_name} is unavailable because the vendored "
            "research_tools implementation is missing from this repository."
        )

