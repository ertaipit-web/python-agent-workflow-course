from __future__ import annotations

from pathlib import Path

import pytest

from integration_lab.cli import build_parser, create_report, main
from integration_lab.issue_api import IssueApi, Token
from integration_lab.runtime import BLOCKED, COMPLETED, NEEDS_APPROVAL
from integration_lab.tools import READ_ONLY_SCOPES, WRITE_SCOPES


@pytest.fixture
def api(tmp_path: Path) -> IssueApi:
    instance = IssueApi(
        database=tmp_path / "cli.db",
        tokens=(
            Token(name="read-only", scopes=READ_ONLY_SCOPES),
            Token(name="read-write", scopes=READ_ONLY_SCOPES | WRITE_SCOPES),
        ),
    )
    instance.store.create_issue(
        "course", "taskboard", title="Filter ignores case", body="", labels=("bug",)
    )
    instance.start()
    try:
        yield instance
    finally:
        instance.close()


def test_parser_exposes_the_documented_options() -> None:
    parser = build_parser()

    assert parser.parse_args([]).scenario == "read"
    assert parser.parse_args(["--scenario", "delete"]).scenario == "delete"
    assert parser.parse_args(["--approve-writes"]).approve_writes is True
    assert parser.parse_args([]).approve_writes is False
    with pytest.raises(SystemExit):
        parser.parse_args(["--scenario", "publish"])


def test_read_scenario_completes_without_an_approval(api: IssueApi) -> None:
    report = create_report(api.base_url, scenario="read")

    assert "- Status: `completed`" in report
    assert "- Granted scopes: issues:read" in report
    assert "The issue API also implements DELETE" in report
    assert "External HTTP calls made by the client: 1." in report


def test_write_scenario_without_an_approver_waits_for_a_human(api: IssueApi) -> None:
    report = create_report(api.base_url, scenario="write-denied")

    assert f"- Status: `{NEEDS_APPROVAL}`" in report
    assert "Waiting for approval: `create_issue`" in report
    assert api.store.count() == 1


def test_approved_write_scenario_reaches_the_api(api: IssueApi) -> None:
    report = create_report(
        api.base_url, scenario="write-approved", approver=lambda call, reason: True
    )

    assert f"- Status: `{COMPLETED}`" in report
    assert api.store.count() == 2


def test_write_approved_scenario_waits_without_an_approver(api: IssueApi) -> None:
    report = create_report(api.base_url, scenario="write-approved")

    assert f"- Status: `{NEEDS_APPROVAL}`" in report
    assert api.store.count() == 1


def test_cli_approve_writes_flag_performs_the_write(tmp_path: Path, monkeypatch) -> None:
    database = tmp_path / "approved.db"
    output = tmp_path / "approved.md"
    monkeypatch.setattr(
        "sys.argv",
        [
            "integration-lab",
            "--database",
            str(database),
            "--port",
            "0",
            "--scenario",
            "write-approved",
            "--approve-writes",
            "--output",
            str(output),
        ],
    )

    exit_code = main()

    assert exit_code == 0
    report = output.read_text(encoding="utf-8")
    assert f"- Status: `{COMPLETED}`" in report

    reopened = IssueApi(
        database=database,
        tokens=(Token(name="read-write", scopes=READ_ONLY_SCOPES | WRITE_SCOPES),),
    )
    try:
        reopened.start()
        assert reopened.store.count() == 3
    finally:
        reopened.close()


def test_delete_scenario_is_rejected_by_the_registry(api: IssueApi) -> None:
    report = create_report(api.base_url, scenario="delete")

    assert f"- Status: `{BLOCKED}`" in report
    assert "tool_not_registered" in report
    assert api.store.count() == 1


def test_cli_writes_a_report_and_stops_the_api(tmp_path: Path, monkeypatch) -> None:
    database = tmp_path / "cli.db"
    output = tmp_path / "report.md"
    monkeypatch.setattr(
        "sys.argv",
        [
            "integration-lab",
            "--database",
            str(database),
            "--port",
            "0",
            "--scenario",
            "read",
            "--output",
            str(output),
        ],
    )

    exit_code = main()

    assert exit_code == 0
    assert "# Integration lab report" in output.read_text(encoding="utf-8")
    assert database.is_file()


def test_create_report_rejects_an_unknown_scenario(api: IssueApi) -> None:
    with pytest.raises(ValueError, match="Unknown scenario: publish"):
        create_report(api.base_url, scenario="publish")
