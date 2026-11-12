"""Architecture guard: every model operation must be routed through GLC v5
by a named task profile, never by a direct provider or model override."""

from __future__ import annotations

import ast
from pathlib import Path

import yaml

SOURCE_ROOT = Path(__file__).parents[1] / "src" / "gateway" / "ingestion"
PROJECT_ROOT = Path(__file__).parents[1]
GLC_PROFILES_PATH = PROJECT_ROOT / "config" / "profiles.yaml"

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
    Path("src/gateway/ingestion/sources/book_metadata.py"): {"urllib.request"},
    Path("src/gateway/ingestion/http_client.py"): {"httpx"},
}
FORBIDDEN_LEGACY_TOKENS = ("llm_gateway", "llm-gateway-v7")
ROUTING_CALL_METHODS = {"chat", "embed"}
FORBIDDEN_ROUTING_KEYWORDS = {"provider", "model"}
# Every place a production process can actually issue a model call: the
# library code, the review-cockpit server that composes it, and the
# operator smoke-test scripts. Excludes tests/, which legitimately builds
# fakes and protocol doubles that declare `provider`/`model` parameters.
PRODUCTION_ROOTS = (SOURCE_ROOT, PROJECT_ROOT / "scripts")


def _python_sources() -> list[Path]:
    return sorted(SOURCE_ROOT.rglob("*.py"))


def _production_sources() -> list[Path]:
    return sorted(path for root in PRODUCTION_ROOTS for path in root.rglob("*.py"))


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


def test_only_runner_constructs_the_shared_glc_client() -> None:
    loaders: list[tuple[Path, int]] = []
    direct_imports: list[tuple[Path, str]] = []

    for path in _python_sources():
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
        direct_imports.extend(
            (path.relative_to(PROJECT_ROOT), module)
            for module in _imported_modules(tree)
            if module == "glc" or module.startswith("glc.")
        )
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
                continue
            if node.func.id != "GatewayHTTPClient":
                continue
            loaders.append((path.relative_to(PROJECT_ROOT), node.lineno))

    runner = Path("src/gateway/ingestion/runner.py")
    assert direct_imports == []
    assert len(loaders) == 1
    assert loaders[0][0] == runner


def test_project_declares_no_direct_model_provider_dependency() -> None:
    pyproject = (PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8").lower()
    for dependency in ("anthropic", "openai", "ollama", "google-generativeai"):
        assert dependency not in pyproject


def test_llm_gateway_is_absent_from_source_scripts_tests_and_dependency_metadata() -> None:
    """Legacy-package guard: this test's own source necessarily names the
    forbidden tokens it searches for, so it excludes itself from the scan."""

    self_path = Path(__file__).resolve()
    violations: list[str] = []
    for directory in (SOURCE_ROOT, PROJECT_ROOT / "scripts", PROJECT_ROOT / "ingestion_tests"):
        for path in sorted(directory.rglob("*.py")):
            if path.resolve() == self_path:
                continue
            text = path.read_text(encoding="utf-8")
            for token in FORBIDDEN_LEGACY_TOKENS:
                if token in text:
                    violations.append(f"{path.relative_to(PROJECT_ROOT)} references {token!r}")

    for filename in ("pyproject.toml", "uv.lock"):
        file_path = PROJECT_ROOT / filename
        if not file_path.is_file():
            continue
        text = file_path.read_text(encoding="utf-8")
        for token in FORBIDDEN_LEGACY_TOKENS:
            if token in text:
                violations.append(f"{filename} references {token!r}")

    assert violations == []


def test_no_production_model_call_passes_provider_or_model_routing_arguments() -> None:
    """AST guard: `chat()`/`embed()` call sites may never route by provider or
    model directly -- only a named GLC profile. `provider`/`model` remain
    legal as plain parameter *declarations* on Protocol classes (they mirror
    `glc.client.LLM`'s own signature) and as ordinary variable/field names
    describing returned metadata or validation expectations; only an actual
    call-site keyword argument on `.chat(...)`/`.embed(...)` is forbidden.

    Scans every production process, not just the library: the review-cockpit
    server and operator smoke-test scripts can issue model calls too, and a
    guard that only watched src/ingestion already missed one regression
    (cockpit/server.py's `cleanup_provider=`) during this migration.
    """

    violations: list[str] = []
    for path in _production_sources():
        relative_path = path.relative_to(PROJECT_ROOT)
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            if node.func.attr not in ROUTING_CALL_METHODS:
                continue
            for keyword in node.keywords:
                if keyword.arg in FORBIDDEN_ROUTING_KEYWORDS:
                    violations.append(
                        f"{relative_path}:{node.lineno} calls .{node.func.attr}() "
                        f"with {keyword.arg}="
                    )
    assert violations == []


def test_required_profile_constants_exist_in_the_glc_profile_catalogue() -> None:
    from gateway.ingestion.config import IntakeConfig, SegmentationConfig
    from gateway.ingestion.extraction.gateway import EXTRACTION_CHAT_PROFILE
    from gateway.ingestion.sources.book_metadata import COVER_CLASSIFICATION_PROFILE
    from gateway.ingestion.vector.vector_store import EMBEDDING_GLC_PROFILE

    catalogue = yaml.safe_load(GLC_PROFILES_PATH.read_text(encoding="utf-8"))
    chat_profiles = set(catalogue.get("chat", {}))
    embedding_profiles = set(catalogue.get("embedding", {}))

    default_intake = IntakeConfig(drop_folder=Path("/tmp/does-not-matter"))
    required_chat_profiles = {
        EXTRACTION_CHAT_PROFILE,
        SegmentationConfig().chat_profile,
        default_intake.cleanup_profile,
        default_intake.spelling_review_profile,
        COVER_CLASSIFICATION_PROFILE,
    }
    assert required_chat_profiles <= chat_profiles
    assert {EMBEDDING_GLC_PROFILE} <= embedding_profiles


def test_cover_classification_profile_resolves_to_a_local_only_provider() -> None:
    """Guard the companion gateway's exact profile pin, not just our call
    site, by reading GLC's own profile catalogue instead of a hardcoded
    gateway internals path."""

    catalogue = yaml.safe_load(GLC_PROFILES_PATH.read_text(encoding="utf-8"))
    spec = catalogue["chat"]["cover-classification-v1"]
    cloud_prefixes = ("anthropic-", "openai-", "gemini-")
    assert not str(spec["provider"]).startswith(cloud_prefixes)
    assert spec["provider"] == "cover-vision-local"


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
