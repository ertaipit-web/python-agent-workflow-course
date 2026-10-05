from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

_HEADING_PATTERN = re.compile(r"^#{1,6}\s+(?P<title>.+?)\s*$")
_IGNORED_DIRECTORY_NAMES = frozenset(
    {".git", ".pytest_cache", ".venv", "__pycache__", "node_modules", "venv"}
)


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    source: str
    section: str
    position: int
    text: str


@dataclass(frozen=True)
class Section:
    heading: str
    body: str


def split_sections(markdown: str) -> tuple[Section, ...]:
    sections: list[Section] = []
    heading = "(intro)"
    buffer: list[str] = []
    for line in markdown.splitlines():
        match = _HEADING_PATTERN.match(line)
        if match is None:
            buffer.append(line)
            continue
        sections.append(Section(heading, "\n".join(buffer).strip()))
        heading = match.group("title")
        buffer = []
    sections.append(Section(heading, "\n".join(buffer).strip()))
    return tuple(section for section in sections if section.body)


def chunk_markdown(
    markdown: str,
    *,
    source: str,
    max_words: int = 90,
    overlap_words: int = 20,
) -> tuple[Chunk, ...]:
    if max_words < 1:
        raise ValueError("max_words must be positive")
    if not 0 <= overlap_words < max_words:
        raise ValueError("overlap_words must be smaller than max_words")

    step = max_words - overlap_words
    minimum = max(3, max_words // 5)
    chunks: list[Chunk] = []
    position = 0
    for section in split_sections(markdown):
        section_words = section.body.split()
        for index, start in enumerate(range(0, len(section_words), step)):
            window = section_words[start : start + max_words]
            if index > 0 and len(window) < minimum:
                break
            if not window:
                break
            position += 1
            chunks.append(
                Chunk(
                    chunk_id=f"{source}#{position}",
                    source=source,
                    section=section.heading,
                    position=position,
                    text=" ".join(window),
                )
            )
            if start + max_words >= len(section_words):
                break
    return tuple(chunks)


def ingest_directory(directory: Path) -> tuple[Chunk, ...]:
    if not directory.is_dir():
        raise ValueError(f"Corpus directory does not exist: {directory}")

    paths = sorted(
        path
        for path in directory.rglob("*.md")
        if path.is_file()
        and not _IGNORED_DIRECTORY_NAMES.intersection(path.relative_to(directory).parts)
    )
    if not paths:
        raise ValueError(f"No Markdown documents found in: {directory}")

    chunks: list[Chunk] = []
    for path in paths:
        chunks.extend(chunk_markdown(path.read_text(encoding="utf-8"), source=path.name))
    return tuple(chunks)