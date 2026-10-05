from pathlib import Path

import pytest

from rag_lab.cli import create_report, main

LAB = Path(__file__).resolve().parents[1]
CORPUS = LAB / "corpus"
QUESTIONS = LAB / "questions.json"


def test_report_covers_the_run_and_the_evaluation() -> None:
    report = create_report(CORPUS, QUESTIONS)

    assert "# RAG lab report" in report
    assert "Documents: 4" in report
    assert "Answer status: `answered`" in report
    assert "Answer status: `insufficient_context`" in report
    assert "Retrieval relevance: 1.00" in report
    assert "Unsupported answer rate: 0.00" in report


def test_report_states_that_only_needed_context_is_loaded() -> None:
    report = create_report(CORPUS, QUESTIONS, top_k=2)

    corpus_line = next(line for line in report.splitlines() if line.startswith("- Corpus characters:"))
    corpus_characters = int(corpus_line.split(":")[1])

    loaded = [
        int(line.split(":")[1].split(" of ")[0])
        for line in report.splitlines()
        if line.startswith("- Loaded context:")
    ]
    assert loaded
    assert all(characters < corpus_characters for characters in loaded)
    assert "- Retrieved chunks per question: 2" in report


def test_report_can_run_a_single_case() -> None:
    report = create_report(CORPUS, QUESTIONS, case_id="outside-the-corpus")

    assert report.count("### ") == 1
    assert "Answer status: `insufficient_context`" in report
    assert "coffee beans" in report


def test_unknown_case_id_is_reported_as_an_error() -> None:
    with pytest.raises(ValueError, match="Unknown case_id: nope"):
        create_report(CORPUS, QUESTIONS, case_id="nope")


def test_cli_writes_the_report_to_the_requested_output(tmp_path: Path, monkeypatch) -> None:
    output = tmp_path / "rag-report.md"
    monkeypatch.setattr(
        "sys.argv",
        [
            "rag-lab",
            "--corpus",
            str(CORPUS),
            "--cases",
            str(QUESTIONS),
            "--case",
            "handoff-fields",
            "--output",
            str(output),
        ],
    )

    exit_code = main()

    assert exit_code == 0
    assert "# RAG lab report" in output.read_text(encoding="utf-8")


def test_cli_rejects_a_missing_corpus(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        "sys.argv",
        ["rag-lab", "--corpus", str(tmp_path / "nope"), "--cases", str(QUESTIONS)],
    )

    with pytest.raises(SystemExit) as exit_info:
        main()

    assert exit_info.value.code == 2
