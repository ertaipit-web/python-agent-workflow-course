from __future__ import annotations

import argparse
import sys
from collections.abc import Callable, Sequence
from pathlib import Path

from integration_lab.client import IssueApiClient
from integration_lab.issue_api import IssueApi, Token
from integration_lab.runtime import AgentRuntime, Policy, ScriptedPlanner, ToolCall
from integration_lab.tools import READ_ONLY_SCOPES, WRITE_SCOPES

OWNER = "course"
REPOSITORY = "taskboard"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run an agent against a local issue API and show the permission, approval "
            "and trace decisions of every proposed tool call."
        )
    )
    parser.add_argument(
        "--database",
        type=Path,
        default=Path("issues-lab.db"),
        help="SQLite file used by the local issue API",
    )
    parser.add_argument("--port", type=int, default=8765, help="Port for the local issue API")
    parser.add_argument("--timeout", type=float, default=2.0, help="Client timeout in seconds")
    parser.add_argument(
        "--scenario",
        choices=("read", "write-approved", "write-denied", "delete"),
        default="read",
        help="Which tool call sequence to demonstrate",
    )
    parser.add_argument(
        "--approve-writes",
        action="store_true",
        help="Act as the human approver for tools with an external side effect",
    )
    parser.add_argument("--output", type=Path, help="Write the report to this file instead of stdout")
    return parser


def main() -> int:
    parser = build_parser()
    arguments = parser.parse_args()
    api = IssueApi(
        database=arguments.database,
        tokens=(
            Token(name="read-only", scopes=READ_ONLY_SCOPES),
            Token(name="read-write", scopes=READ_ONLY_SCOPES | WRITE_SCOPES),
        ),
    )
    api.store.create_issue(
        OWNER, REPOSITORY, title="Filter ignores status case", body="", labels=("bug",)
    )
    api.store.create_issue(
        OWNER, REPOSITORY, title="Document status values", body="", labels=("docs",)
    )
    base_url = api.start(port=arguments.port)
    approver = approve if arguments.approve_writes else None
    try:
        report = create_report(
            base_url,
            scenario=arguments.scenario,
            timeout=arguments.timeout,
            approver=approver,
        )
        if arguments.output is None:
            sys.stdout.write(report)
        else:
            arguments.output.write_text(report, encoding="utf-8")
    except (OSError, ValueError) as error:
        parser.exit(2, f"{parser.prog}: error: {error}\n")
    finally:
        api.close()
    return 0


def approve(call: ToolCall, reason: str) -> bool:
    return True


def create_report(
    base_url: str,
    *,
    scenario: str = "read",
    timeout: float = 2.0,
    approver: Callable[[ToolCall, str], bool] | None = None,
) -> str:
    client = IssueApiClient(base_url, "read-write", timeout=timeout)
    calls, policy, scenarios = _scenario(scenario, approver)
    runtime = AgentRuntime(client=client, policy=policy, planner=ScriptedPlanner(calls))
    run = runtime.run(f"scenario: {scenario}")

    allowlist = ", ".join(f"{owner}/{name}" for owner, name in policy.allowed_repositories)
    lines = [
        "# Integration lab report",
        "",
        f"- Base URL: `{base_url}`",
        f"- Scenario: `{scenario}`",
        f"- Granted scopes: {', '.join(sorted(policy.granted_scopes)) or '-'}",
        f"- Allowlisted repositories: {allowlist}",
        f"- Tools exposed to the agent: {', '.join(spec.name for spec in runtime.tools())}",
        "",
        (
            "The issue API also implements DELETE /repos/{owner}/{repository}. No agent tool wraps "
            "it, so the agent cannot reach it."
        ),
        "",
    ]
    lines.extend(run.lines())
    lines.extend(["", "## Scenarios", ""])
    lines.extend(f"- `{name}`: {description}" for name, description in scenarios)
    lines.extend(
        [
            "",
            f"External HTTP calls made by the client: {client.call_count}.",
            "",
            (
            "Read tools run without a human. Tools with an external side effect need both an "
            "approval and a granted scope before they reach the API."
        ),
            "",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def _scenario(
    scenario: str, approver: Callable[[ToolCall, str], bool] | None
) -> tuple[list[ToolCall], Policy, Sequence[tuple[str, str]]]:
    read_calls = [
        ToolCall("list_issues", {"owner": OWNER, "repository": REPOSITORY, "state": "open"}),
    ]
    write_call = ToolCall(
        "create_issue",
        {
            "owner": OWNER,
            "repository": REPOSITORY,
            "title": "Triage: status filter is case sensitive",
            "body": "Found by the read-only analyst. Scope: filter_tasks in src/taskboard/core.py.",
            "labels": ["bug", "needs-triage"],
        },
    )
    allowed = frozenset({(OWNER, REPOSITORY)})
    resolve_approver = approver if callable(approver) else (lambda call, reason: False)

    match scenario:
        case "read":
            return (
                read_calls,
                Policy(granted_scopes=READ_ONLY_SCOPES, allowed_repositories=allowed),
                (
                    ("read", "read-only analyst lists issues with a read scope"),
                    ("write-approved", "a write tool runs only after a human approved it"),
                    ("write-denied", "the same write tool stops at the approval gate"),
                    ("delete", "a tool that is not in the registry is rejected"),
                ),
            )
        case "write-approved":
            return (
                read_calls + [write_call],
                Policy(
                    granted_scopes=READ_ONLY_SCOPES | WRITE_SCOPES,
                    allowed_repositories=allowed,
                    approver=resolve_approver,
                ),
                (("write-approved", "read, then an approved write"),),
            )
        case "write-denied":
            return (
                read_calls + [write_call],
                Policy(
                    granted_scopes=READ_ONLY_SCOPES | WRITE_SCOPES,
                    allowed_repositories=allowed,
                    approver=resolve_approver,
                ),
                (("write-denied", "the approver returns False, so nothing is written"),),
            )
        case "delete":
            return (
                [ToolCall("delete_repository", {"owner": OWNER, "repository": REPOSITORY})],
                Policy(granted_scopes=READ_ONLY_SCOPES | WRITE_SCOPES, allowed_repositories=allowed),
                (("delete", "the delete route exists in the API but no agent tool exposes it"),),
            )
    raise ValueError(f"Unknown scenario: {scenario}")


if __name__ == "__main__":
    raise SystemExit(main())
