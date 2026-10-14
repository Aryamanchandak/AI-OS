from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
import os
from pathlib import Path
import shutil
from typing import Callable

from ingestion.config import IngestionConfig
from ingestion.content_store import ContentStore
from ingestion.extraction.gateway import EXTRACTION_CHAT_PROFILE
from ingestion.intake.funnel import CONTROL_FILENAMES
from ingestion.kg.kg_store import KGStore
from ingestion.runner import GatewayClient, _shared_gateway_client
from ingestion.sources import book_metadata, obsidian
from ingestion.sources.page_scanner import store as page_store
from ingestion.store import IngestionStore
from ingestion.vector.vector_store import VectorStore, validate_embedding

_LOCAL_MODEL_PREFLIGHT_MAX_TOKENS = 64


@dataclass(frozen=True)
class CheckResult:
    name: str
    ok: bool
    detail: str
    retryable: bool


def _check(
    name: str, operation: Callable[[], object], *, retryable: bool = True
) -> CheckResult:
    try:
        operation()
    except Exception as error:
        return CheckResult(name, False, f"{type(error).__name__}: {error}", retryable)
    return CheckResult(name, True, "ok", retryable)


def _ensure_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    if not path.is_dir() or not os.access(path, os.W_OK):
        raise PermissionError(f"directory is not writable: {path}")


def _folder_files(drop: Path) -> list[Path]:
    """The files a run would actually take in, not every file on disk.

    Mirrors ``RunCoordinator._discover``: top-level files plus one level of
    book folders, skipping dotfiles, the intake control files that
    ``scan_drop_folder`` itself skips, and anything nested deeper
    (``_retake/`` above all). ``rglob("*")`` counted files no run ever
    touches, so a drop folder holding nothing but a
    ``.DS_Store`` -- which macOS writes into any folder you open -- or nothing
    but already-parked ``_retake/`` photos made preflight demand a running
    local cleanup/spelling model and Apple Vision, and refused a run that had
    no work to do.
    """

    files: list[Path] = []
    for path in sorted(drop.iterdir()):
        if path.name.startswith("."):
            continue
        if path.is_file():
            if path.name not in CONTROL_FILENAMES:
                files.append(path)
            continue
        if not path.is_dir():
            continue
        for child in sorted(path.iterdir()):
            if child.name.startswith(".") or not child.is_file():
                continue
            if child.name == book_metadata.QUERY_FILE:
                continue
            files.append(child)
    return files


def _probe_local_model(gateway: GatewayClient, provider: str) -> None:
    """Require visible output without truncating a model's hidden reasoning."""

    response = gateway.chat(
        "Return exactly OK",
        provider=provider,
        max_tokens=_LOCAL_MODEL_PREFLIGHT_MAX_TOKENS,
        temperature=0,
    )
    if not isinstance(response, dict) or not str(response.get("text", "")).strip():
        raise RuntimeError(f"the {provider} model is not answering")


