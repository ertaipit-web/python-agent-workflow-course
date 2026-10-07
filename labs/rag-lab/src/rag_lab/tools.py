from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from rag_lab.chunking import Chunk
from rag_lab.store import DEFAULT_MIN_SCORE, RetrievedChunk, VectorStore

SEARCH_TOOL_NAME = "search_documents"
READ_CHUNK_TOOL_NAME = "read_chunk"


class ToolError(ValueError):
    pass


class UnknownToolError(ToolError):
    pass


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    arguments: Mapping[str, str]
    required_arguments: tuple[str, ...]
    integer_limits: Mapping[str, tuple[int, int]] = field(default_factory=dict)


@dataclass(frozen=True)
class ToolResult:
    name: str
    payload: Mapping[str, object]
    returned_characters: int
    chunks: tuple[Chunk, ...] = ()
    hits: tuple[RetrievedChunk, ...] = ()


SEARCH_TOOL = ToolSpec(
    name=SEARCH_TOOL_NAME,
    description=(
        "Find the document chunks that are most relevant to one question. "
        "Returns references, scores and short snippets, never the whole corpus."
    ),
    arguments={"query": "the user question as a string", "limit": "how many chunks to return"},
    required_arguments=("query",),
    integer_limits={"limit": (1, 8)},
)

READ_CHUNK_TOOL = ToolSpec(
    name=READ_CHUNK_TOOL_NAME,
    description=(
        "Load the full text of a single chunk that search_documents returned. "
        "Use it only for the chunks that are actually needed for the current question."
    ),
    arguments={"chunk_id": "a chunk identifier returned by search_documents"},
    required_arguments=("chunk_id",),
)


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
        if limits is None:
            if not isinstance(value, str):
                raise ToolError(f"{spec.name}: argument '{name}' must be a string")
            if not value.strip():
                raise ToolError(f"{spec.name}: argument '{name}' must not be empty")
        else:
            if isinstance(value, bool) or not isinstance(value, int):
                raise ToolError(f"{spec.name}: argument '{name}' must be an integer")
            minimum, maximum = limits
            if not minimum <= value <= maximum:
                raise ToolError(
                    f"{spec.name}: argument '{name}' must be between {minimum} and {maximum}"
                )
        validated[name] = value
    return validated


class RetrievalTools:
    def __init__(
        self,
        store: VectorStore,
        *,
        top_k: int = 3,
        min_score: float = DEFAULT_MIN_SCORE,
    ) -> None:
        if top_k < 1:
            raise ValueError("top_k must be positive")
        self._store = store
        self._top_k = top_k
        self._min_score = min_score

    @property
    def store(self) -> VectorStore:
        return self._store

    @property
    def top_k(self) -> int:
        return self._top_k

    @property
    def specs(self) -> tuple[ToolSpec, ...]:
        return (SEARCH_TOOL, READ_CHUNK_TOOL)

    def spec(self, name: str) -> ToolSpec:
        for spec in self.specs:
            if spec.name == name:
                return spec
        raise UnknownToolError(f"Unknown tool: {name}")

    def chunk(self, chunk_id: str) -> Chunk:
        return self._store.chunk(chunk_id)

    def call(self, name: str, arguments: Mapping[str, object]) -> ToolResult:
        spec = self.spec(name)
        validated = validate_arguments(spec, arguments)

        if spec.name == SEARCH_TOOL_NAME:
            return self._search(spec.name, validated)
        return self._read_chunk(spec.name, validated)

    def _search(self, name: str, validated: Mapping[str, object]) -> ToolResult:
        query = validated["query"]
        limit = validated.get("limit", self._top_k)
        if not isinstance(query, str) or not isinstance(limit, int):
            raise ToolError(f"{name}: validated arguments have invalid types")
        hits = self._store.search(
            query,
            limit=limit,
            min_score=self._min_score,
        )
        serialized = [
            {
                "chunk_id": hit.chunk.chunk_id,
                "source": hit.chunk.source,
                "section": hit.chunk.section,
                "score": round(hit.score, 4),
                "snippet": hit.snippet,
            }
            for hit in hits
        ]
        return ToolResult(
            name=name,
            payload={"tool": name, "query": query, "hits": serialized},
            returned_characters=sum(len(hit["snippet"]) for hit in serialized),
            hits=hits,
        )

    def _read_chunk(self, name: str, validated: Mapping[str, object]) -> ToolResult:
        chunk_id = validated["chunk_id"]
        if not isinstance(chunk_id, str):
            raise ToolError(f"{name}: validated chunk_id has an invalid type")
        chunk = self._store.chunk(chunk_id)
        return ToolResult(
            name=name,
            payload={
                "tool": name,
                "chunk_id": chunk.chunk_id,
                "source": chunk.source,
                "section": chunk.section,
                "text": chunk.text,
            },
            returned_characters=len(chunk.text),
            chunks=(chunk,),
        )