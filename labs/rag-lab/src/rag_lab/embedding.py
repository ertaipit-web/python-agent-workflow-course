from __future__ import annotations

import math
import zlib
from collections.abc import Sequence

from rag_lab.text import words

DEFAULT_DIMENSIONS = 256


class HashingEmbedder:
    name = "hashing-v1"

    def __init__(self, dimensions: int = DEFAULT_DIMENSIONS) -> None:
        if dimensions < 8:
            raise ValueError("dimensions must be at least 8")
        self._dimensions = dimensions

    @property
    def dimensions(self) -> int:
        return self._dimensions

    def embed(self, text: str) -> tuple[float, ...]:
        buckets: dict[int, float] = {}
        for token in words(text):
            index = zlib.crc32(token.encode("utf-8")) % self._dimensions
            buckets[index] = buckets.get(index, 0.0) + 1.0

        vector = [0.0] * self._dimensions
        for index, count in buckets.items():
            vector[index] += 1.0 + math.log(count)

        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0.0:
            return tuple(vector)
        return tuple(value / norm for value in vector)

    def embed_many(self, texts: Sequence[str]) -> tuple[tuple[float, ...], ...]:
        return tuple(self.embed(text) for text in texts)


def cosine_similarity(left: Sequence[float], right: Sequence[float]) -> float:
    if len(left) != len(right):
        raise ValueError("vectors must have the same number of dimensions")
    return sum(a * b for a, b in zip(left, right, strict=True))