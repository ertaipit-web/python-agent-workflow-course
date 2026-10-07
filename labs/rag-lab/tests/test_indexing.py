from pathlib import Path

import pytest
from rag_lab.chunking import chunk_markdown, ingest_directory, split_sections
from rag_lab.embedding import HashingEmbedder, cosine_similarity
from rag_lab.store import VectorStore, build_index, make_snippet

CORPUS = Path(__file__).resolve().parents[1] / "corpus"


def test_split_sections_keeps_headings_and_drops_empty_sections() -> None:
    markdown = "# Title\n\nBody text.\n\n## Empty\n\n## Next\n\nMore text.\n"

    sections = split_sections(markdown)

    assert [(section.heading, section.body) for section in sections] == [
        ("Title", "Body text."),
        ("Next", "More text."),
    ]


def test_chunk_markdown_creates_overlapping_windows_with_provenance() -> None:
    markdown = "# Guide\n\n" + " ".join(f"word{index}" for index in range(20)) + "\n"

    chunks = chunk_markdown(markdown, source="guide.md", max_words=12, overlap_words=4)

    assert [chunk.chunk_id for chunk in chunks] == ["guide.md#1", "guide.md#2"]
    assert chunks[0].source == "guide.md"
    assert chunks[0].section == "Guide"
    assert chunks[0].position == 1
    assert chunks[1].position == 2
    assert set(chunks[0].text.split()) & set(chunks[1].text.split())


def test_chunk_markdown_rejects_invalid_window_sizes() -> None:
    with pytest.raises(ValueError, match="max_words must be positive"):
        chunk_markdown("text", source="a.md", max_words=0)

    with pytest.raises(ValueError, match="overlap_words must be smaller"):
        chunk_markdown("text", source="a.md", max_words=10, overlap_words=10)


def test_ingest_directory_reads_markdown_and_skips_caches(tmp_path: Path) -> None:
    (tmp_path / ".venv").mkdir()
    (tmp_path / ".venv" / "ignored.md").write_text("# Ignored\n\ntext\n", encoding="utf-8")
    (tmp_path / "notes.md").write_text(
        "# Notes\n\n" + " ".join(f"word{index}" for index in range(40)), encoding="utf-8"
    )

    chunks = ingest_directory(tmp_path)

    assert {chunk.source for chunk in chunks} == {"notes.md"}


def test_ingest_directory_reports_missing_or_empty_corpus(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Corpus directory does not exist"):
        ingest_directory(tmp_path / "missing")

    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(ValueError, match="No Markdown documents found"):
        ingest_directory(empty)


def test_embedder_is_deterministic_and_normalized() -> None:
    embedder = HashingEmbedder(dimensions=64)

    first = embedder.embed("least privilege scopes")
    second = embedder.embed("least privilege scopes")

    assert first == second
    assert len(first) == 64
    assert pytest.approx(1.0, abs=1e-9) == sum(value * value for value in first)
    assert embedder.embed("") == tuple([0.0] * 64)


def test_cosine_similarity_ranks_overlapping_text_higher() -> None:
    embedder = HashingEmbedder()
    query = embedder.embed("least privilege for a read only role")
    related = embedder.embed("give the role the least scopes it needs for reading")
    unrelated = embedder.embed("coffee beans are roasted in the harbour district")

    assert cosine_similarity(query, related) > cosine_similarity(query, unrelated)


def test_cosine_similarity_rejects_mismatched_dimensions() -> None:
    with pytest.raises(ValueError, match="same number of dimensions"):
        cosine_similarity((1.0, 0.0), (1.0, 0.0, 0.0))


def test_make_snippet_truncates_long_text() -> None:
    chunk = chunk_markdown("# T\n\n" + " ".join(f"w{i}" for i in range(30)), source="t.md")[0]

    snippet = make_snippet(chunk, word_limit=5)

    assert snippet.endswith("...")
    assert len(snippet.split()) == 5


def test_store_search_returns_ranked_hits_with_provenance() -> None:
    store = build_index(CORPUS)

    hits = store.search("least privilege scopes for a tool", limit=2)

    assert len(hits) == 2
    assert hits[0].score >= hits[1].score
    assert hits[0].chunk.source == "permissions-policy.md"
    assert hits[0].snippet


def test_store_search_hides_chunks_below_the_threshold() -> None:
    store = build_index(CORPUS)

    assert store.search("zebra giraffe lighthouse", min_score=0.2) == ()


def test_store_validates_limits_and_lookups() -> None:
    store = build_index(CORPUS)

    with pytest.raises(ValueError, match="limit must be positive"):
        store.search("anything", limit=0)
    with pytest.raises(ValueError, match="min_score must be between"):
        store.search("anything", min_score=1.5)
    with pytest.raises(LookupError, match="Unknown chunk identifier"):
        store.chunk("missing.md#9")


def test_store_rejects_empty_and_ambiguous_indexes() -> None:
    with pytest.raises(ValueError, match="at least one chunk"):
        VectorStore([])

    chunk = chunk_markdown("# T\n\ntext", source="t.md")[0]
    with pytest.raises(ValueError, match="Duplicate chunk identifiers"):
        VectorStore([chunk, chunk])
