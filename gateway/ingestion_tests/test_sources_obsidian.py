from __future__ import annotations

import json
from pathlib import Path

import pytest

from gateway.ingestion.config import IngestionConfig
from gateway.ingestion.pipeline import UnifiedIngestionPipeline
from gateway.ingestion.sources.obsidian import (
    ObsidianConfigError,
    ObsidianFilterError,
    capture_book_highlights,
    capture_obsidian_vault,
    discover_vault_path,
    load_filters,
)


def _write_highlights_doc(vault: Path, slug: str, *, passages: list[tuple[int, str]]) -> Path:
    """passages: (page_scanner_id, passage_text) pairs, in document order."""
    doc = vault / "Page Scanners" / slug / f"{slug}-highlights.md"
    doc.parent.mkdir(parents=True, exist_ok=True)
    lines = ["<!-- page_scanner_highlights_doc -->", f"# {slug} — highlights", ""]
    current_page: int | None = None
    for passage_id, (page_id, text) in enumerate(passages, start=100):
        if page_id != current_page:
            lines.append(f"<!-- page_scanner_id: {page_id} -->")
            lines.append(f"## p{page_id}")
            lines.append("")
            current_page = page_id
        lines.append(f"<!-- page_scanner_passage: {passage_id} -->")
        lines.extend(text.splitlines())
        lines.append(f"<!-- /page_scanner_passage: {passage_id} -->")
        lines.append("")
    doc.write_text("\n".join(lines).rstrip("\n") + "\n", encoding="utf-8")
    return doc


def _make_vault(tmp_path: Path) -> Path:
    vault = tmp_path / "vault"
    (vault / ".obsidian").mkdir(parents=True)
    (vault / ".trash").mkdir(parents=True)
    (vault / "Notion").mkdir(parents=True)
    (vault / "Daily Notes").mkdir(parents=True)
    (vault / "note.md").write_text("Top level note", encoding="utf-8")
    (vault / ".obsidian" / "workspace.md").write_text("app internals", encoding="utf-8")
    (vault / ".trash" / "deleted.md").write_text("trashed", encoding="utf-8")
    (vault / "Notion" / "import.md").write_text("bulk import", encoding="utf-8")
    (vault / "Daily Notes" / "today.md").write_text("daily note", encoding="utf-8")
    return vault


def test_discover_vault_path_prefers_existing_vault(tmp_path: Path) -> None:
    real_vault = tmp_path / "real-vault"
    real_vault.mkdir()
    config_path = tmp_path / "obsidian.json"
    config_path.write_text(
        json.dumps(
            {
                "vaults": {
                    "missing": {"path": str(tmp_path / "gone")},
                    "real": {"path": str(real_vault)},
                }
            }
        ),
        encoding="utf-8",
    )
    assert discover_vault_path(config_path) == real_vault.resolve()


def test_discover_vault_path_raises_without_any_vault(tmp_path: Path) -> None:
    config_path = tmp_path / "obsidian.json"
    config_path.write_text(json.dumps({"vaults": {}}), encoding="utf-8")
    with pytest.raises(ObsidianConfigError):
        discover_vault_path(config_path)


def test_load_filters_default_excludes_are_shipped(tmp_path: Path) -> None:
    filters_path = tmp_path / "obsidian_filters.txt"
    filters_path.write_text(
        "exclude .obsidian\nexclude .trash\nexclude Notion\n", encoding="utf-8"
    )
    includes, excludes = load_filters(filters_path)
    assert includes == []
    assert set(excludes) == {".obsidian", ".trash", "Notion"}


def test_load_filters_missing_file_is_permissive(tmp_path: Path) -> None:
    assert load_filters(tmp_path / "nope.txt") == ([], [])


def test_load_filters_rejects_malformed_rule_loudly(tmp_path: Path) -> None:
    filters_path = tmp_path / "obsidian_filters.txt"
    filters_path.write_text("exclude .obsidian\nbogus rule here\n", encoding="utf-8")
    with pytest.raises(ObsidianFilterError):
        load_filters(filters_path)


def test_load_filters_rejects_rule_with_no_pattern(tmp_path: Path) -> None:
    filters_path = tmp_path / "obsidian_filters.txt"
    filters_path.write_text("exclude\n", encoding="utf-8")
    with pytest.raises(ObsidianFilterError):
        load_filters(filters_path)


