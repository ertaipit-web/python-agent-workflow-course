from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from rag_lab.chunking import Chunk, ingest_directory
from rag_lab.embedding import HashingEmbedder, cosine_similarity

DEFAULT_MIN_SCORE = 0.08


@dataclass(frozen=True)
class RetrievedChunk:
    chunk: Chunk
    score: float
    snippet: str


def make_snippet(chunk: Chunk, *, word_limit: int = 40) -> str:
    if word_limit < 1:
        raise ValueError("word_limit must be positive")
    tokens = chunk.text.split()
    if len(tokens) <= word_limit:
        return chunk.text
    return " ".join(tokens[:word_limit]) + "..."


class VectorStore:
    def __init__(
        self,
        chunks: Sequence[Chunk],
        embedder: HashingEmbedder | None = None,
    ) -> None:
        if not chunks:
            raise ValueError("A vector store needs at least one chunk")
        counts = Counter(chunk.chunk_id for chunk in chunks)
        duplicates = sorted(chunk_id for chunk_id, count in counts.items() if count > 1)
        if duplicates:
            raise ValueError(f"Duplicate chunk identifiers: {', '.join(duplicates)}")

        self._embedder = embedder if embedder is not None else HashingEmbedder()
        self._chunks = tuple(chunks)
        self._vectors = self._embedder.embed_many([chunk.text for chunk in self._chunks])
        self._by_id = {chunk.chunk_id: chunk for chunk in self._chunks}

    @property
    def chunks(self) -> tuple[Chunk, ...]:
        return self._chunks

    @property
    def embedder_name(self) -> str:
        return self._embedder.name

    @property
    def sources(self) -> tuple[str, ...]:
        return tuple(sorted({chunk.source for chunk in self._chunks}))

    @property
    def total_characters(self) -> int:
        return sum(len(chunk.text) for chunk in self._chunks)

    def __len__(self) -> int:
        return len(self._chunks)

    def chunk(self, chunk_id: str) -> Chunk:
        try:
            return self._by_id[chunk_id]
        except KeyError:
            raise LookupError(f"Unknown chunk identifier: {chunk_id}") from None

    def search(
        self,
        query: str,
        *,
        limit: int = 3,
        min_score: float = DEFAULT_MIN_SCORE,
    ) -> tuple[RetrievedChunk, ...]:
        if limit < 1:
            raise ValueError("limit must be positive")
        if not 0.0 <= min_score <= 1.0:
            raise ValueError("min_score must be between 0.0 and 1.0")

        query_vector = self._embedder.embed(query)
        ranked: list[RetrievedChunk] = []
        for chunk, vector in zip(self._chunks, self._vectors, strict=True):
            score = cosine_similarity(query_vector, vector)
            if score < min_score:
                continue
            ranked.append(RetrievedChunk(chunk=chunk, score=score, snippet=make_snippet(chunk)))

        ranked.sort(key=lambda item: (-item.score, item.chunk.chunk_id))
        return tuple(ranked[:limit])


def build_index(directory: Path, embedder: HashingEmbedder | None = None) -> VectorStore:
    return VectorStore(ingest_directory(directory), embedder)