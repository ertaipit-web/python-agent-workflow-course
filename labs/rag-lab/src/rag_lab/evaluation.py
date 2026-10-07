from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from rag_lab.agent import ANSWERED, Answer, Answerer, AnswerRun, run_question
from rag_lab.chunking import Chunk
from rag_lab.text import terms
from rag_lab.tools import RetrievalTools

_REQUIRED_FIELDS = ("case_id", "question", "supported", "expected_sources")


class CaseFormatError(ValueError):
    pass


@dataclass(frozen=True)
class EvaluationCase:
    case_id: str
    question: str
    supported: bool
    expected_sources: tuple[str, ...]


@dataclass(frozen=True)
class CaseReport:
    case_id: str
    question: str
    supported: bool
    status: str
    retrieved_sources: tuple[str, ...]
    missing_sources: tuple[str, ...]
    grounded: bool
    unsupported: bool
    detail: str


@dataclass(frozen=True)
class EvaluationReport:
    cases: tuple[CaseReport, ...]
    runs: tuple[AnswerRun, ...] = ()

    @property
    def supported_cases(self) -> tuple[CaseReport, ...]:
        return tuple(case for case in self.cases if case.supported)

    @property
    def answered_cases(self) -> tuple[CaseReport, ...]:
        return tuple(case for case in self.cases if case.status == ANSWERED)

    @property
    def retrieval_relevance(self) -> float:
        supported = self.supported_cases
        if not supported:
            return 0.0
        hits = sum(1 for case in supported if not case.missing_sources)
        return hits / len(supported)

    @property
    def grounded_answer_rate(self) -> float:
        answered = self.answered_cases
        if not answered:
            return 0.0
        grounded = sum(1 for case in answered if case.grounded)
        return grounded / len(answered)

    @property
    def unsupported_answer_rate(self) -> float:
        unsupported = tuple(case for case in self.cases if not case.supported)
        if not unsupported:
            return 0.0
        fabricated = sum(1 for case in unsupported if case.unsupported)
        return fabricated / len(unsupported)

    def summary(self) -> str:
        return (
            f"cases: {len(self.cases)}, "
            f"retrieval relevance: {self.retrieval_relevance:.2f}, "
            f"grounded answers: {self.grounded_answer_rate:.2f}, "
            f"unsupported answers: {self.unsupported_answer_rate:.2f}"
        )

    def lines(self) -> tuple[str, ...]:
        rows = ["## RAG evaluation", ""]
        rows.append(
            "| case | supported | status | retrieved | missing sources | grounded "
            "| unsupported | detail |"
        )
        rows.append("|---|---|---|---|---|---|---|---|")
        for case in self.cases:
            rows.append(
                "| {case_id} | {supported} | {status} | {retrieved} | {missing} | {grounded} | "
                "{unsupported} | {detail} |".format(
                    case_id=case.case_id,
                    supported=case.supported,
                    status=case.status,
                    retrieved=", ".join(case.retrieved_sources) or "-",
                    missing=", ".join(case.missing_sources) or "-",
                    grounded=case.grounded,
                    unsupported=case.unsupported,
                    detail=case.detail,
                )
            )
        rows.extend(
            [
                "",
                f"Retrieval relevance: {self.retrieval_relevance:.2f}.",
                f"Grounded answer rate: {self.grounded_answer_rate:.2f}.",
                f"Unsupported answer rate: {self.unsupported_answer_rate:.2f}.",
                "",
                (
                    "Retrieval relevance and grounding are lexical measurements of this offline "
                    "index. They are not proof that an answer is correct."
                ),
                "",
            ]
        )
        return tuple(rows)


def load_cases(path: Path) -> tuple[EvaluationCase, ...]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list) or not payload:
        raise CaseFormatError(f"{path}: expected a non-empty JSON list of cases")

    cases: list[EvaluationCase] = []
    seen: set[str] = set()
    for index, entry in enumerate(payload):
        cases.append(_parse_case(path, index, entry, seen))
    return tuple(cases)


def _parse_case(path: Path, index: int, entry: object, seen: set[str]) -> EvaluationCase:
    where = f"{path}: case #{index + 1}"
    if not isinstance(entry, dict):
        raise CaseFormatError(f"{where}: expected an object")

    missing = [field for field in _REQUIRED_FIELDS if field not in entry]
    if missing:
        raise CaseFormatError(f"{where}: missing field '{missing[0]}'")

    case_id = entry["case_id"]
    question = entry["question"]
    supported = entry["supported"]
    expected_sources = entry["expected_sources"]

    if not isinstance(case_id, str) or not case_id.strip():
        raise CaseFormatError(f"{where}: case_id must be a non-empty string")
    if case_id in seen:
        raise CaseFormatError(f"{where}: duplicate case_id '{case_id}'")
    if not isinstance(question, str) or not question.strip():
        raise CaseFormatError(f"{where}: question must be a non-empty string")
    if not isinstance(supported, bool):
        raise CaseFormatError(f"{where}: supported must be true or false")
    if not isinstance(expected_sources, list) or not all(
        isinstance(source, str) and source.strip() for source in expected_sources
    ):
        raise CaseFormatError(f"{where}: expected_sources must be a list of document names")
    if supported and not expected_sources:
        raise CaseFormatError(
            f"{where}: a supported case needs at least one expected source document"
        )

    seen.add(case_id)
    return EvaluationCase(
        case_id=case_id,
        question=question,
        supported=supported,
        expected_sources=tuple(expected_sources),
    )


def evaluate(
    cases: Sequence[EvaluationCase],
    *,
    tools: RetrievalTools,
    answerer: Answerer,
) -> EvaluationReport:
    case_reports: list[CaseReport] = []
    runs: list[AnswerRun] = []
    for case in cases:
        run = run_question(case.question, tools=tools, answerer=answerer, run_id=case.case_id)
        runs.append(run)
        case_reports.append(_evaluate_case(case, run=run))
    return EvaluationReport(cases=tuple(case_reports), runs=tuple(runs))


def _evaluate_case(case: EvaluationCase, *, run: AnswerRun) -> CaseReport:
    retrieved_sources = tuple(sorted({hit.chunk.source for hit in run.retrieved}))
    missing = tuple(source for source in case.expected_sources if source not in retrieved_sources)
    grounded, detail = _grounding(run.answer, run.loaded)

    if case.supported:
        if missing:
            detail = f"expected source not retrieved: {', '.join(missing)}"
        elif run.answer.status != ANSWERED:
            detail = "supported question produced no grounded answer"
    elif run.answer.status == ANSWERED:
        detail = "answer produced without supporting evidence"

    return CaseReport(
        case_id=case.case_id,
        question=case.question,
        supported=case.supported,
        status=run.answer.status,
        retrieved_sources=retrieved_sources,
        missing_sources=missing,
        grounded=grounded,
        unsupported=run.answer.status == ANSWERED and not case.supported,
        detail=detail,
    )


def _grounding(answer: Answer, loaded: Sequence[Chunk]) -> tuple[bool, str]:
    if answer.status != ANSWERED:
        return False, "no answer to check"
    if not answer.claims:
        return False, "answered without claims"

    by_id = {chunk.chunk_id: chunk for chunk in loaded}
    for claim in answer.claims:
        chunk = by_id.get(claim.citation)
        if chunk is None:
            return False, f"citation outside retrieved context: {claim.citation}"
        claim_terms = terms(claim.text)
        if not claim_terms:
            return False, f"claim without checkable content: {claim.citation}"
        if not claim_terms <= terms(chunk.text):
            return False, f"claim is not supported by its citation: {claim.citation}"
    return True, "every claim is present in its cited chunk"