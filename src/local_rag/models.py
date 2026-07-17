"""Data models for chunks and query results."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ExtractedEntity:
    """A single extracted entity (person, org, technology, etc.)."""

    label: str
    text: str
    score: float


@dataclass
class DocumentChunk:
    """A single chunk of text from a document."""

    id: str  # unique hash-based id
    text: str
    source: str  # filename (basename)
    file_path: str  # full path
    chunk_index: int
    total_chunks: int
    file_hash: str  # sha256 of original file (for idempotency)
    embedding: list[float] | None = None
    source_refs: list[dict] | None = None  # [{"source": ..., "file_path": ..., "chunk_ids": [...]}]
    metadata: dict | None = None  # {"type": "python", "name": ..., "version": ..., "dependencies": [...]}


@dataclass
class MemoryEntry:
    """A single memory with timestamp and extracted entities."""

    id: str
    text: str
    source: str  # "cli", "file", "conversation", etc.
    timestamp: str  # ISO 8601
    tags: list[str] = field(default_factory=list)
    entities: list[ExtractedEntity] = field(default_factory=list)
    embedding: list[float] | None = None


@dataclass
class SearchResult:
    """A single retrieval result with score and source info."""

    text: str
    source: str
    file_path: str
    chunk_index: int
    vector_score: float = 0.0
    rerank_score: float = 0.0
    entities: list[ExtractedEntity] = field(default_factory=list)
    source_refs: list[dict] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    @property
    def score(self) -> float:
        """Use rerank score if positive (better-than-random), else vector score."""
        if self.rerank_score > 0.0:
            return self.rerank_score
        return self.vector_score


@dataclass
class SpotlightEntry:
    """A single chunk indexed by the lightweight background spotlight indexer."""

    id: str
    text: str
    file_path: str
    source: str  # basename
    chunk_index: int
    total_chunks: int
    file_hash: str  # sha256 for idempotency
    embedding: list[float] | None = None


@dataclass
class DigestItem:
    """A single item in the newsletter / paper digest."""

    id: str  # UUID
    text: str  # Original article / snippet text
    summary: str  # Summarized version
    source_type: str  # "newsletter", "paper", "article", "manual"
    source: str  # Newsletter name, URL label, etc.
    url: str  # Source URL (can be empty)
    topics: list[str] = field(default_factory=list)  # e.g. ["ml", "infrastructure"]
    importance: str = "routine"  # "high", "medium", "low"
    entities: list[ExtractedEntity] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    timestamp: str = ""  # ISO 8601
    embedding: list[float] | None = None
