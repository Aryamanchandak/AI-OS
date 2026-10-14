from __future__ import annotations

from typing import Any

import pytest

from ingestion.sources import book_metadata


@pytest.fixture(autouse=True)
def offline_book_lookup(monkeypatch: pytest.MonkeyPatch) -> None:
    """No unit test performs network I/O.

    `load_or_resolve()`'s folder-name fallback turns any book-folder name into a
    real Open Library / Google Books query, so a `tmp_path` folder named `drop`
    used to issue an HTTP request mid-suite — making results depend on whether
    the machine was online. Stubbing the one function both lookups go through
    makes offline the default; a test that wants a resolved book overrides this
    with its own `monkeypatch`, which is how `tests/test_book_metadata.py`
    already works.
    """

    def offline(_url: str) -> dict[str, Any] | None:
        return None

    monkeypatch.setattr(book_metadata, "_get_json", offline)
