from __future__ import annotations

from ingestion.text_cleanup.abbreviations import MappingRow, find_candidates
from ingestion.text_cleanup.models import Passage, current_offsets, recompute_passages


def mapping(shorthand: str, expansion: str, *, case_sensitive: bool = True, id_: str = "m1") -> MappingRow:
    return MappingRow(id=id_, shorthand=shorthand, expansion=expansion, case_sensitive=case_sensitive)


def test_literal_matching_prevents_embedded_word_match() -> None:
    passages = [Passage(index=0, text="The duration was long, dur it went well.")]
    candidates = find_candidates(passages, [mapping("dur", "during")])
    assert len(candidates) == 1
    assert candidates[0].original_text == "dur"
    start = candidates[0].base_start
    assert passages[0].text[start : start + 3] == "dur"
    assert passages[0].text[start - 1] == " "


def test_punctuation_bearing_shorthand_matches() -> None:
    passages = [Passage(index=0, text="Talk w/ me later, but not thew/that.")]
    candidates = find_candidates(passages, [mapping("w/", "with")])
    assert len(candidates) == 1
    assert candidates[0].original_text == "w/"
    assert passages[0].text[candidates[0].base_start : candidates[0].base_end] == "w/"


def test_case_insensitive_mapping_inserts_stored_expansion_exactly() -> None:
    passages = [Passage(index=0, text="ASAP means as soon as possible, or asap.")]
    candidates = find_candidates(passages, [mapping("ASAP", "as soon as possible", case_sensitive=False)])
    assert len(candidates) == 2
    assert all(c.proposed_text == "as soon as possible" for c in candidates)


def test_case_sensitive_mapping_default_only_matches_exact_case() -> None:
    passages = [Passage(index=0, text="ASAP and asap are different here.")]
    candidates = find_candidates(passages, [mapping("ASAP", "as soon as possible")])
    assert len(candidates) == 1
    assert candidates[0].base_start == 0


def test_protected_regions_are_untouched() -> None:
    text = (
        "---\n"
        "title: dur test\n"
        "---\n"
        "Visit https://example.com/dur or email dur@example.com.\n"
        "Run `dur --flag` in a code span.\n"
        "```\n"
        "dur fenced\n"
        "```\n"
        "See [dur](dur/path) and path a/dur/b.\n"
        "But this dur is fair game.\n"
    )
    passages = [Passage(index=0, text=text)]
    candidates = find_candidates(passages, [mapping("dur", "during")])
    starts = {candidate.base_start for candidate in candidates}
    # The link's visible label ("[dur]") is ordinary prose and stays
    # reviewable; only its target ("(dur/path)") is protected. Every other
    # "dur" (frontmatter, URL, email, inline code, fenced code, the path)
    # must be excluded, leaving exactly the label and the free-standing one.
    label_start = text.index("[dur]") + 1
    target_start = text.index("(dur/path)") + 1
    free_start = text.index("But this dur") + len("But this ")
    assert starts == {label_start, free_start}
    assert target_start not in starts


def test_candidates_are_stable_and_in_document_order() -> None:
    passages = [
        Passage(index=0, text="w/ one w/ two"),
        Passage(index=1, text="w/ three"),
    ]
    candidates = find_candidates(passages, [mapping("w/", "with")])
    assert [c.ordinal for c in candidates] == [1, 2, 3]
    assert [c.passage_index for c in candidates] == [0, 0, 1]


def test_apply_once_changes_one_occurrence() -> None:
    passages = [Passage(index=0, text="w/ one w/ two")]
    candidates = find_candidates(passages, [mapping("w/", "with")])
    first_id = candidates[0].occurrence_id
    recomputed = recompute_passages(passages, candidates, {first_id: "apply_once"})
    assert recomputed[0].text == "with one w/ two"


def test_skipped_occurrence_remains_unchanged() -> None:
    passages = [Passage(index=0, text="w/ one w/ two")]
    candidates = find_candidates(passages, [mapping("w/", "with")])
    decisions = {c.occurrence_id: "skip" for c in candidates}
    recomputed = recompute_passages(passages, candidates, decisions)
    assert recomputed[0].text == passages[0].text


