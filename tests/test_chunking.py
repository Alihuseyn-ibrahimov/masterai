import re

from pipeline.chunking import CHUNK_OVERLAP_CHARS, CHUNK_SIZE_CHARS, split


def _numbered_sentences(count: int) -> str:
    return " ".join(
        f"Cumle-{i:04d} bu numune metnin unikal bir hissesidir." for i in range(count)
    )


def _sentence_ids(chunk: str) -> set[str]:
    return set(re.findall(r"Cumle-\d{4}", chunk))


def test_empty_text_returns_empty_list():
    assert split("") == []
    assert split("   \n  ") == []


def test_short_text_returns_single_chunk_unchanged():
    text = "Bu qisa bir numune metndir."
    assert split(text) == [text]


def test_long_text_is_split_into_multiple_chunks_within_size_limit():
    text = _numbered_sentences(400)
    chunks = split(text)

    assert len(chunks) > 1
    for chunk in chunks:
        # RecursiveCharacterTextSplitter təbii sərhədlərdə (boşluq/cümlə) kəsir,
        # ona görə dəqiq ölçü deyil, kiçik bir sapmaya icazə veririk.
        assert len(chunk) <= CHUNK_SIZE_CHARS + 200


def test_consecutive_chunks_share_overlapping_sentences():
    text = _numbered_sentences(400)
    chunks = split(text)

    for i in range(len(chunks) - 1):
        shared = _sentence_ids(chunks[i]) & _sentence_ids(chunks[i + 1])
        assert shared, f"chunk {i} və {i + 1} arasında overlap tapılmadı"


def test_overlap_is_smaller_than_chunk_size():
    assert CHUNK_OVERLAP_CHARS < CHUNK_SIZE_CHARS
