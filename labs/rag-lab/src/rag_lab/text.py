from __future__ import annotations

import re

_WORD_PATTERN = re.compile(r"[^\W_]+", re.UNICODE)
_SENTENCE_PATTERN = re.compile(r"(?<=[.!?])\s+")
_STOP_WORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "but",
        "by",
        "can",
        "do",
        "does",
        "for",
        "from",
        "how",
        "if",
        "in",
        "into",
        "is",
        "it",
        "its",
        "of",
        "on",
        "or",
        "should",
        "so",
        "than",
        "that",
        "the",
        "then",
        "there",
        "these",
        "this",
        "to",
        "was",
        "what",
        "when",
        "which",
        "who",
        "why",
        "will",
        "with",
        "you",
    }
)


def words(value: str) -> tuple[str, ...]:
    return tuple(
        token
        for token in _WORD_PATTERN.findall(value.casefold())
        if len(token) > 1 and token not in _STOP_WORDS
    )


def terms(value: str) -> frozenset[str]:
    return frozenset(words(value))


def sentences(value: str) -> tuple[str, ...]:
    parts = _SENTENCE_PATTERN.split(" ".join(value.split()))
    return tuple(part for part in parts if len(words(part)) >= 3)