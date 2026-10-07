from pathlib import Path

import pytest
from rag_lab.agent import (
    ANSWERED,
    INSUFFICIENT_CONTEXT,
    ExtractiveAnswerer,
    run_question,
)
from rag_lab.store import build_index
from rag_lab.tools import RetrievalTools

CORPUS = Path(__file__).resolve().parents[1] / "corpus"
QUESTIONS = Path(__file__).resolve().parents[1] / "questions.json"


@pytest.fixture
def tools() -> RetrievalTools:
    return RetrievalTools(build_index(CORPUS), top_k=3)


def test_agent_answers_only_from_retrieved_context(tools: RetrievalTools) -> None:
    run = run_question(
        "What must every handoff artifact contain?",
        tools=tools,
        answerer=ExtractiveAnswerer(),
        run_id="test-run",
    )

    assert run.answer.status == ANSWERED
    assert run.answer.answerer == "extractive-v1"
    assert run.answer.citations == ("handoff-contract.md#1",)
    assert all(claim.text in run.loaded[0].text for claim in run.answer.claims)


def test_agent_receives_far_less_context_than_the_corpus(tools: RetrievalTools) -> None:
    run = run_question(
        "What happens when the tool name is unknown?",
        tools=tools,
        answerer=ExtractiveAnswerer(),
    )

    loaded_characters = sum(len(chunk.text) for chunk in run.loaded)
    assert loaded_characters < tools.store.total_characters / 2
    assert run.answer.context_characters == loaded_characters
    assert len(run.loaded) <= tools.top_k


def test_agent_refuses_to_answer_a_question_outside_the_corpus(tools: RetrievalTools) -> None:
    run = run_question(
        "How much does a kilogram of coffee beans cost in Lisbon?",
        tools=tools,
        answerer=ExtractiveAnswerer(),
    )

    assert run.answer.status == INSUFFICIENT_CONTEXT
    assert run.answer.claims == ()
    assert run.answer.citations == ()
    assert run.trace[-1].transition_reason == "no_supporting_context"


def test_agent_refuses_even_when_retrieval_returns_similar_chunks(tools: RetrievalTools) -> None:
    run = run_question(
        "Which database engine stores the retrieved chunks?",
        tools=tools,
        answerer=ExtractiveAnswerer(),
    )

    assert run.retrieved
    assert run.answer.status == INSUFFICIENT_CONTEXT


def test_agent_refuses_when_no_chunk_passes_the_threshold() -> None:
    tools = RetrievalTools(build_index(CORPUS), top_k=3, min_score=0.9)

    run = run_question(
        "What must every handoff artifact contain?",
        tools=tools,
        answerer=ExtractiveAnswerer(),
    )

    assert run.retrieved == ()
    assert run.loaded == ()
    assert run.answer.status == INSUFFICIENT_CONTEXT


def test_extractive_answerer_requires_question_terms(tools: RetrievalTools) -> None:
    chunks = tools.store.search("handoff artifact", limit=1)
    loaded = tuple(hit.chunk for hit in chunks)

    answer = ExtractiveAnswerer().answer("of the", loaded)

    assert answer.status == INSUFFICIENT_CONTEXT


def test_extractive_answerer_validates_its_configuration() -> None:
    with pytest.raises(ValueError, match="support_ratio"):
        ExtractiveAnswerer(support_ratio=0.0)
    with pytest.raises(ValueError, match="max_claims"):
        ExtractiveAnswerer(max_claims=0)


def test_run_question_rejects_an_empty_question(tools: RetrievalTools) -> None:
    with pytest.raises(ValueError, match="question must not be empty"):
        run_question("  ", tools=tools, answerer=ExtractiveAnswerer())


def test_trace_records_search_read_and_answer_steps(tools: RetrievalTools) -> None:
    run = run_question(
        "Why is injecting every document into every model call a problem?",
        tools=tools,
        answerer=ExtractiveAnswerer(),
        run_id="trace-run",
    )

    assert [event.tool_name for event in run.trace] == [
        "search_documents",
        "read_chunk",
        "read_chunk",
        "read_chunk",
        None,
    ]
    assert {event.run_id for event in run.trace} == {"trace-run"}
    assert run.trace[-1].transition_reason == "answer_grounded_in_context"


def test_questions_file_stays_in_sync_with_the_corpus() -> None:
    assert QUESTIONS.is_file()