def test_capture_obsidian_vault_applies_exclude_precedence_and_direct_captures(
    tmp_path: Path,
) -> None:
    vault = _make_vault(tmp_path)
    filters_path = tmp_path / "obsidian_filters.txt"
    filters_path.write_text(
        "exclude .obsidian\nexclude .trash\nexclude Notion\n", encoding="utf-8"
    )
    config = IngestionConfig(database_root=tmp_path / "Database")

    with UnifiedIngestionPipeline(config) as pipeline:
        outcomes = capture_obsidian_vault(pipeline, vault=vault, filters_path=filters_path)
        origins = sorted(
            Path(pipeline.store.get_source(item.source_record_id)["origin"]).name
            for item in outcomes
        )
        assert origins == ["note.md", "today.md"]

        # No separate ledger/note_lineage table -- capture() is the only write path.
        table_names = {
            row["name"]
            for row in pipeline.store._conn.execute(  # noqa: SLF001 -- verifying no extra table
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        assert "note_lineage" not in table_names


def test_capture_obsidian_vault_include_allowlist(tmp_path: Path) -> None:
    vault = _make_vault(tmp_path)
    filters_path = tmp_path / "obsidian_filters.txt"
    filters_path.write_text("include Daily Notes\n", encoding="utf-8")
    config = IngestionConfig(database_root=tmp_path / "Database")

    with UnifiedIngestionPipeline(config) as pipeline:
        outcomes = capture_obsidian_vault(pipeline, vault=vault, filters_path=filters_path)
        origins = [
            Path(pipeline.store.get_source(item.source_record_id)["origin"]).name
            for item in outcomes
        ]
        assert origins == ["today.md"]


def test_capture_obsidian_vault_isolates_one_bad_note_from_the_rest(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "good.md").write_text("A healthy note.", encoding="utf-8")
    # A NUL byte makes normalize_source raise MalformedSourceError, which
    # pipeline.capture() re-raises after quarantining.
    (vault / "malformed.md").write_bytes(b"bad\x00byte")
    (vault / "also_good.md").write_text("Another healthy note.", encoding="utf-8")
    config = IngestionConfig(database_root=tmp_path / "Database")

    with UnifiedIngestionPipeline(config) as pipeline:
        outcomes = capture_obsidian_vault(pipeline, vault=vault)
        origins = sorted(
            Path(pipeline.store.get_source(item.source_record_id)["origin"]).name
            for item in outcomes
        )
        # The malformed note is skipped, not fatal to the rest of the batch.
        assert origins == ["also_good.md", "good.md"]


def test_capture_obsidian_vault_is_idempotent_and_records_metadata(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "note.md").write_text("hello", encoding="utf-8")
    filters_path = tmp_path / "obsidian_filters.txt"
    filters_path.write_text("", encoding="utf-8")
    config = IngestionConfig(database_root=tmp_path / "Database")

    with UnifiedIngestionPipeline(config) as pipeline:
        first = capture_obsidian_vault(pipeline, vault=vault, filters_path=filters_path)
        second = capture_obsidian_vault(pipeline, vault=vault, filters_path=filters_path)

        assert all(not item.exact_duplicate for item in first)
        assert all(item.exact_duplicate for item in second)

        source = pipeline.store.get_source(first[0].source_record_id)
        metadata = json.loads(source["metadata_json"])
        assert metadata["vault_relative_path"] == "note.md"
        assert metadata["note_title"] == "note"
        assert metadata["origin_kind"] == "obsidian_note"


def test_capture_obsidian_vault_includes_page_scanners_folder_with_spaces(
    tmp_path: Path,
) -> None:
    vault = tmp_path / "vault"
    note = vault / "Page Scanners" / "atomic-habits" / "page.md"
    note.parent.mkdir(parents=True)
    note.write_text("# Atomic Habits\n\n> A reviewed passage.\n", encoding="utf-8")
    filters_path = tmp_path / "obsidian_filters.txt"
    filters_path.write_text(
        "exclude .obsidian\nexclude .trash\nexclude Notion\nexclude Readwise\n",
        encoding="utf-8",
    )
    config = IngestionConfig(database_root=tmp_path / "Database")

    with UnifiedIngestionPipeline(config) as pipeline:
        outcomes = capture_obsidian_vault(
            pipeline, vault=vault, filters_path=filters_path
        )
        assert len(outcomes) == 1
        source = pipeline.store.get_source(outcomes[0].source_record_id)
        metadata = json.loads(source["metadata_json"])
        assert metadata["vault_relative_path"] == (
            "Page Scanners/atomic-habits/page.md"
        )
        assert metadata["origin_kind"] == "obsidian_note"


def test_capture_obsidian_vault_skips_page_scanner_notes(
    tmp_path: Path,
) -> None:
    """T63: a page-scanner note's marked passages become highlights through
    its book's highlights document (capture_book_highlights()), not by
    handing the whole page note to the segmentation model here -- so a note
    carrying the publication marker is skipped by this function entirely.
    """
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "scan.md").write_text(
        "# Book\n\npage_scanner_id: 42\n\n> Reviewed OCR.\n",
        encoding="utf-8",
    )
    config = IngestionConfig(database_root=tmp_path / "Database")

    with UnifiedIngestionPipeline(config) as pipeline:
        outcomes = capture_obsidian_vault(pipeline, vault=vault)
        assert outcomes == []


def test_capture_book_highlights_captures_one_page_parent_with_sibling_highlights(
    tmp_path: Path,
) -> None:
    vault = tmp_path / "vault"
    doc = _write_highlights_doc(
        vault,
        "atomic-habits",
        passages=[(42, "First passage."), (42, "Second passage.")],
    )
    config = IngestionConfig(database_root=tmp_path / "Database")

    with UnifiedIngestionPipeline(config) as pipeline:
        outcomes = capture_book_highlights(pipeline, vault=vault)

        assert len(outcomes) == 1
        source = pipeline.store.get_source(outcomes[0].source_record_id)
        metadata = json.loads(source["metadata_json"])
        assert metadata["origin_kind"] == "page_scanner"
        assert metadata["page_scanner_id"] == 42
        assert metadata["passage_count"] == 2
        assert source["boundary_origin"] == "user_selection"
        assert source["version"] == 1
        assert source["supersedes_record_id"] is None

        pipeline.process_pending()
        highlights = pipeline.store.get_highlights(outcomes[0].source_record_id)
        assert [row["text"] for row in highlights] == [
            "First passage.",
            "Second passage.",
        ]
        assert all(
            json.loads(row["segmentation_json"])["boundary_origin"]
            == "user_selection"
            for row in highlights
        )
        envelopes = pipeline.store.get_envelopes_for_source(
            outcomes[0].source_record_id, pipeline.config.extraction_version
        )
        assert len(envelopes) == 2
        vault_text = doc.read_text(encoding="utf-8")
        assert [
            vault_text[
                envelope.highlight_parent_start_char : envelope.highlight_parent_end_char
            ]
            for envelope in envelopes
        ] == ["First passage.", "Second passage."]
        assert [envelope.highlight_parent_source_ref for envelope in envelopes] == [
            "Page Scanners/atomic-habits/atomic-habits-highlights.md"
            "#page-scanner-passage-100",
            "Page Scanners/atomic-habits/atomic-habits-highlights.md"
            "#page-scanner-passage-101",
        ]


def test_equal_wording_on_two_pages_stays_two_sources_with_correct_provenance(
    tmp_path: Path,
) -> None:
    vault = tmp_path / "vault"
    _write_highlights_doc(
        vault,
        "atomic-habits",
        passages=[(42, "Repeated wording."), (43, "Repeated wording.")],
    )
    config = IngestionConfig(database_root=tmp_path / "Database")

    with UnifiedIngestionPipeline(config) as pipeline:
        outcomes = capture_book_highlights(pipeline, vault=vault)
        assert len(outcomes) == 2
        assert outcomes[0].source_record_id != outcomes[1].source_record_id
        sources = [pipeline.store.get_source(item.source_record_id) for item in outcomes]
        metadata = [json.loads(source["metadata_json"]) for source in sources]
        assert [item["page_scanner_id"] for item in metadata] == [42, 43]
        assert all(source["version"] == 1 for source in sources)

        pipeline.process_pending()
        assert [
            pipeline.store.get_highlights(item.source_record_id)[0]["text"]
            for item in outcomes
        ] == ["Repeated wording.", "Repeated wording."]


def test_capture_book_highlights_is_idempotent_across_runs(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    _write_highlights_doc(vault, "atomic-habits", passages=[(42, "First passage.")])
    config = IngestionConfig(database_root=tmp_path / "Database")

    with UnifiedIngestionPipeline(config) as pipeline:
        first = capture_book_highlights(pipeline, vault=vault)
        second = capture_book_highlights(pipeline, vault=vault)

        assert all(not outcome.exact_duplicate for outcome in first)
        assert all(outcome.exact_duplicate for outcome in second)
        assert [o.source_record_id for o in first] == [o.source_record_id for o in second]


def test_capture_book_highlights_returns_empty_without_page_scanners_folder(
    tmp_path: Path,
) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    config = IngestionConfig(database_root=tmp_path / "Database")

    with UnifiedIngestionPipeline(config) as pipeline:
        assert capture_book_highlights(pipeline, vault=vault) == []


def test_capture_obsidian_vault_skips_book_highlights_doc(tmp_path: Path) -> None:
    """The book highlights document itself is not a note to be segmented --
    capture_book_highlights() reads it and captures its passages instead.
    """
    vault = tmp_path / "vault"
    doc = vault / "Page Scanners" / "atomic-habits" / "atomic-habits-highlights.md"
    doc.parent.mkdir(parents=True)
    doc.write_text(
        "<!-- page_scanner_highlights_doc -->\n"
        "# Atomic Habits — highlights\n\n"
        "<!-- page_scanner_id: 42 -->\n"
        "## p42\n\n"
        "> Reviewed OCR.\n\n",
        encoding="utf-8",
    )
    config = IngestionConfig(database_root=tmp_path / "Database")

    with UnifiedIngestionPipeline(config) as pipeline:
        outcomes = capture_obsidian_vault(pipeline, vault=vault)
        assert outcomes == []
