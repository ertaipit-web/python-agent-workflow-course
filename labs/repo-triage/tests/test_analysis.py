from pathlib import Path

import pytest
from repo_triage.analysis import (
    Issue,
    RepositoryFile,
    create_report,
    inventory_repository,
    parse_issue,
    rank_files,
)
from repo_triage.cli import main


def test_parse_issue_reads_title_and_category(tmp_path: Path) -> None:
    issue_path = tmp_path / "01-filter.md"
    issue_path.write_text("# Fix status filter\nType: bug\n\nDetails.\n", encoding="utf-8")

    issue = parse_issue(issue_path)

    assert issue.title == "Fix status filter"
    assert issue.category == "bug"
    assert issue.issue_id == "01-filter"


def test_parse_issue_defaults_missing_or_unknown_type_to_ambiguous(tmp_path: Path) -> None:
    issue_path = tmp_path / "unclear.md"
    issue_path.write_text("# Unclear request\nType: feature\n", encoding="utf-8")

    assert parse_issue(issue_path).category == "ambiguous"


def test_parse_issue_rejects_duplicate_type_fields(tmp_path: Path) -> None:
    issue_path = tmp_path / "duplicate.md"
    issue_path.write_text("# Duplicated metadata\nType: bug\nType: docs\n", encoding="utf-8")

    with pytest.raises(ValueError, match="at most one Type"):
        parse_issue(issue_path)


def test_parse_issue_requires_markdown_heading(tmp_path: Path) -> None:
    issue_path = tmp_path / "missing-title.md"
    issue_path.write_text("Type: bug\n", encoding="utf-8")

    with pytest.raises(ValueError, match="expected a Markdown heading"):
        parse_issue(issue_path)


def test_inventory_extracts_python_symbols_and_markdown(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "docs").mkdir()
    (tmp_path / "src" / "catalog.py").write_text(
        "class Catalog:\n    def find_by_status(self, status):\n        return []\n",
        encoding="utf-8",
    )
    (tmp_path / "docs" / "guide.md").write_text("# Guide\n", encoding="utf-8")

    files = inventory_repository(tmp_path)

    assert files == [
        RepositoryFile(
            path="docs/guide.md",
            kind="markdown",
        ),
        RepositoryFile(
            path="src/catalog.py",
            kind="python",
            symbols=("Catalog", "Catalog.find_by_status"),
        ),
    ]


def test_inventory_skips_virtual_environments_and_reports_syntax_errors(tmp_path: Path) -> None:
    (tmp_path / ".venv" / "Lib").mkdir(parents=True)
    (tmp_path / ".venv" / "Lib" / "ignored.py").write_text("def hidden(): pass\n", encoding="utf-8")
    (tmp_path / "broken.py").write_text("def incomplete(:\n", encoding="utf-8")

    files = inventory_repository(tmp_path)

    assert [file.path for file in files] == ["broken.py"]
    assert files[0].syntax_error is not None
    assert "line 1" in files[0].syntax_error


def test_rank_files_prioritizes_matching_source_symbols() -> None:
    issue = Issue("bug", "Fix status filter", "bug", "", Path("bug.md"))
    matching = RepositoryFile(
        path="src/catalog.py",
        kind="python",
        symbols=("Catalog.filter_by_status",),
    )
    other = RepositoryFile(path="src/users.py", kind="python", symbols=("load_users",))

    assert rank_files(issue, [other, matching])[0] == matching


def test_test_issue_candidates_stay_within_test_scope() -> None:
    issue = Issue("test", "Add a status filter test", "test", "", Path("test.md"))
    source = RepositoryFile(path="src/catalog.py", kind="python")
    tests = RepositoryFile(path="tests/test_catalog.py", kind="python")

    assert rank_files(issue, [source, tests]) == [tests]


def test_rank_files_returns_no_suggestions_for_ambiguous_issue() -> None:
    issue = Issue("unclear", "Make it better", "ambiguous", "", Path("unclear.md"))

    assert rank_files(issue, [RepositoryFile("src/app.py", "python")]) == []


def test_report_marks_ambiguous_issue_as_needs_input(tmp_path: Path) -> None:
    repository = tmp_path / "repo"
    issues = tmp_path / "issues"
    repository.mkdir()
    issues.mkdir()
    (repository / "app.py").write_text("def run():\n    return True\n", encoding="utf-8")
    (issues / "unclear.md").write_text("# Improve the app\n", encoding="utf-8")

    report = create_report(repository, issues)

    assert "Status: `needs_input`" in report
    assert "Do not infer scope" in report


def test_report_includes_request_and_ranked_context(tmp_path: Path) -> None:
    repository = tmp_path / "repo"
    issues = tmp_path / "issues"
    (repository / "src").mkdir(parents=True)
    issues.mkdir()
    (repository / "src" / "catalog.py").write_text(
        "def filter_by_status(items, status):\n    return items\n",
        encoding="utf-8",
    )
    (issues / "filter.md").write_text(
        "# Fix status filter\nType: bug\n\nMatch status values without regard to case.\n",
        encoding="utf-8",
    )

    report = create_report(repository, issues)

    assert "Match status values without regard to case." in report
    assert "`src/catalog.py`" in report
    assert "ready_for_planning" in report


def test_cli_writes_report_to_requested_output(tmp_path: Path, monkeypatch) -> None:
    repository = tmp_path / "repo"
    issues = tmp_path / "issues"
    output = tmp_path / "triage.md"
    repository.mkdir()
    issues.mkdir()
    (issues / "unclear.md").write_text("# Unclear request\n", encoding="utf-8")
    monkeypatch.setattr(
        "sys.argv",
        ["repo-triage", "--repo", str(repository), "--issues", str(issues), "--output", str(output)],
    )

    exit_code = main()

    assert exit_code == 0
    assert "Repo Triage report" in output.read_text(encoding="utf-8")
