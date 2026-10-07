from pathlib import Path

import pytest
from rag_lab.store import build_index
from rag_lab.tools import (
    READ_CHUNK_TOOL,
    SEARCH_TOOL,
    RetrievalTools,
    ToolError,
    UnknownToolError,
    validate_arguments,
)

CORPUS = Path(__file__).resolve().parents[1] / "corpus"


@pytest.fixture
def tools() -> RetrievalTools:
    return RetrievalTools(build_index(CORPUS), top_k=2)


def test_every_tool_declares_a_narrow_purpose_and_schema(tools: RetrievalTools) -> None:
    names = [spec.name for spec in tools.specs]

    assert names == [SEARCH_TOOL.name, READ_CHUNK_TOOL.name]
    for spec in tools.specs:
        assert spec.description
        assert set(spec.required_arguments) <= set(spec.arguments)


def test_unknown_tool_is_rejected_before_execution(tools: RetrievalTools) -> None:
    with pytest.raises(UnknownToolError, match="Unknown tool: delete_repository"):
        tools.call("delete_repository", {})


@pytest.mark.parametrize(
    ("arguments", "message"),
    [
        ({"query": "scopes", "path": "secrets"}, "unknown argument 'path'"),
        ({}, "missing required argument 'query'"),
        ({"query": "scopes", "limit": 99}, "must be between 1 and 8"),
        ({"query": "scopes", "limit": "two"}, "must be an integer"),
        ({"query": "scopes", "limit": True}, "must be an integer"),
        ({"query": ""}, "must not be empty"),
        ({"query": 7}, "must be a string"),
    ],
)
def test_invalid_arguments_are_rejected_before_execution(
    tools: RetrievalTools, arguments: dict[str, object], message: str
) -> None:
    with pytest.raises(ToolError, match=message):
        tools.call(SEARCH_TOOL.name, arguments)


def test_search_tool_returns_references_and_snippets_only(tools: RetrievalTools) -> None:
    result = tools.call(SEARCH_TOOL.name, {"query": "least privilege scopes", "limit": 2})

    assert result.returned_characters > 0
    assert len(result.hits) == 2
    assert result.chunks == ()
    assert set(result.payload) == {"tool", "query", "hits"}
    hits = result.payload["hits"]
    assert isinstance(hits, list)
    for hit in hits:
        assert isinstance(hit, dict)
        assert set(hit) == {"chunk_id", "source", "section", "score", "snippet"}
        assert "text" not in hit


def test_read_tool_loads_one_chunk_and_returns_the_chunk_object(tools: RetrievalTools) -> None:
    chunk_id = tools.call(SEARCH_TOOL.name, {"query": "handoff artifact"}).hits[0].chunk.chunk_id

    result = tools.call(READ_CHUNK_TOOL.name, {"chunk_id": chunk_id})

    assert len(result.chunks) == 1
    assert result.chunks[0].chunk_id == chunk_id
    assert result.returned_characters == len(result.chunks[0].text)


def test_read_tool_rejects_a_chunk_that_was_not_retrieved(tools: RetrievalTools) -> None:
    with pytest.raises(LookupError, match="Unknown chunk identifier"):
        tools.call(READ_CHUNK_TOOL.name, {"chunk_id": "not-indexed.md#1"})


def test_search_then_read_stays_far_below_the_whole_corpus(tools: RetrievalTools) -> None:
    store = tools.store
    search = tools.call(SEARCH_TOOL.name, {"query": "redaction and secrets", "limit": 2})
    loaded_characters = sum(
        tools.call(READ_CHUNK_TOOL.name, {"chunk_id": hit.chunk.chunk_id}).returned_characters
        for hit in search.hits
    )

    assert loaded_characters < store.total_characters / 2
    assert search.returned_characters < store.total_characters


def test_validate_arguments_returns_a_plain_dictionary() -> None:
    validated = validate_arguments(SEARCH_TOOL, {"query": "scopes", "limit": 2})

    assert validated == {"query": "scopes", "limit": 2}
    assert isinstance(validated, dict)
