from __future__ import annotations

from pathlib import Path

import pytest

from ingestion.text_cleanup.store import (
    AuditEntry,
    DuplicateMappingError,
    MappingNotFoundError,
    MappingRepository,
)


def repo(tmp_path: Path) -> MappingRepository:
    return MappingRepository(tmp_path / "text_cleanup.db")


def audit(**overrides: object) -> AuditEntry:
    defaults: dict[str, object] = dict(
        source_kind="image",
        run_id="run1",
        item_id="item1",
        occurrence_id="abbr-p0-0-2-1",
        phase="abbreviation",
        action="apply_remember",
        before="w/",
        after="with",
        interaction_revision=1,
        working_draft_revision=1,
    )
    defaults.update(overrides)
    return AuditEntry(**defaults)  # type: ignore[arg-type]


def test_first_use_mapping_creation_works_with_empty_dictionary(tmp_path: Path) -> None:
    repository = repo(tmp_path)
    assert repository.active_mappings() == []
    record = repository.create("w/", "with")
    assert record.shorthand == "w/"
    assert record.expansion == "with"
    assert record.case_sensitive is True
    mappings = repository.active_mappings()
    assert len(mappings) == 1
    assert mappings[0].shorthand == "w/"


def test_search_edit_delete(tmp_path: Path) -> None:
    repository = repo(tmp_path)
    created = repository.create("ASAP", "as soon as possible", case_sensitive=False)
    found = repository.search("ASA")
    assert len(found) == 1
    assert found[0].id == created.id

    edited = repository.edit(created.id, expansion="ASAP!")
    assert edited.expansion == "ASAP!"

    repository.delete(created.id)
    assert repository.get(created.id) is None
    assert repository.active_mappings() == []


def test_edit_missing_mapping_raises(tmp_path: Path) -> None:
    repository = repo(tmp_path)
    with pytest.raises(MappingNotFoundError):
        repository.edit("nope", expansion="x")


def test_delete_missing_mapping_raises(tmp_path: Path) -> None:
    repository = repo(tmp_path)
    with pytest.raises(MappingNotFoundError):
        repository.delete("nope")


def test_one_active_expansion_uniqueness_per_shorthand_and_case(tmp_path: Path) -> None:
    repository = repo(tmp_path)
    repository.create("w/", "with", case_sensitive=True)
    with pytest.raises(DuplicateMappingError):
        repository.create("w/", "within", case_sensitive=True)
    # A different case policy for the same shorthand text is a distinct row.
    other_case = repository.create("w/", "with-ci", case_sensitive=False)
    assert other_case.case_sensitive is False


def test_mappings_survive_reopening_the_repository(tmp_path: Path) -> None:
    db_path = tmp_path / "text_cleanup.db"
    MappingRepository(db_path).create("w/", "with")
    reopened = MappingRepository(db_path)
    assert [m.shorthand for m in reopened.active_mappings()] == ["w/"]


def test_apply_remember_atomically_creates_mapping_and_audit_row(tmp_path: Path) -> None:
    repository = repo(tmp_path)
    record = repository.record_apply_remember(
        shorthand="w/",
        expansion="with",
        case_sensitive=True,
        audit=audit(),
    )
    assert record.shorthand == "w/"
    assert record.expansion == "with"
    assert len(repository.active_mappings()) == 1


def test_apply_remember_replaces_active_value_not_a_second_row(tmp_path: Path) -> None:
    repository = repo(tmp_path)
    first = repository.record_apply_remember(
        shorthand="w/", expansion="with", case_sensitive=True, audit=audit()
    )
    second = repository.record_apply_remember(
        shorthand="w/",
        expansion="within",
        case_sensitive=True,
        audit=audit(occurrence_id="abbr-p0-10-12-2", after="within"),
    )
    assert first.id == second.id
    mappings = repository.active_mappings()
    assert len(mappings) == 1
    assert mappings[0].expansion == "within"


def test_standalone_append_audit_does_not_touch_mappings(tmp_path: Path) -> None:
    repository = repo(tmp_path)
    repository.append_audit(audit(action="skip", after="w/"))
    assert repository.active_mappings() == []
