#!/usr/bin/env python3
"""Fail loudly when Gateway's ingestion runtime cannot import normally."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

REQUIRED_MODULES = (
    "gateway.ingestion.config",
    "gateway.ingestion.runner",
    "gateway.ingestion.pipeline",
    "gateway.ingestion.extraction.gateway",
    "gateway.ingestion.kg.kg_store",
    "gateway.ingestion.http_client",
    "chromadb",
    "neo4j",
)


def main() -> None:
    environment_root = Path(sys.prefix).resolve()
    loaded_paths: dict[str, Path] = {}
    for name in REQUIRED_MODULES:
        module = importlib.import_module(name)
        module_file = getattr(module, "__file__", None)
        if not module_file:
            raise RuntimeError(f"{name} has no concrete module file")
        resolved = Path(module_file).resolve()
        if not resolved.is_relative_to(environment_root):
            raise RuntimeError(
                f"{name} loaded outside the runtime environment: {resolved}"
            )
        loaded_paths[name] = resolved

    print("Gateway ingestion runtime imports: PASS")
    print(f"gateway.ingestion.runner: {loaded_paths['gateway.ingestion.runner']}")
    print(f"gateway.ingestion.http_client: {loaded_paths['gateway.ingestion.http_client']}")


if __name__ == "__main__":
    main()
