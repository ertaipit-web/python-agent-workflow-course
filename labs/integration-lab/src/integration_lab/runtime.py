from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Protocol

from integration_lab.client import IssueApiClient
from integration_lab.errors import IntegrationError
from integration_lab.tools import (
    Tool,
    ToolCall,
    ToolError,
    ToolSpec,
    build_registry,
    validate_arguments,
)

COMPLETED = "completed"
NEEDS_APPROVAL = "needs_approval"
BLOCKED = "blocked"
REDACTED_ARGUMENTS = frozenset({"token", "secret", "authorization", "password"})
_ARGUMENT_PREVIEW = 120


@dataclass(frozen=True)
class Policy:
    granted_scopes: frozenset[str]
    allowed_repositories: frozenset[tuple[str, str]]
    approver: Callable[[ToolCall, str], bool] | None = None

    def allows_repository(self, arguments: Mapping[str, object]) -> bool:
        repository = (str(arguments.get("owner", "")), str(arguments.get("repository", "")))
        return repository in self.allowed_repositories


@dataclass(frozen=True)
class TraceEvent:
    run_id: str
    node_id: str
    tool_name: str | None
    arguments: dict[str, object]
    status: str
    detail: str
    error_type: str | None
    transition_reason: str


@dataclass(frozen=True)
class RunReport:
    task: str
    status: str
    results: tuple[Mapping[str, object], ...]
    pending_approval: ToolCall | None
    reason: str | None
    trace: tuple[TraceEvent, ...]

    def lines(self) -> tuple[str, ...]:
        rows = ["## Agent run", "", f"- Task: {self.task}", f"- Status: `{self.status}`"]
        if self.reason:
            rows.append(f"- Reason: {self.reason}")
        if self.pending_approval is not None:
            rows.append(
                f"- Waiting for approval: `{self.pending_approval.tool}` with "
                f"{redact(self.pending_approval.arguments)}"
            )
        rows.append("")
        rows.append("| tool | status | detail | error | transition |")
        rows.append("|---|---|---|---|---|")
        for event in self.trace:
            rows.append(
                f"| {event.tool_name or '-'} | {event.status} | {event.detail} | "
                f"{event.error_type or '-'} | {event.transition_reason} |"
            )
        return tuple(rows)


def redact(arguments: Mapping[str, object]) -> dict[str, object]:
    redacted: dict[str, object] = {}
    for name, value in arguments.items():
        if name.casefold() in REDACTED_ARGUMENTS:
            redacted[name] = "***"
        elif isinstance(value, str) and len(value) > _ARGUMENT_PREVIEW:
            redacted[name] = value[:_ARGUMENT_PREVIEW] + "..."
        else:
            redacted[name] = value
    return redacted


class Planner(Protocol):
    name: str

    def plan(self, task: str, tools: Sequence[ToolSpec]) -> list[ToolCall]: ...


class ScriptedPlanner:
    name = "scripted-v1"

    def __init__(self, calls: Sequence[ToolCall]) -> None:
        self._calls = list(calls)

    def plan(self, task: str, tools: Sequence[ToolSpec]) -> list[ToolCall]:
        return list(self._calls)


@dataclass
class AgentRuntime:
    client: IssueApiClient
    policy: Policy
    planner: Planner
    run_id: str = "run-1"
    node_id: str = "issue_agent"
    registry: dict[str, Tool] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.registry:
            self.registry = build_registry(self.client)

    def tools(self) -> tuple[ToolSpec, ...]:
        return tuple(tool.spec for tool in self.registry.values())

    def run(self, task: str) -> RunReport:
        trace: list[TraceEvent] = []
        results: list[Mapping[str, object]] = []
        status = COMPLETED
        reason: str | None = None
        pending: ToolCall | None = None

        for call in self.planner.plan(task, self.tools()):
            tool = self.registry.get(call.tool)
            if tool is None:
                trace.append(self._event(call, "rejected", "tool is not exposed to the agent",
                                         "tool_not_registered", "tool_not_registered"))
                status, reason = BLOCKED, f"{call.tool} is not in the tool registry"
                break

            try:
                arguments = validate_arguments(tool.spec, call.arguments)
            except ToolError as error:
                trace.append(self._event(call, "rejected", str(error), "invalid_arguments",
                                         "invalid_arguments"))
                status, reason = BLOCKED, str(error)
                break

            if not self.policy.allows_repository(arguments):
                trace.append(self._event(call, "rejected", "repository is not allowlisted",
                                         "repository_not_allowed", "repository_not_allowed"))
                status, reason = BLOCKED, f"{call.tool}: repository is not allowlisted"
                break

            missing = sorted(tool.spec.required_scopes - self.policy.granted_scopes)
            if missing:
                detail = f"missing scope: {', '.join(missing)}"
                trace.append(self._event(call, "rejected", detail, "insufficient_scope",
                                         "insufficient_scope"))
                status, reason = BLOCKED, detail
                break

            if tool.spec.side_effect and not self._approved(call):
                pending = call
                trace.append(self._event(call, "awaiting_approval", "human approval required",
                                         None, "needs_approval"))
                status, reason = NEEDS_APPROVAL, f"{call.tool} has an external side effect"
                break

            try:
                results.append(tool.handler(arguments))
            except IntegrationError as error:
                trace.append(self._event(call, "failed", str(error), type(error).__name__,
                                         "tool_failed"))
                status, reason = BLOCKED, f"{call.tool}: {error}"
                break
            trace.append(self._event(call, "complete", "result returned", None, "tool_complete"))

        return RunReport(
            task=task,
            status=status,
            results=tuple(results),
            pending_approval=pending,
            reason=reason,
            trace=tuple(trace),
        )

    def _approved(self, call: ToolCall) -> bool:
        if self.policy.approver is None:
            return False
        return bool(self.policy.approver(call, f"{call.tool} changes an external system"))

    def _event(
        self,
        call: ToolCall,
        status: str,
        detail: str,
        error_type: str | None,
        transition_reason: str,
    ) -> TraceEvent:
        return TraceEvent(
            run_id=self.run_id,
            node_id=self.node_id,
            tool_name=call.tool,
            arguments=redact(call.arguments),
            status=status,
            detail=detail,
            error_type=error_type,
            transition_reason=transition_reason,
        )
