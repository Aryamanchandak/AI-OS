from __future__ import annotations

from ingestion.text_cleanup.protected import find_protected_spans, intersects


def test_frontmatter_is_protected() -> None:
    text = "---\ntitle: x\n---\nbody\n"
    spans = find_protected_spans(text)
    assert intersects(spans, 4, 12)
    assert not intersects(spans, 18, 22)


def test_url_and_email_and_path_are_protected() -> None:
    text = "go to https://example.com/a and mail@example.com and /a/b/c ok"
    spans = find_protected_spans(text)
    url_start = text.index("https://")
    assert intersects(spans, url_start, url_start + 5)
    email_start = text.index("mail@")
    assert intersects(spans, email_start, email_start + 4)
    path_start = text.index("/a/b/c")
    assert intersects(spans, path_start, path_start + 2)
    ok_start = text.index(" ok")
    assert not intersects(spans, ok_start + 1, ok_start + 3)


def test_single_separator_path_is_protected_but_w_slash_shorthand_is_not() -> None:
    text = "open docs/file.md and talk w/ me"
    spans = find_protected_spans(text)
    path_start = text.index("docs/file.md")
    shorthand_start = text.index("w/")
    assert intersects(spans, path_start, path_start + len("docs/file.md"))
    assert not intersects(spans, shorthand_start, shorthand_start + 2)


def test_link_label_is_not_protected_only_target_is() -> None:
    text = "see [click here](https://example.com/target) now"
    spans = find_protected_spans(text)
    label_start = text.index("click")
    assert not intersects(spans, label_start, label_start + 5)
    target_start = text.index("https://example.com/target")
    assert intersects(spans, target_start, target_start + 5)
