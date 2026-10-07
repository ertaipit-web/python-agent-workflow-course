from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from integration_lab.client import IssueApiClient
from integration_lab.issue_api import SCOPE_READ, SCOPE_WRITE, IssueApi, Token
from integration_lab.runtime import (
    BLOCKED,
    COMPLETED,
    NEEDS_APPROVAL,
    AgentRuntime,
    Policy,
    ScriptedPlanner,
    ToolCall,
    redact,
)
from integration_lab.tools import READ_ONLY_SCOPES, WRITE_SCOPES

OWNER = "course"
REPOSITORY = "taskboard"
ALLOWED = frozenset({(OWNER, REPOSITORY)})
READ_CALL = ToolCall("list_issues", {"owner": OWNER, "repository": REPOSITORY})
WRITE_CALL = ToolCall(
    "create_issue",
    {"owner": OWNER, "repository": REPOSITORY, "title": "Triage status filter"},
)


@pytest.fixture
def api(tmp_path: Path) -> Iterator[IssueApi]:
    instance = IssueApi(
        database=tmp_path / "issues.db",
        tokens=(
            Token(name="read-only", scopes=READ_ONLY_SCOPES),
            Token(name="read-write", scopes=READ_ONLY_SCOPES | WRITE_SCOPES),
        ),
    )
    instance.store.create_issue(
        OWNER, REPOSITORY, title="Filter ignores case", body="", labels=("bug",)
    )
    instance.start()
    try:
        yield instance
    finally:
        instance.close()


@pytest.fixture
def client(api: IssueApi) -> IssueApiClient:
    return IssueApiClient(api.base_url, "read-write", timeout=2.0)


def run_with(client: IssueApiClient, policy: Policy, calls: list[ToolCall]):
    runtime = AgentRuntime(
        client=client,
        policy=policy,
        planner=ScriptedPlanner(calls),
        run_id="test-run",
    )
    return runtime, runtime.run("triage the filter bug")


def test_read_tool_runs_with_only_a_read_scope(client: IssueApiClient) -> None:
    policy = Policy(granted_scopes=READ_ONLY_SCOPES, allowed_repositories=ALLOWED)

    runtime, run = run_with(client, policy, [READ_CALL])

    assert run.status == COMPLETED
    assert run.results[0][0]["title"] == "Filter ignores case"
    assert [event.transition_reason for event in run.trace] == ["tool_complete"]
    assert all(event.run_id == "test-run" for event in runtime.run("triage").trace)


def test_write_tool_needs_approval_and_stops_before_the_api(
    client: IssueApiClient, api: IssueApi
) -> None:
    policy = Policy(
        granted_scopes=READ_ONLY_SCOPES | WRITE_SCOPES,
        allowed_repositories=ALLOWED,
        approver=None,
    )

    _, run = run_with(client, policy, [READ_CALL, WRITE_CALL])

    assert run.status == NEEDS_APPROVAL
    assert run.pending_approval is not None
    assert run.pending_approval.tool == "create_issue"
    assert run.trace[-1].status == "awaiting_approval"
    assert run.trace[-1].transition_reason == "needs_approval"
    assert api.store.count() == 1


def test_approved_write_reaches_the_external_system(client: IssueApiClient, api: IssueApi) -> None:
    policy = Policy(
        granted_scopes=READ_ONLY_SCOPES | WRITE_SCOPES,
        allowed_repositories=ALLOWED,
        approver=lambda call, reason: True,
    )

    _, run = run_with(client, policy, [READ_CALL, WRITE_CALL])

    assert run.status == COMPLETED
    assert len(run.results) == 2
    assert run.results[1]["number"] == 2
    assert api.store.count() == 2


def test_denied_approval_keeps_the_run_without_a_side_effect(
    client: IssueApiClient, api: IssueApi
) -> None:
    policy = Policy(
        granted_scopes=READ_ONLY_SCOPES | WRITE_SCOPES,
        allowed_repositories=ALLOWED,
        approver=lambda call, reason: False,
    )

    _, run = run_with(client, policy, [WRITE_CALL])

    assert run.status == NEEDS_APPROVAL
    assert api.store.count() == 1


