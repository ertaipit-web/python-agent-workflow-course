from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from integration_lab.client import IssueApiClient
from integration_lab.issue_api import SCOPE_READ, SCOPE_WRITE

READ_ONLY_SCOPES = frozenset({SCOPE_READ})
WRITE_SCOPES = frozenset({SCOPE_WRITE})


class ToolError(ValueError):
    pass


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    arguments: Mapping[str, str]
    required_arguments: tuple[str, ...]
    required_scopes: frozenset[str]
    side_effect: bool
    integer_limits: Mapping[str, tuple[int, int]] = field(default_factory=dict)


@dataclass(frozen=True)
class ToolCall:
    tool: str
    arguments: Mapping[str, object]


@dataclass(frozen=True)
class Tool:
    spec: ToolSpec
    handler: Callable[[Mapping[str, object]], object]


def _labels(arguments: Mapping[str, object]) -> tuple[str, ...]:
    labels = arguments.get("labels", [])
    if isinstance(labels, (list, tuple)):
        return tuple(str(label) for label in labels)
    return ()


def build_registry(client: IssueApiClient | None) -> dict[str, Tool]:
    """Build the tool registry.

    When client is None (test mode), handlers are still defined but never
    invoked — ScriptedPlanner returns empty calls, so the loop body never
    reaches tool.handler(). This keeps the registry consistent without
    requiring a real GitHub client.
    """
    def _no_client(*_args: object, **_kwargs: object) -> dict[str, Any]:
        raise RuntimeError("no GitHub client configured for this runner mode")

    def _safe_handler(handler):
        if client is None:
            return lambda arguments: _no_client()
        return handler

    tools = (
        Tool(
            spec=ToolSpec(
                name="list_issues",
                description="List issues of one repository. Read-only.",
                arguments={
                    "owner": "repository owner",
                    "repository": "repository name",
                    "state": "open, closed or all",
                    "limit": "how many issues to return",
                },
                required_arguments=("owner", "repository"),
                required_scopes=READ_ONLY_SCOPES,
                side_effect=False,
                integer_limits={"limit": (1, 100)},
            ),
            handler=_safe_handler(lambda arguments: client.list_issues(
                str(arguments["owner"]),
                str(arguments["repository"]),
                state=str(arguments.get("state", "open")),
                limit=int(arguments.get("limit", 10)),
            )),
        ),
        Tool(
            spec=ToolSpec(
                name="get_issue",
                description="Read one issue by number. Read-only.",
                arguments={
                    "owner": "repository owner",
                    "repository": "repository name",
                    "number": "issue number",
                },
                required_arguments=("owner", "repository", "number"),
                required_scopes=READ_ONLY_SCOPES,
                side_effect=False,
                integer_limits={"number": (1, 1_000_000)},
            ),
            handler=_safe_handler(lambda arguments: client.get_issue(
                str(arguments["owner"]), str(arguments["repository"]), int(arguments["number"])
            )),
        ),
        Tool(
            spec=ToolSpec(
                name="create_issue",
                description="File a new issue in a repository. External side effect.",
                arguments={
                    "owner": "repository owner",
                    "repository": "repository name",
                    "title": "one line summary",
                    "body": "details of the issue",
                    "labels": "list of label names",
                },
                required_arguments=("owner", "repository", "title"),
                required_scopes=WRITE_SCOPES,
                side_effect=True,
            ),
            handler=_safe_handler(lambda arguments: client.create_issue(
                str(arguments["owner"]),
                str(arguments["repository"]),
                title=str(arguments["title"]),
                body=str(arguments.get("body", "")),
                labels=_labels(arguments),
            )),
        ),
        Tool(
            spec=ToolSpec(
                name="close_issue",
                description="Close an existing issue. External side effect.",
                arguments={
                    "owner": "repository owner",
                    "repository": "repository name",
                    "number": "issue number",
                },
                required_arguments=("owner", "repository", "number"),
                required_scopes=WRITE_SCOPES,
                side_effect=True,
                integer_limits={"number": (1, 1_000_000)},
            ),
            handler=_safe_handler(lambda arguments: client.close_issue(
                str(arguments["owner"]), str(arguments["repository"]), int(arguments["number"])
            )),
        ),
    )
    return {tool.spec.name: tool for tool in tools}


def validate_arguments(spec: ToolSpec, arguments: Mapping[str, object]) -> dict[str, object]:
    unknown = sorted(set(arguments) - set(spec.arguments))
    if unknown:
        raise ToolError(f"{spec.name}: unknown argument '{unknown[0]}'")

    missing = [name for name in spec.required_arguments if name not in arguments]
    if missing:
        raise ToolError(f"{spec.name}: missing required argument '{missing[0]}'")

    validated: dict[str, object] = {}
    for name, value in arguments.items():
        limits = spec.integer_limits.get(name)
        if limits is not None:
            if isinstance(value, bool) or not isinstance(value, int):
                raise ToolError(f"{spec.name}: argument '{name}' must be an integer")
            minimum, maximum = limits
            if not minimum <= value <= maximum:
                raise ToolError(
                    f"{spec.name}: argument '{name}' must be between {minimum} and {maximum}"
                )
        elif name == "labels":
            if not isinstance(value, (list, tuple)) or not all(
                isinstance(label, str) for label in value
            ):
                raise ToolError(f"{spec.name}: argument '{name}' must be a list of strings")
        else:
            if not isinstance(value, str):
                raise ToolError(f"{spec.name}: argument '{name}' must be a string")
            if not value.strip():
                raise ToolError(f"{spec.name}: argument '{name}' must not be empty")
        validated[name] = value
    return validated