from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from rag_lab.chunking import Chunk
from rag_lab.store import RetrievedChunk
from rag_lab.text import sentences, terms
from rag_lab.tools import READ_CHUNK_TOOL_NAME, SEARCH_TOOL_NAME, RetrievalTools

ANSWERED = "answered"
INSUFFICIENT_CONTEXT = "insufficient_context"
INSUFFICIENT_CONTEXT_TEXT = (
    "The indexed documents do not contain enough information to answer this question."
)


@dataclass(frozen=True)
class Claim:
    text: str
    citation: str


@dataclass(frozen=True)
class Answer:
    question: str
    status: str
    text: str
    claims: tuple[Claim, ...]
    citations: tuple[str, ...]
    context_characters: int
    answerer: str


@dataclass(frozen=True)
class TraceEvent:
    run_id: str
    node_id: str
    tool_name: str | None
    arguments: dict[str, object]
    status: str
    detail: str
    transition_reason: str


@dataclass(frozen=True)
class AnswerRun:
    question: str
    answer: Answer
    retrieved: tuple[RetrievedChunk, ...]
    loaded: tuple[Chunk, ...]
    trace: tuple[TraceEvent, ...]


class Answerer(Protocol):
    name: str

    def answer(self, question: str, contexts: Sequence[Chunk]) -> Answer: ...


class ExtractiveAnswerer:
    name = "extractive-v1"

    def __init__(self, *, support_ratio: float = 0.5, max_claims: int = 3) -> None:
        if not 0.0 < support_ratio <= 1.0:
            raise ValueError("support_ratio must be between 0.0 and 1.0")
        if max_claims < 1:
            raise ValueError("max_claims must be positive")
        self._support_ratio = support_ratio
        self._max_claims = max_claims

    def answer(self, question: str, contexts: Sequence[Chunk]) -> Answer:
        question_terms = terms(question)
        if not question_terms:
            return _insufficient(question, contexts, self.name)

        required = max(1, math.ceil(self._support_ratio * len(question_terms)))
        claims: list[Claim] = []
        for chunk in contexts:
            for sentence in sentences(chunk.text):
                overlap = len(terms(sentence) & question_terms)
                if overlap >= required:
                    claims.append(Claim(text=sentence, citation=chunk.chunk_id))
                    break
            if len(claims) >= self._max_claims:
                break

        if not claims:
            return _insufficient(question, contexts, self.name)

        citations = tuple(dict.fromkeys(claim.citation for claim in claims))
        return Answer(
            question=question,
            status=ANSWERED,
            text=" ".join(claim.text for claim in claims),
            claims=tuple(claims),
            citations=citations,
            context_characters=sum(len(chunk.text) for chunk in contexts),
            answerer=self.name,
        )


def _insufficient(question: str, contexts: Sequence[Chunk], answerer: str) -> Answer:
    return Answer(
        question=question,
        status=INSUFFICIENT_CONTEXT,
        text=INSUFFICIENT_CONTEXT_TEXT,
        claims=(),
        citations=(),
        context_characters=sum(len(chunk.text) for chunk in contexts),
        answerer=answerer,
    )


def run_question(
    question: str,
    *,
    tools: RetrievalTools,
    answerer: Answerer,
    run_id: str = "local",
) -> AnswerRun:
    if not question.strip():
        raise ValueError("question must not be empty")

    trace: list[TraceEvent] = []
    search = tools.call(SEARCH_TOOL_NAME, {"query": question, "limit": tools.top_k})
    trace.append(
        TraceEvent(
            run_id=run_id,
            node_id="retrieval_tool",
            tool_name=search.name,
            arguments={"query": question, "limit": tools.top_k},
            status="complete",
            detail=f"{len(search.hits)} candidate chunks",
            transition_reason="candidates_found",
        )
    )

    loaded: list[Chunk] = []
    for candidate in search.hits:
        read = tools.call(READ_CHUNK_TOOL_NAME, {"chunk_id": candidate.chunk.chunk_id})
        loaded.extend(read.chunks)
        trace.append(
            TraceEvent(
                run_id=run_id,
                node_id="retrieval_tool",
                tool_name=read.name,
                arguments={"chunk_id": candidate.chunk.chunk_id},
                status="complete",
                detail=f"{read.returned_characters} characters loaded",
                transition_reason="chunk_loaded",
            )
        )

    answer = answerer.answer(question, tuple(loaded))
    trace.append(
        TraceEvent(
            run_id=run_id,
            node_id="answering",
            tool_name=None,
            arguments={
                "context_chunks": len(loaded),
                "context_characters": answer.context_characters,
            },
            status="complete",
            detail=answer.status,
            transition_reason=(
                "answer_grounded_in_context"
                if answer.status == ANSWERED
                else "no_supporting_context"
            ),
        )
    )
    return AnswerRun(
        question=question,
        answer=answer,
        retrieved=search.hits,
        loaded=tuple(loaded),
        trace=tuple(trace),
    )