def test_missing_write_scope_blocks_before_approval(client: IssueApiClient, api: IssueApi) -> None:
    policy = Policy(
        granted_scopes=frozenset({SCOPE_READ}),
        allowed_repositories=ALLOWED,
        approver=lambda call, reason: True,
    )

    _, run = run_with(client, policy, [WRITE_CALL])

    assert run.status == BLOCKED
    assert run.reason == f"missing scope: {SCOPE_WRITE}"
    assert run.trace[-1].error_type == "insufficient_scope"
    assert api.store.count() == 1


def test_repository_outside_the_allowlist_is_rejected(client: IssueApiClient) -> None:
    policy = Policy(granted_scopes=READ_ONLY_SCOPES, allowed_repositories=ALLOWED)
    call = ToolCall("list_issues", {"owner": OWNER, "repository": "someone-else"})

    _, run = run_with(client, policy, [call])

    assert run.status == BLOCKED
    assert run.reason == "list_issues: repository is not allowlisted"
    assert run.trace[-1].transition_reason == "repository_not_allowed"


def test_tool_outside_the_registry_is_rejected_by_name(client: IssueApiClient) -> None:
    policy = Policy(granted_scopes=READ_ONLY_SCOPES | WRITE_SCOPES, allowed_repositories=ALLOWED)
    call = ToolCall("delete_repository", {"owner": OWNER, "repository": REPOSITORY})

    runtime, run = run_with(client, policy, [call])

    assert run.status == BLOCKED
    assert run.reason == "delete_repository is not in the tool registry"
    assert "delete_repository" not in {spec.name for spec in runtime.tools()}


def test_invalid_arguments_are_rejected_before_execution(client: IssueApiClient) -> None:
    policy = Policy(granted_scopes=READ_ONLY_SCOPES, allowed_repositories=ALLOWED)
    call = ToolCall("list_issues", {"owner": OWNER, "repository": REPOSITORY, "path": "/etc/passwd"})

    _, run = run_with(client, policy, [call])

    assert run.status == BLOCKED
    assert run.trace[-1].error_type == "invalid_arguments"
    assert run.trace[-1].detail == "list_issues: unknown argument 'path'"


def test_external_failure_blocks_the_run_instead_of_reporting_success(
    api: IssueApi,
) -> None:
    api.stop()
    api.start(port=0)
    policy = Policy(granted_scopes=READ_ONLY_SCOPES, allowed_repositories=ALLOWED)

    _, blocked = run_with(IssueApiClient(api.base_url, "made-up-token", timeout=1.0), policy, [READ_CALL])
    _, allowed = run_with(IssueApiClient(api.base_url, "read-write", timeout=1.0), policy, [READ_CALL])

    assert blocked.status == BLOCKED
    assert blocked.trace[-1].error_type == "AuthenticationError"
    assert blocked.trace[-1].transition_reason == "tool_failed"
    assert allowed.status == COMPLETED


def test_redaction_hides_secrets_and_truncates_long_values() -> None:
    redacted = redact(
        {
            "token": "ghp_secret_value",
            "authorization": "Bearer ghp_secret_value",
            "body": "x" * 200,
            "title": "short",
            "number": 7,
        }
    )

    assert redacted["token"] == "***"
    assert redacted["authorization"] == "***"
    assert redacted["body"].endswith("...")
    assert len(redacted["body"]) == 123
    assert redacted["title"] == "short"
    assert redacted["number"] == 7


def test_run_report_renders_a_readable_trace(client: IssueApiClient) -> None:
    policy = Policy(granted_scopes=READ_ONLY_SCOPES, allowed_repositories=ALLOWED)

    _, run = run_with(client, policy, [READ_CALL])
    rendered = "\n".join(run.lines())

    assert "- Status: `completed`" in rendered
    assert "| list_issues | complete |" in rendered