def test_replacements_do_not_cascade_or_create_new_candidates() -> None:
    # Expansion text itself contains the shorthand ("hi ho" contains "hi"),
    # which would be a fresh match if recompute re-scanned its own output.
    passages = [Passage(index=0, text="hi there")]
    candidates = find_candidates(passages, [mapping("hi", "hi ho")])
    assert len(candidates) == 1
    recomputed = recompute_passages(
        passages, candidates, {candidates[0].occurrence_id: "apply_once"}
    )
    assert recomputed[0].text == "hi ho there"
    # The candidate list itself is untouched -- recompute never re-invokes
    # find_candidates on its own output, so no second "hi" candidate appears.
    assert len(candidates) == 1


def test_re_decision_recomputes_from_base_text() -> None:
    passages = [Passage(index=0, text="w/ one")]
    candidates = find_candidates(passages, [mapping("w/", "with")])
    occurrence_id = candidates[0].occurrence_id
    first = recompute_passages(passages, candidates, {occurrence_id: "apply_once"})
    assert first[0].text == "with one"
    second = recompute_passages(passages, candidates, {occurrence_id: "skip"})
    assert second[0].text == "w/ one"


def test_zero_matches_create_no_candidates() -> None:
    passages = [Passage(index=0, text="nothing to see here")]
    candidates = find_candidates(passages, [mapping("xyz", "expansion")])
    assert candidates == []


def test_current_offsets_shift_with_earlier_accepted_replacement() -> None:
    passages = [Passage(index=0, text="w/ one w/ two")]
    candidates = find_candidates(passages, [mapping("w/", "with")])
    first_id, second_id = candidates[0].occurrence_id, candidates[1].occurrence_id
    offsets = current_offsets(candidates, {first_id: "apply_once"})
    assert offsets[first_id] == (0, 4)
    # "with" is 2 chars longer than "w/", so the second occurrence shifts by +2.
    assert offsets[second_id] == (9, 11)


def test_one_shorthand_case_policy_has_at_most_one_effective_expansion() -> None:
    passages = [Passage(index=0, text="w/ one")]
    candidates = find_candidates(
        passages,
        [mapping("w/", "with", id_="m1"), mapping("w/", "within", id_="m2")],
    )
    # Both mappings are literal candidates against the same shorthand text;
    # repository-level uniqueness (see store.py) is what actually prevents
    # two active rows -- the engine itself just matches whatever mappings it
    # is given, in list order, first-match-wins on overlapping spans.
    assert len(candidates) == 1


def test_overlapping_mapping_winner_is_independent_of_repository_order() -> None:
    passages = [Passage(index=0, text="w/ one")]
    short = mapping("w", "double-u", id_="short")
    long = mapping("w/", "with", id_="long")
    forward = find_candidates(passages, [short, long])
    reverse = find_candidates(passages, [long, short])
    assert [(item.original_text, item.proposed_text) for item in forward] == [
        ("w/", "with")
    ]
    assert forward == reverse


def test_case_insensitive_match_keeps_exact_offsets_after_a_folding_character() -> None:
    """U+0130 lowercases to two characters; offsets must not slide with it.

    Before the length-preserving fold, the lowered haystack was one character
    longer than the passage from the "İ" onwards, so this occurrence was
    reported at (10, 12) as "> " and applying it produced
    "İstanbul -leads togrowth" -- a silent corruption of a verbatim quote.
    """

    passages = [Passage(index=0, text="İstanbul -> growth")]
    candidates = find_candidates(
        passages, [mapping("->", "leads to", case_sensitive=False)]
    )

    assert len(candidates) == 1
    candidate = candidates[0]
    assert (candidate.base_start, candidate.base_end) == (9, 11)
    assert candidate.original_text == "->"
    assert (
        passages[0].text[candidate.base_start : candidate.base_end]
        == candidate.original_text
    )
    applied = recompute_passages(
        passages, candidates, {candidate.occurrence_id: "apply_once"}
    )
    assert applied[0].text == "İstanbul leads to growth"


def test_case_insensitive_match_is_still_found_after_a_folding_character() -> None:
    passages = [Passage(index=0, text="İstanbul mgmt review")]
    candidates = find_candidates(
        passages, [mapping("MGMT", "management", case_sensitive=False)]
    )

    assert len(candidates) == 1
    assert candidates[0].original_text == "mgmt"
    assert (candidates[0].base_start, candidates[0].base_end) == (9, 13)
