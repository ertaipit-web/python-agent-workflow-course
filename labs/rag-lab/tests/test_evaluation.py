import json
from collections.abc import Sequence
from pathlib import Path

import pytest
from rag_lab.agent import (
    ANSWERED,
    INSUFFICIENT_CONTEXT,
    Answer,
    Claim,
    ExtractiveAnswerer,
)
from rag_lab.chunking import Chunk
from rag_lab.evaluation import CaseFormatError, EvaluationCase, evaluate, load_cases
from rag_lab.store import build_index
from rag_lab.tools import RetrievalTools

LAB = Path(__file__).resolve().parents[1]
CORPUS = LAB / "corpus"
QUESTIONS = LAB / "questions.json"


class FabricatedAnswerer:
    name = "fabricated-v1"

    def answer(self, question: str, contexts: Sequence[Chunk]) -> Answer:
        citation = contexts[0].chunk_id if contexts else "unknown.md#1"
        claim = Claim(text="An answer that no indexed document actually contains.", citation=citation)
        return Answer(
            question=question,
            status=ANSWERED,
            text=claim.text,
            claims=(claim,),
            citations=(citation,),
            context_characters=sum(len(chunk.text) for chunk in contexts),
            answerer=self.name,
        )


@pytest.fixture
def tools() -> RetrievalTools:
    return RetrievalTools(build_index(CORPUS), top_k=3)


def test_load_cases_reads_the_shipped_golden_set() -> None:
    cases = load_cases(QUESTIONS)

    assert [case.case_id for case in cases][:2] == ["handoff-fields", "whole-corpus"]
    assert any(not case.supported for case in cases)
    assert all(case.expected_sources for case in cases if case.supported)


def test_golden_set_reports_retrieval_grounding_and_unsupported_answers(
    tools: RetrievalTools,
) -> None:
    report = evaluate(load_cases(QUESTIONS), tools=tools, answerer=ExtractiveAnswerer())

    assert len(report.cases) == 7
    assert report.retrieval_relevance == 1.0
    assert report.grounded_answer_rate == 1.0
    assert report.unsupported_answer_rate == 0.0
    assert report.runs
    assert "retrieval relevance: 1.00" in report.summary()


def test_every_supported_case_is_answered_and_grounded(tools: RetrievalTools) -> None:
    report = evaluate(load_cases(QUESTIONS), tools=tools, answerer=ExtractiveAnswerer())

    for case in report.supported_cases:
        assert case.status == ANSWERED, case.case_id
        assert case.grounded, case.case_id
        assert case.missing_sources == ()
        assert case.detail == "every claim is present in its cited chunk"


def test_unsupported_cases_never_produce_an_answer(tools: RetrievalTools) -> None:
    report = evaluate(load_cases(QUESTIONS), tools=tools, answerer=ExtractiveAnswerer())

    unsupported = [case for case in report.cases if not case.supported]
    assert len(unsupported) == 2
    for case in unsupported:
        assert case.status == INSUFFICIENT_CONTEXT
        assert case.unsupported is False
        assert case.grounded is False


def test_evaluation_reports_a_missing_source_instead_of_hiding_it(
    tools: RetrievalTools,
) -> None:
    cases = [
        EvaluationCase(
            case_id="wrong-source",
            question="What must every handoff artifact contain?",
            supported=True,
            expected_sources=("not-indexed-document.md",),
        )
    ]

    report = evaluate(cases, tools=tools, answerer=ExtractiveAnswerer())

    assert report.retrieval_relevance == 0.0
    assert report.cases[0].missing_sources == ("not-indexed-document.md",)
    assert report.cases[0].detail == "expected source not retrieved: not-indexed-document.md"


def test_grounding_check_rejects_an_answer_that_is_not_in_its_citation(
    tools: RetrievalTools,
) -> None:
    case = load_cases(QUESTIONS)[0]

    report = evaluate([case], tools=tools, answerer=FabricatedAnswerer())

    assert report.cases[0].status == ANSWERED
    assert report.cases[0].grounded is False
    assert report.cases[0].detail == "claim is not supported by its citation: handoff-contract.md#1"
    assert report.grounded_answer_rate == 0.0


def test_unsupported_case_with_an_answerer_that_always_answers_is_flagged(
    tools: RetrievalTools,
) -> None:
    case = EvaluationCase(
        case_id="hallucination",
        question="Which database engine stores the retrieved chunks?",
        supported=False,
        expected_sources=(),
    )

    report = evaluate([case], tools=tools, answerer=FabricatedAnswerer())

    assert report.cases[0].unsupported is True
    assert report.unsupported_answer_rate == 1.0
    assert report.cases[0].detail == "answer produced without supporting evidence"


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({}, "expected a non-empty JSON list"),
        ([["case"]], "expected an object"),
        ([{"question": "q", "supported": True, "expected_sources": []}], "missing field 'case_id'"),
        (
            [{"case_id": "a", "question": "", "supported": True, "expected_sources": ["x.md"]}],
            "question must be a non-empty string",
        ),
        (
            [{"case_id": "a", "question": "q", "supported": "yes", "expected_sources": []}],
            "supported must be true or false",
        ),
        (
            [{"case_id": "a", "question": "q", "supported": True, "expected_sources": "x"}],
            "expected_sources must be a list",
        ),
        (
            [{"case_id": "a", "question": "q", "supported": True, "expected_sources": []}],
            "needs at least one expected source",
        ),
        (
            [
                {"case_id": "a", "question": "q1", "supported": False, "expected_sources": []},
                {"case_id": "a", "question": "q2", "supported": False, "expected_sources": []},
            ],
            "duplicate case_id 'a'",
        ),
    ],
)
def test_load_cases_rejects_a_broken_golden_set(tmp_path: Path, payload: object, message: str) -> None:
    path = tmp_path / "cases.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(CaseFormatError, match=message):
        load_cases(path)


def test_report_lines_render_a_readable_table(tools: RetrievalTools) -> None:
    report = evaluate(load_cases(QUESTIONS), tools=tools, answerer=ExtractiveAnswerer())

    rendered = "\n".join(report.lines())

    assert "## RAG evaluation" in rendered
    assert "| handoff-fields |" in rendered
    assert "| retrieved |" in rendered
    assert "handoff-contract.md, permissions-policy.md" in rendered
    assert "not proof that an answer is correct" in rendered
