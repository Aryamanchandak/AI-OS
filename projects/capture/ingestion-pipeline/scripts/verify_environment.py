#!/usr/bin/env python3
"""Fail loudly when the runtime is not a complete non-editable installation."""

from __future__ import annotations

import importlib
import site
import sys
from importlib.metadata import version
from pathlib import Path

REQUIRED_MODULES = (
    "ingestion.config",
    "ingestion.runner",
    "ingestion.pipeline",
    "ingestion.extraction.gateway",
    "ingestion.kg.kg_store",
    "llm_gateway.client",
    "llm_gateway.providers",
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

    editable_markers = sorted(
        marker
        for package_root in map(Path, site.getsitepackages())
        for marker in package_root.glob("__editable__.merged_ingestion*.pth")
    )
    if editable_markers:
        rendered = ", ".join(str(path) for path in editable_markers)
        raise RuntimeError(f"editable merged-ingestion markers remain: {rendered}")

    print(
        "runtime imports: PASS "
        f"(merged-ingestion={version('merged-ingestion')}, "
        f"llm-gateway-v7={version('llm-gateway-v7')})"
    )
    print(f"ingestion.runner: {loaded_paths['ingestion.runner']}")
    print(f"llm_gateway.providers: {loaded_paths['llm_gateway.providers']}")


if __name__ == "__main__":
    main()
