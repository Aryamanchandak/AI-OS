"""Architecture guard: every model operation must use the system LLM Gateway."""

from __future__ import annotations

import ast
from pathlib import Path


SOURCE_ROOT = Path(__file__).parents[1] / "src" / "ingestion"
PROJECT_ROOT = Path(__file__).parents[1]

FORBIDDEN_IMPORT_ROOTS = {
    "anthropic",
    "openai",
    "ollama",
    "google.generativeai",
    "google.genai",
}
FORBIDDEN_NETWORK_MODULES = {
    "aiohttp",
    "httpx",
    "requests",
    "urllib.request",
}
FORBIDDEN_PROVIDER_ENDPOINTS = {
    "api.anthropic.com",
    "api.openai.com",
    "generativelanguage.googleapis.com",
    "localhost:11434",
}
NON_MODEL_NETWORK_EXCEPTIONS = {
    Path("src/ingestion/sources/book_metadata.py"): {"urllib.request"},
    # The one file allowed to make web calls for models: it talks only to the gateway.
    Path("src/ingestion/gateway_client.py"): {"httpx"},
}


def _python_sources() -> list[Path]:
    return sorted(SOURCE_ROOT.rglob("*.py"))


def _imported_modules(tree: ast.AST) -> list[str]:
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.append(node.module)
    return modules


def test_merged_source_has_no_direct_model_provider_or_network_client() -> None:
    violations: list[str] = []
    for path in _python_sources():
        relative_path = path.relative_to(PROJECT_ROOT)
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for module in _imported_modules(tree):
            forbidden_provider = any(
                module == forbidden or module.startswith(f"{forbidden}.")
                for forbidden in FORBIDDEN_IMPORT_ROOTS
            )
            forbidden_network = any(
                module == forbidden or module.startswith(f"{forbidden}.")
                for forbidden in FORBIDDEN_NETWORK_MODULES
            ) and module not in NON_MODEL_NETWORK_EXCEPTIONS.get(relative_path, set())
            if forbidden_provider or forbidden_network:
                violations.append(f"{relative_path} imports {module}")

        source = path.read_text(encoding="utf-8")
        for endpoint in FORBIDDEN_PROVIDER_ENDPOINTS:
            if endpoint in source:
                violations.append(
                    f"{relative_path} contains provider endpoint {endpoint}"
                )

    assert violations == []


def test_only_runner_constructs_the_shared_gateway_client() -> None:
    importers: list[Path] = []
    constructors: list[Path] = []
    client_file = Path("src/ingestion/gateway_client.py")

    for path in _python_sources():
        relative_path = path.relative_to(PROJECT_ROOT)
        if relative_path == client_file:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        if any(
            module == "llm_gateway"
            or module.startswith("llm_gateway.")
            or module == "ingestion.gateway_client"
            for module in _imported_modules(tree)
        ):
            importers.append(relative_path)
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "LLM"
            ):
                constructors.append(relative_path)

    runner = Path("src/ingestion/runner.py")
    assert importers == [runner]
    assert constructors == [runner]


def test_project_declares_no_direct_model_provider_dependency() -> None:
    pyproject = (PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8").lower()
    for dependency in ("anthropic", "openai", "ollama", "google-generativeai"):
        assert dependency not in pyproject


def test_cover_classification_profile_can_never_resolve_to_cloud() -> None:
    """Guard the AI OS gateway's exact profile pin, not just our call site."""

    profiles = (PROJECT_ROOT / "../gateway/config/profiles.yaml").resolve()
    lines = profiles.read_text(encoding="utf-8").splitlines()
    start = next(
        index
        for index, line in enumerate(lines)
        if line.strip() == "cover-classification-v1:"
    )
    provider = next(
        line.split(":", 1)[1].strip()
        for line in lines[start + 1 :]
        if line.strip().startswith("provider:")
    )
    cloud_prefixes = ("anthropic", "openai", "gemini", "together")
    assert not provider.startswith(cloud_prefixes)
    assert provider == "cover-vision-local"


def test_book_cover_calls_are_pinned_to_the_local_only_profile() -> None:
    source = (SOURCE_ROOT / "sources/book_metadata.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    profile_values = [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and node.value.endswith("-classification-v1")
    ]
    assert profile_values == ["cover-classification-v1"]
