from gateway.ingestion.config import EmbeddingChunkConfig
from gateway.ingestion.vector.chunking import chunk_text, sentence_chunks


def test_chunk_text_is_deterministic_and_preserves_overlap() -> None:
    text = "First sentence. Second sentence. Third sentence."

    first = chunk_text(text, chunk_size=32, overlap=8)
    second = chunk_text(text, chunk_size=32, overlap=8)

    assert first == second
    assert len(first) == 2
    assert first[1].startswith(first[0][-8:])


def test_chunk_text_hard_splits_an_unbroken_piece() -> None:
    chunks = chunk_text("x" * 25, chunk_size=10, overlap=0)

    assert chunks == ["x" * 10, "x" * 10, "x" * 5]


def test_chunk_text_returns_the_input_when_no_structural_piece_exists() -> None:
    assert chunk_text("\n\n", chunk_size=10, overlap=0) == ["\n\n"]


def test_sentence_chunks_use_three_sentences_with_one_sentence_overlap() -> None:
    text = "One alpha. Two beta. Three gamma. Four delta. Five epsilon."

    chunks = sentence_chunks(text, EmbeddingChunkConfig())

    assert [chunk.text for chunk in chunks] == [
        "One alpha. Two beta. Three gamma.",
        "Three gamma. Four delta. Five epsilon.",
    ]
    assert [(chunk.sentence_start, chunk.sentence_end) for chunk in chunks] == [
        (0, 3),
        (2, 5),
    ]


def test_pathological_sentence_hard_split_has_no_loss_and_stays_bounded() -> None:
    text = " ".join(f"word{index}" for index in range(360))
    config = EmbeddingChunkConfig(max_words=150, max_characters=8_000)

    chunks = sentence_chunks(text, config)

    assert len(chunks) == 3
    assert all(chunk.hard_split for chunk in chunks)
    assert all(len(chunk.text.split()) <= 150 for chunk in chunks)
    assert "".join(chunk.text for chunk in chunks) == text
    assert {
        word
        for chunk in chunks
        for word in chunk.text.split()
    } == set(text.split())


def test_unbroken_url_dump_is_split_at_the_character_ceiling_without_loss() -> None:
    text = "x" * 16_050
    config = EmbeddingChunkConfig(max_characters=8_000)

    chunks = sentence_chunks(text, config)

    assert [len(chunk.text) for chunk in chunks] == [8_000, 8_000, 50]
    assert "".join(chunk.text for chunk in chunks) == text
