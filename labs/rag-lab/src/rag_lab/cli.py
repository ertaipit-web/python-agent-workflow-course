from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from rag_lab.agent import ANSWERED, AnswerRun, ExtractiveAnswerer
from rag_lab.evaluation import EvaluationCase, evaluate, load_cases
from rag_lab.store import build_index
from rag_lab.tools import RetrievalTools


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Answer questions from a Markdown corpus through a retrieval tool and "
            "report retrieval quality."
        )
    )
    parser.add_argument("--corpus", type=Path, required=True, help="Directory with Markdown documents")
    parser.add_argument("--cases", type=Path, required=True, help="JSON file with evaluation cases")
    parser.add_argument("--case", help="Run only the case with this case_id")
    parser.add_argument("--top-k", type=int, default=3, help="How many chunks to retrieve per question")
    parser.add_argument("--output", type=Path, help="Write the report to this file instead of stdout")
    return parser


def main() -> int:
    parser = build_parser()
    arguments = parser.parse_args()
    try:
        report = create_report(
            arguments.corpus,
            arguments.cases,
            case_id=arguments.case,
            top_k=arguments.top_k,
        )
        if arguments.output is None:
            sys.stdout.write(report)
        else:
            arguments.output.write_text(report, encoding="utf-8")
    except (OSError, ValueError) as error:
        parser.exit(2, f"{parser.prog}: error: {error}\n")
    return 0


def create_report(
    corpus: Path,
    cases: Path,
    *,
    case_id: str | None = None,
    top_k: int = 3,
) -> str:
    store = build_index(corpus)
    tools = RetrievalTools(store, top_k=top_k)
    answerer = ExtractiveAnswerer()

    selected = _select(load_cases(cases), case_id)
    report = evaluate(selected, tools=tools, answerer=answerer)

    lines = [
        "# RAG lab report",
        "",
        f"- Corpus: `{corpus.as_posix()}`",
        f"- Documents: {len(store.sources)}",
        f"- Chunks: {len(store)}",
        f"- Corpus characters: {store.total_characters}",
        f"- Embedder: `{store.embedder_name}`",
        f"- Retrieved chunks per question: {top_k}",
        "",
        (
            "The agent never receives the whole corpus: it calls the retrieval tool and only "
            "loads the chunks it needs for the current question."
        ),
        "",
    ]
    lines.extend(_run_lines(report.runs, store.total_characters))
    lines.extend(report.lines())
    return "\n".join(lines).rstrip() + "\n"


def _select(cases: tuple[EvaluationCase, ...], case_id: str | None) -> tuple[EvaluationCase, ...]:
    if case_id is None:
        return cases
    selected = tuple(case for case in cases if case.case_id == case_id)
    if not selected:
        raise ValueError(f"Unknown case_id: {case_id}")
    return selected


def _run_lines(runs: Sequence[AnswerRun], corpus_characters: int) -> list[str]:
    lines = ["## Answers", ""]
    for run in runs:
        answer = run.answer
        loaded_characters = sum(len(chunk.text) for chunk in run.loaded)
        retrieved = ", ".join(
            f"{hit.chunk.chunk_id} ({hit.score:.3f})" for hit in run.retrieved
        )
        lines.extend(
            [
                f"### {run.question}",
                "",
                f"- Retrieved: {retrieved or 'nothing'}",
                f"- Loaded context: {loaded_characters} of {corpus_characters} corpus characters",
                f"- Answer status: `{answer.status}`",
                f"- Answer: {answer.text}",
                f"- Citations: {', '.join(f'`{value}`' for value in answer.citations) or '-'}",
                "",
            ]
        )
        if answer.status != ANSWERED:
            lines.extend(
                [
                    (
                        "The agent refuses to answer without retrieved evidence instead of "
                        "inventing a plausible answer."
                    ),
                    "",
                ]
            )
    return lines