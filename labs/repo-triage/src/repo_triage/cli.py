from __future__ import annotations

import argparse
import sys
from pathlib import Path

from repo_triage.analysis import create_report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create a local triage report from Markdown issues and a Python repository."
    )
    parser.add_argument("--repo", type=Path, required=True, help="Python repository to inspect")
    parser.add_argument("--issues", type=Path, required=True, help="Directory containing Markdown issues")
    parser.add_argument(
        "--output",
        type=Path,
        help="Write the report to this file instead of stdout",
    )
    return parser


def main() -> int:
    parser = build_parser()
    arguments = parser.parse_args()
    try:
        report = create_report(arguments.repo, arguments.issues)
        if arguments.output is None:
            sys.stdout.write(report)
        else:
            arguments.output.write_text(report, encoding="utf-8")
    except (OSError, ValueError) as error:
        parser.exit(2, f"{parser.prog}: error: {error}\n")
    return 0