def run_preflight(config: IngestionConfig) -> tuple[CheckResult, ...]:
    """Run the complete repository preflight and report every failure."""

    results: list[CheckResult] = []
    results.append(_check("configuration", config.validate, retryable=False))
    intake = config.intake
    if intake is None:
        results.append(
            CheckResult(
                "intake_configuration",
                False,
                "IngestionConfig.intake is required for repository runs",
                False,
            )
        )
        return tuple(results)

    def paths() -> None:
        _ensure_directory(config.database_root)
        for path in (
            config.raw_root,
            config.envelope_root,
            config.database_root / "sqlite",
            config.database_root / "reports",
        ):
            _ensure_directory(path)

    results.append(_check("paths", paths, retryable=False))

    def ledger() -> None:
        value = IngestionStore(config.ledger_path)
        value.close()

    results.append(_check("ingestion_sqlite", ledger))

    def content() -> None:
        value = ContentStore(config.content_db_path)
        value.close()

    results.append(_check("content_sqlite", content))
    results.append(
        _check(
            "page_scanner_sqlite",
            lambda: page_store.init_db(config.page_scanner_db_path),
        )
    )

    def drop_folder() -> None:
        if not intake.drop_folder.is_dir():
            raise NotADirectoryError(intake.drop_folder)
        controls = [
            name
            for name in (book_metadata.CACHE_NAME, book_metadata.QUERY_FILE)
            if (intake.drop_folder / name).exists()
        ]
        if controls:
            raise RuntimeError(
                "drop folder contains book control files: " + ", ".join(controls)
            )

    results.append(_check("drop_folder", drop_folder, retryable=False))

    resolved_vault: Path | None = None

    def vault() -> None:
        nonlocal resolved_vault
        resolved_vault = (
            intake.vault_path or obsidian.discover_vault_path()
        ).expanduser().resolve()
        if not resolved_vault.is_dir():
            raise NotADirectoryError(resolved_vault)
        obsidian.load_filters()

    results.append(_check("obsidian", vault, retryable=False))
    results.append(
        _check(
            "vector_store",
            lambda: VectorStore(config.chroma_path),
        )
    )

    def neo4j() -> None:
        kg = KGStore(strict=True, expected_data_root=config.neo4j_path)
        try:
            kg.preflight()
        finally:
            kg.close()

    results.append(_check("neo4j", neo4j))

    gateway_holder: list[GatewayClient] = []

    def gateway_profiles() -> None:
        gateway = _shared_gateway_client()
        gateway_holder.append(gateway)
        # Cover classification is unreachable from a coordinator run — the
        # ImageExtractor is built with `metadata_client=None` — so its profile
        # is not a dependency of this run and is not checked.
        profiles = [EXTRACTION_CHAT_PROFILE]
        if config.segmentation.mode == "gateway":
            profiles.append(config.segmentation.chat_profile)
        for profile in profiles:
            gateway.resolve_chat_profile(profile)
        validate_embedding(gateway.embed("repository coordinator preflight", provider="ollama"))

    results.append(_check("gateway_profiles", gateway_profiles))

    if config.segmentation.mode == "gateway":
        def segmentation_model() -> None:
            """Ping the model that splits notes into highlights.

            Resolving the profile above only proves the gateway knows the
            profile. An Obsidian-only run — empty drop folder, so the cleanup
            check below never runs — otherwise passes preflight with the local
            model stopped and dies partway through parsing instead.
            """

            gateway = gateway_holder[0] if gateway_holder else _shared_gateway_client()
            response = gateway.chat(
                "Return exactly OK",
                profile=config.segmentation.chat_profile,
                max_tokens=8,
                temperature=0,
            )
            if not isinstance(response, dict) or not str(response.get("text", "")).strip():
                raise RuntimeError("the segmentation model is not answering")

        results.append(_check("segmentation_model", segmentation_model))

    files = _folder_files(intake.drop_folder) if intake.drop_folder.is_dir() else []
    has_image = any(
        path.suffix.casefold()
        in {".jpg", ".jpeg", ".png", ".heic", ".heif", ".tiff", ".tif", ".bmp"}
        for path in files
    )
    has_pdf = any(path.suffix.casefold() == ".pdf" for path in files)
    has_doc = any(path.suffix.casefold() == ".doc" for path in files)

    if has_image:
        def cleanup_model() -> None:
            if intake.cleanup_provider not in {"gemma", "phi4-local"}:
                raise ValueError("cleanup provider is not local")
            gateway = gateway_holder[0] if gateway_holder else _shared_gateway_client()
            _probe_local_model(gateway, intake.cleanup_provider)

        results.append(_check("cleanup_model", cleanup_model))

    if files:
        # Component 8's human spelling review runs on every intake item that
        # reaches the cleanup gate (any file type, not only images) --
        # checked here, not gated on has_image, so a PDF/DOCX/Markdown-only
        # run still fails preflight instead of dying mid-run when the local
        # spelling model is unreachable.
        def spelling_review_model() -> None:
            if intake.spelling_review_provider not in {"gemma", "phi4-local"}:
                raise ValueError("spelling review provider is not local")
            gateway = gateway_holder[0] if gateway_holder else _shared_gateway_client()
            _probe_local_model(gateway, intake.spelling_review_provider)

        results.append(_check("spelling_review_model", spelling_review_model))

    if has_image or has_pdf:
        results.append(
            _check("apple_vision_ocr", lambda: import_module("ocrmac"))
        )
    if has_doc:
        results.append(
            _check(
                "textutil",
                lambda: shutil.which("textutil")
                or (_ for _ in ()).throw(RuntimeError("textutil is not on PATH")),
                retryable=False,
            )
        )
    return tuple(results)
