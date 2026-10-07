from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from pathlib import Path

ISSUE_TYPES = frozenset({"bug", "test", "docs", "ambiguous"})
IGNORED_DIRECTORY_NAMES = frozenset(
    {
        ".git",
        ".hg",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".venv",
        "__pycache__",
        "build",
        "dist",
        "node_modules",
        "venv",
    }
)

_WORD_PATTERN = re.compile(r"[^\W_]+", re.UNICODE)
_STOP_WORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "as",
        "at",
        "be",
        "for",
        "from",
        "in",
        "is",
        "it",
        "of",
        "on",
        "or",
        "the",
        "to",
        "with",
        "в",
        "для",
        "и",
        "из",
        "на",
        "по",
        "с",
        "это",
    }
)


@dataclass(frozen=True)
class Issue:
    issue_id: str
    title: str
    category: str
    body: str
    path: Path


@dataclass(frozen=True)
class RepositoryFile:
    path: str
    kind: str
    symbols: tuple[str, ...] = ()
    syntax_error: str | None = None


def _extract_symbols(nodes: list[ast.stmt], prefix: str = "") -> list[str]:
    symbols: list[str] = []
    for node in nodes:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            symbols.append(f"{prefix}{node.name}")
        elif isinstance(node, ast.ClassDef):
            class_name = f"{prefix}{node.name}"
            symbols.append(class_name)
            symbols.extend(_extract_symbols(node.body, f"{class_name}."))
    return symbols


def parse_issue(path: Path) -> Issue:
    lines = path.read_text(encoding="utf-8").splitlines()
    title_line = next((line for line in lines if line.startswith("# ")), None)
    if title_line is None:
        raise ValueError(f"{path}: expected a Markdown heading beginning with '# '")

    category_lines = [
        line.split(":", maxsplit=1)[1].strip().casefold()
        for line in lines
        if line.casefold().startswith("type:")
    ]
    if len(category_lines) > 1:
        raise ValueError(f"{path}: expected at most one Type: field")

    category = category_lines[0] if category_lines else "ambiguous"
    if category not in ISSUE_TYPES:
        category = "ambiguous"

    body = "\n".join(
        line
        for line in lines
        if line != title_line and not line.casefold().startswith("type:")
    ).strip()
    return Issue(
        issue_id=path.stem,
        title=title_line[2:].strip(),
        category=category,
        body=body,
        path=path,
    )


def load_issues(issue_directory: Path) -> list[Issue]:
    if not issue_directory.is_dir():
        raise ValueError(f"Issue directory does not exist: {issue_directory}")

    paths = sorted(issue_directory.rglob("*.md"))
    if not paths:
        raise ValueError(f"No Markdown issues found in: {issue_directory}")
    return [parse_issue(path) for path in paths]


def inventory_repository(repository: Path) -> list[RepositoryFile]:
    if not repository.is_dir():
        raise ValueError(f"Repository directory does not exist: {repository}")

    files: list[RepositoryFile] = []
    paths = sorted(
        path
        for path in repository.rglob("*")
        if path.is_file()
        and not path.is_symlink()
        and not IGNORED_DIRECTORY_NAMES.intersection(path.relative_to(repository).parts)
    )

    for path in paths:
        relative_path = path.relative_to(repository).as_posix()
        if path.suffix == ".py":
            source = path.read_text(encoding="utf-8")
            try:
                tree = ast.parse(source, filename=relative_path)
            except SyntaxError as error:
                detail = f"line {error.lineno}: {error.msg}"
                files.append(
                    RepositoryFile(
                        path=relative_path,
                        kind="python",
                        syntax_error=detail,
                    )
                )
            else:
                files.append(
                    RepositoryFile(
                        path=relative_path,
                        kind="python",
                        symbols=tuple(_extract_symbols(tree.body)),
                    )
                )
        elif path.suffix.casefold() == ".md":
            files.append(RepositoryFile(path=relative_path, kind="markdown"))

    return files


def _tokens(value: str) -> set[str]:
    return {
        token
        for token in _WORD_PATTERN.findall(value.casefold())
        if len(token) > 1 and token not in _STOP_WORDS
    }


def _category_score(issue: Issue, repository_file: RepositoryFile) -> int:
    path = repository_file.path.casefold()
    if issue.category == "docs":
        return 5 if repository_file.kind == "markdown" else 0
    if issue.category == "test":
        return 5 if "test" in path else 0
    if issue.category == "bug":
        if repository_file.kind != "python":
            return 0
        return 3 if path.startswith(("src/", "app/")) else 1
    return 0


def rank_files(issue: Issue, files: list[RepositoryFile]) -> list[RepositoryFile]:
    if issue.category == "ambiguous":
        return []

    issue_terms = _tokens(issue.title)
    ranked: list[tuple[int, str, RepositoryFile]] = []
    for repository_file in files:
        base_score = _category_score(issue, repository_file)
        if base_score == 0:
            continue

        searchable = " ".join((repository_file.path, *repository_file.symbols))
        score = base_score + 2 * len(issue_terms & _tokens(searchable))
        ranked.append((score, repository_file.path, repository_file))

    ranked.sort(key=lambda item: (-item[0], item[1]))
    return [item[2] for item in ranked[:5]]


def create_report(repository: Path, issue_directory: Path) -> str:
    files = inventory_repository(repository)
    issues = load_issues(issue_directory)
    python_files = [file for file in files if file.kind == "python"]
    markdown_files = [file for file in files if file.kind == "markdown"]

    lines = [
        "# Repo Triage report",
        "",
        f"- Repository: `{repository.as_posix()}`",
        f"- Issues analyzed: {len(issues)}",
        f"- Python files: {len(python_files)}",
        f"- Markdown files: {len(markdown_files)}",
        "",
        "File ranking is a keyword-based hint, not a semantic code analysis.",
        "",
        "## Repository inventory",
        "",
    ]

    for repository_file in files:
        if repository_file.kind == "python":
            details = ", ".join(f"`{symbol}`" for symbol in repository_file.symbols)
            if repository_file.syntax_error:
                details = f"**Syntax error:** {repository_file.syntax_error}"
            elif not details:
                details = "no top-level classes or functions"
            lines.append(f"- `{repository_file.path}` — {details}")
        else:
            lines.append(f"- `{repository_file.path}` — Markdown")

    lines.extend(["", "## Issue triage", ""])
    for issue in issues:
        lines.extend(
            [
                f"### {issue.issue_id}: {issue.title}",
                "",
                f"- Type: `{issue.category}`",
                f"- Status: `{'needs_input' if issue.category == 'ambiguous' else 'ready_for_planning'}`",
                f"- Source: `{issue.path.as_posix()}`",
                "",
                "Request details:",
                "",
                *[f"> {line}" if line else ">" for line in issue.body.splitlines()],
                "",
            ]
        )

        if issue.category == "ambiguous":
            lines.extend(
                [
                    (
                        "Do not infer scope or modify files. Ask the requester for measurable acceptance "
                        "criteria and the affected behavior."
                    ),
                    "",
                ]
            )
            continue

        candidates = rank_files(issue, files)
        lines.append("Context candidates:")
        if candidates:
            for candidate in candidates:
                lines.append(f"- `{candidate.path}`")
        else:
            lines.append("- No candidate files found for this category.")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"
