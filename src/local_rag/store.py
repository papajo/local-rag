"""LanceDB vector store — insert, search, stats."""

from __future__ import annotations

import hashlib
import json
import warnings
from pathlib import Path

import lancedb
import pyarrow as pa

# Suppress LanceDB deprecation warnings for the `_distance` column.
# The column is still available but triggers a DeprecationWarning on every
# search().to_list() call.  Known issue, harmless — we suppress it at the
# module level so it doesn't flood stdout during incremental ingest.
warnings.filterwarnings("ignore", category=DeprecationWarning, module="lancedb")

from local_rag.config import DEFAULT_DATA_DIR, get_settings
from local_rag.config import SPOTLIGHT_EMBED_DIM, SPOTLIGHT_TABLE
from local_rag.models import DigestItem, DocumentChunk, ExtractedEntity, MemoryEntry, SearchResult, SpotlightEntry

# ── Generation counter (LanceDB / ingest_state desync detection) ──────────────
_GENERATION_FILE = "rag_generation"


def _generation_path() -> Path:
    return DEFAULT_DATA_DIR / _GENERATION_FILE


def read_generation() -> int:
    settings = get_settings()
    if not (settings.lancedb_dir / "chunks.lance").exists():
        return 0
    gen_file = _generation_path()
    if gen_file.exists():
        try:
            return int(gen_file.read_text().strip())
        except (ValueError, OSError):
            pass
    return 0


def write_generation(gen: int) -> None:
    _generation_path().write_text(str(gen))


def increment_generation() -> int:
    current = read_generation()
    new_gen = current + 1
    write_generation(new_gen)
    return new_gen


# ── Embedding dimension ───────────────────────────────────────────────────────
EMBEDDING_DIM = 1024  # bge-m3 outputs 1024-dim vectors


def _embedding_type() -> pa.DataType:
    """Return a fixed-size list type for 1024-dim float32 embeddings."""
    return pa.list_(pa.float32(), EMBEDDING_DIM)


def _chunks_schema() -> pa.Schema:
    """PyArrow schema for the chunks table."""
    return pa.schema([
        pa.field("id", pa.string()),
        pa.field("text", pa.string()),
        pa.field("source", pa.string()),
        pa.field("file_path", pa.string()),
        pa.field("chunk_index", pa.int32()),
        pa.field("total_chunks", pa.int32()),
        pa.field("file_hash", pa.string()),
        pa.field("embedding", _embedding_type()),
        pa.field("source_refs", pa.string()),  # JSON: [{"source": ..., "file_path": ..., "chunk_ids": [...]}]
        pa.field("metadata", pa.string()),  # JSON: {"type": "python", "name": ..., ...}
    ])


def _get_db() -> lancedb.DBConnection:
    settings = get_settings()
    settings.lancedb_dir.mkdir(parents=True, exist_ok=True)
    return lancedb.connect(str(settings.lancedb_dir))


def _get_table(db: lancedb.DBConnection, create: bool = True):
    """Return the chunks table, creating/upgrading it if needed."""
    tbl_name = "chunks"
    if tbl_name not in db.table_names():
        if not create:
            return None
        tbl = db.create_table(tbl_name, schema=_chunks_schema())
        increment_generation()  # new table → new generation (flags ingest_state reset)
        return tbl

    tbl = db.open_table(tbl_name)
    # Schema migration: check for columns added in newer versions
    existing_names = {f.name for f in tbl.schema}
    required_names = {f.name for f in _chunks_schema()}
    missing = required_names - existing_names
    if missing:
        required_types = {f.name: f.type for f in _chunks_schema()}
        for col_name in sorted(missing):
            tbl.add_columns({pa.field(col_name, required_types[col_name])})
    return tbl


def chunk_id(file_hash: str, chunk_index: int) -> str:
    """Deterministic unique ID for a chunk."""
    raw = f"{file_hash}:{chunk_index}"
    return hashlib.sha256(raw.encode()).hexdigest()[:24]


def store_chunks(chunks: list[DocumentChunk]) -> int:
    """Insert chunks into LanceDB. Returns count stored."""
    db = _get_db()
    tbl = _get_table(db)

    records = []
    for c in chunks:
        records.append({
            "id": c.id or chunk_id(c.file_hash, c.chunk_index),
            "text": c.text,
            "source": c.source,
            "file_path": c.file_path,
            "chunk_index": c.chunk_index,
            "total_chunks": c.total_chunks,
            "file_hash": c.file_hash,
            "embedding": c.embedding,
            "source_refs": json.dumps(c.source_refs) if c.source_refs else "[]",
            "metadata": json.dumps(c.metadata) if c.metadata else "{}",
        })

    tbl.add(records)
    return len(records)


def search(query_embedding: list[float], top_k: int | None = None) -> list[SearchResult]:
    """Vector search returning top_k results."""
    settings = get_settings()
    k = top_k or settings.vector_top_k
    db = _get_db()
    tbl = _get_table(db, create=False)
    if tbl is None:
        return []

    results = (
        tbl.search(query_embedding)
        .metric("cosine")
        .limit(k)
        .select(["text", "source", "file_path", "chunk_index", "source_refs", "metadata", "_distance"])
        .to_list()
    )

    out: list[SearchResult] = []
    for r in results:
        raw_refs = r.get("source_refs", "[]")
        parsed_refs: list[dict] = json.loads(raw_refs) if isinstance(raw_refs, str) else raw_refs or []
        raw_meta = r.get("metadata", "{}")
        parsed_meta: dict = json.loads(raw_meta) if isinstance(raw_meta, str) else raw_meta or {}
        out.append(
            SearchResult(
                text=r.get("text", ""),
                source=r.get("source", ""),
                file_path=r.get("file_path", ""),
                chunk_index=r.get("chunk_index", 0),
                vector_score=r.get("_distance", 0.0),
                source_refs=parsed_refs,
                metadata=parsed_meta,
            )
        )
    return out


def get_stats() -> dict:
    """Return ingestion statistics."""
    db = _get_db()
    tbl = _get_table(db, create=False)
    if tbl is None:
        return {"total_chunks": 0, "total_files": 0, "sources": []}

    count = tbl.count_rows()
    # Get unique file sources
    # LanceDB supports SQL queries
    unique_sources = (
        tbl.search()
        .select(["source"])
        .limit(10_000)
        .to_list()
    )
    seen = set()
    sources = []
    for r in unique_sources:
        s = r.get("source", "")
        if s and s not in seen:
            seen.add(s)
            sources.append(s)

    return {
        "total_chunks": count,
        "total_files": len(sources),
        "sources": sorted(sources),
    }


def update_chunk_source_refs(chunk_id: str, new_ref: dict) -> None:
    """Append a source reference to an existing chunk's source_refs list."""
    db = _get_db()
    tbl = _get_table(db, create=False)
    if tbl is None:
        return

    rows = tbl.search().where(f"id = '{chunk_id}'").select(["id", "source_refs"]).limit(1).to_list()
    if not rows:
        return

    current = json.loads(rows[0].get("source_refs", "[]")) if rows[0].get("source_refs") else []
    # Avoid adding duplicate entries for the same file_path
    if not any(r.get("file_path") == new_ref.get("file_path") for r in current):
        current.append(new_ref)
    tbl.update(where=f"id = '{chunk_id}'", values={"source_refs": json.dumps(current)})


def find_similar_chunk(
    embedding: list[float], threshold: float, exclude_hash: str | None = None,
) -> dict | None:
    """Search for an existing chunk with cosine similarity above threshold.

    Returns the top match or None.
    """
    db = _get_db()
    tbl = _get_table(db, create=False)
    if tbl is None:
        return None

    results = (
        tbl.search(embedding)
        .metric("cosine")
        .limit(5)
        .select(["id", "source", "file_path", "file_hash", "text", "_distance"])
        .to_list()
    )

    for r in results:
        distance = r.get("_distance", 1.0)
        similarity = 1.0 - distance
        if similarity >= threshold:
            if exclude_hash and r.get("file_hash") == exclude_hash:
                continue
            return r
    return None


def delete_file(file_hash: str) -> int:
    """Remove all chunks for a given file hash. Returns count removed."""
    db = _get_db()
    tbl = _get_table(db, create=False)
    if tbl is None:
        return 0
    # LanceDB delete uses SQL syntax
    result = tbl.delete(f"file_hash = '{file_hash}'")
    return result  # number of rows deleted (LanceDB returns int)


# ── Memories table (Stage 3) ─────────────────────────────────────────────────


def _memories_schema() -> pa.Schema:
    return pa.schema([
        pa.field("id", pa.string()),
        pa.field("text", pa.string()),
        pa.field("source", pa.string()),
        pa.field("timestamp", pa.string()),
        pa.field("tags", pa.string()),
        pa.field("entities", pa.string()),
        pa.field("embedding", _embedding_type()),
    ])


def _get_memories_table(db: lancedb.DBConnection, create: bool = True):
    tbl_name = "memories"
    if tbl_name not in db.table_names():
        if not create:
            return None
        tbl = db.create_table(tbl_name, schema=_memories_schema())
        return tbl
    return db.open_table(tbl_name)


def store_memory(memory: MemoryEntry) -> str:
    """Insert a single memory into the memories table. Returns the memory ID."""
    db = _get_db()
    tbl = _get_memories_table(db)

    tag_json = json.dumps(memory.tags)
    ent_json = json.dumps([
        {"label": e.label, "text": e.text, "score": e.score}
        for e in memory.entities
    ])

    tbl.add([{
        "id": memory.id,
        "text": memory.text,
        "source": memory.source,
        "timestamp": memory.timestamp,
        "tags": tag_json,
        "entities": ent_json,
        "embedding": memory.embedding,
    }])
    return memory.id


def search_memories(
    query_embedding: list[float],
    top_k: int = 10,
) -> list[MemoryEntry]:
    db = _get_db()
    tbl = _get_memories_table(db, create=False)
    if tbl is None:
        return []

    results = (
        tbl.search(query_embedding)
        .metric("cosine")
        .limit(top_k)
        .select(["id", "text", "source", "timestamp", "tags", "entities", "_distance"])
        .to_list()
    )

    out: list[MemoryEntry] = []
    for r in results:
        raw_tags = r.get("tags", "[]")
        parsed_tags: list[str] = json.loads(raw_tags) if isinstance(raw_tags, str) else raw_tags or []
        raw_ents = r.get("entities", "[]")
        parsed_ents: list[dict] = json.loads(raw_ents) if isinstance(raw_ents, str) else raw_ents or []
        from local_rag.models import ExtractedEntity
        entities = [
            ExtractedEntity(label=e.get("label", ""), text=e.get("text", ""), score=e.get("score", 0.0))
            for e in parsed_ents
        ]
        out.append(MemoryEntry(
            id=r.get("id", ""),
            text=r.get("text", ""),
            source=r.get("source", ""),
            timestamp=r.get("timestamp", ""),
            tags=parsed_tags,
            entities=entities,
        ))
    return out


def list_memories(limit: int = 20) -> list[MemoryEntry]:
    db = _get_db()
    tbl = _get_memories_table(db, create=False)
    if tbl is None:
        return []

    # LanceDB doesn't support ORDER BY natively, so we fetch and sort
    results = (
        tbl.search()
        .select(["id", "text", "source", "timestamp", "tags", "entities"])
        .limit(max(limit, 1000))
        .to_list()
    )

    entries: list[MemoryEntry] = []
    for r in results:
        raw_tags = r.get("tags", "[]")
        parsed_tags: list[str] = json.loads(raw_tags) if isinstance(raw_tags, str) else raw_tags or []
        raw_ents = r.get("entities", "[]")
        parsed_ents: list[dict] = json.loads(raw_ents) if isinstance(raw_ents, str) else raw_ents or []
        from local_rag.models import ExtractedEntity
        entities = [
            ExtractedEntity(label=e.get("label", ""), text=e.get("text", ""), score=e.get("score", 0.0))
            for e in parsed_ents
        ]
        entries.append(MemoryEntry(
            id=r.get("id", ""),
            text=r.get("text", ""),
            source=r.get("source", ""),
            timestamp=r.get("timestamp", ""),
            tags=parsed_tags,
            entities=entities,
        ))

    entries.sort(key=lambda m: m.timestamp, reverse=True)
    return entries[:limit]


def count_memories() -> int:
    db = _get_db()
    tbl = _get_memories_table(db, create=False)
    if tbl is None:
        return 0
    return tbl.count_rows()


# ── Legacy list_indexed_files ────────────────────────────────────────────────


def list_indexed_files() -> list[dict]:
    """List unique indexed files with their hash and chunk count."""
    db = _get_db()
    tbl = _get_table(db, create=False)
    if tbl is None:
        return []

    # Use LanceDB SQL for aggregation
    try:
        result = tbl.create_empty_table("_tmp_stats")
        result.drop()
        # Fallback: scan and aggregate
        pass
    except Exception:
        pass

    rows = (
        tbl.search()
        .select(["file_path", "file_hash", "chunk_index", "total_chunks"])
        .limit(100_000)
        .to_list()
    )

    files: dict[str, dict] = {}
    for r in rows:
        fp = r.get("file_path", "")
        if fp not in files:
            files[fp] = {"file_path": fp, "file_hash": r.get("file_hash", ""), "chunks": r.get("total_chunks", 0)}
    return sorted(files.values(), key=lambda x: x["file_path"])


# ── Digest table (Stage 4 — Newsletter / Paper Digestor) ─────────────────────


def _digest_schema() -> pa.Schema:
    return pa.schema([
        pa.field("id", pa.string()),
        pa.field("text", pa.string()),
        pa.field("summary", pa.string()),
        pa.field("source_type", pa.string()),
        pa.field("source", pa.string()),
        pa.field("url", pa.string()),
        pa.field("topics", pa.string()),       # JSON list
        pa.field("importance", pa.string()),   # "high", "medium", "low"
        pa.field("entities", pa.string()),     # JSON list
        pa.field("tags", pa.string()),         # JSON list
        pa.field("timestamp", pa.string()),
        pa.field("embedding", _embedding_type()),
    ])


def _get_digest_table(db: lancedb.DBConnection, create: bool = True):
    tbl_name = "digest"
    if tbl_name not in db.table_names():
        if not create:
            return None
        tbl = db.create_table(tbl_name, schema=_digest_schema())
        return tbl
    return db.open_table(tbl_name)


def store_digest_item(item: DigestItem) -> str:
    """Insert a single digest item. Returns the item ID."""
    db = _get_db()
    tbl = _get_digest_table(db)

    tbl.add([{
        "id": item.id,
        "text": item.text,
        "summary": item.summary,
        "source_type": item.source_type,
        "source": item.source,
        "url": item.url,
        "topics": json.dumps(item.topics),
        "importance": item.importance,
        "entities": json.dumps([{"label": e.label, "text": e.text, "score": e.score} for e in item.entities]),
        "tags": json.dumps(item.tags),
        "timestamp": item.timestamp,
        "embedding": item.embedding,
    }])
    return item.id


def search_digest(
    query_embedding: list[float],
    top_k: int = 10,
    topic_filter: str | None = None,
    importance_filter: str | None = None,
) -> list[DigestItem]:
    """Semantic search over digest items."""
    db = _get_db()
    tbl = _get_digest_table(db, create=False)
    if tbl is None:
        return []

    results = (
        tbl.search(query_embedding)
        .metric("cosine")
        .limit(top_k)
        .select(["id", "text", "summary", "source_type", "source", "url", "topics", "importance", "entities", "tags", "timestamp", "_distance"])
        .to_list()
    )

    out: list[DigestItem] = []
    for r in results:
        topics = json.loads(r.get("topics", "[]")) if isinstance(r.get("topics"), str) else r.get("topics") or []
        if topic_filter and topic_filter not in topics:
            continue
        imp = r.get("importance", "routine")
        if importance_filter and imp != importance_filter:
            continue
        raw_ents = r.get("entities", "[]")
        parsed_ents: list[dict] = json.loads(raw_ents) if isinstance(raw_ents, str) else raw_ents or []
        entities = [
            ExtractedEntity(label=e.get("label", ""), text=e.get("text", ""), score=e.get("score", 0.0))
            for e in parsed_ents
        ]
        tags = json.loads(r.get("tags", "[]")) if isinstance(r.get("tags"), str) else r.get("tags") or []
        out.append(DigestItem(
            id=r.get("id", ""),
            text=r.get("text", ""),
            summary=r.get("summary", ""),
            source_type=r.get("source_type", ""),
            source=r.get("source", ""),
            url=r.get("url", ""),
            topics=topics,
            importance=imp,
            entities=entities,
            tags=tags,
            timestamp=r.get("timestamp", ""),
        ))
    return out


def list_digest_items(
    limit: int = 20,
    topic_filter: str | None = None,
    importance_filter: str | None = None,
    days: int | None = None,
) -> list[DigestItem]:
    """Return digest items, newest first, with optional filters."""
    from datetime import datetime, timezone, timedelta

    db = _get_db()
    tbl = _get_digest_table(db, create=False)
    if tbl is None:
        return []

    rows = (
        tbl.search()
        .select(["id", "text", "summary", "source_type", "source", "url", "topics", "importance", "entities", "tags", "timestamp"])
        .limit(max(limit, 1000))
        .to_list()
    )

    cutoff: datetime | None = None
    if days is not None:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    out: list[DigestItem] = []
    for r in rows:
        ts_str = r.get("timestamp", "")
        if cutoff is not None and ts_str:
            try:
                ts = datetime.fromisoformat(ts_str)
                if ts < cutoff:
                    continue
            except ValueError:
                pass
        topics = json.loads(r.get("topics", "[]")) if isinstance(r.get("topics"), str) else r.get("topics") or []
        if topic_filter and topic_filter not in topics:
            continue
        imp = r.get("importance", "routine")
        if importance_filter and imp != importance_filter:
            continue
        raw_ents = r.get("entities", "[]")
        parsed_ents: list[dict] = json.loads(raw_ents) if isinstance(raw_ents, str) else raw_ents or []
        from local_rag.models import ExtractedEntity
        entities = [
            ExtractedEntity(label=e.get("label", ""), text=e.get("text", ""), score=e.get("score", 0.0))
            for e in parsed_ents
        ]
        tags = json.loads(r.get("tags", "[]")) if isinstance(r.get("tags"), str) else r.get("tags") or []
        out.append(DigestItem(
            id=r.get("id", ""),
            text=r.get("text", ""),
            summary=r.get("summary", ""),
            source_type=r.get("source_type", ""),
            source=r.get("source", ""),
            url=r.get("url", ""),
            topics=topics,
            importance=imp,
            entities=entities,
            tags=tags,
            timestamp=ts_str,
        ))

    out.sort(key=lambda d: d.timestamp, reverse=True)
    return out[:limit]


def count_digest_items() -> int:
    db = _get_db()
    tbl = _get_digest_table(db, create=False)
    if tbl is None:
        return 0
    return tbl.count_rows()


# ── Spotlight table (Stage 5 — Smart Spotlight) ────────────────────────────


def _spotlight_embedding_type(dim: int) -> pa.DataType:
    """Return a fixed-size list type for dim-dimensional float32 embeddings."""
    return pa.list_(pa.float32(), dim)


def _spotlight_schema(dim: int = SPOTLIGHT_EMBED_DIM) -> pa.Schema:
    return pa.schema([
        pa.field("id", pa.string()),
        pa.field("text", pa.string()),
        pa.field("file_path", pa.string()),
        pa.field("source", pa.string()),
        pa.field("chunk_index", pa.int32()),
        pa.field("total_chunks", pa.int32()),
        pa.field("file_hash", pa.string()),
        pa.field("embedding", _spotlight_embedding_type(dim)),
    ])


def _get_spotlight_table(db: lancedb.DBConnection, create: bool = True):
    tbl_name = SPOTLIGHT_TABLE
    if tbl_name not in db.table_names():
        if not create:
            return None
        tbl = db.create_table(tbl_name, schema=_spotlight_schema())
        return tbl
    return db.open_table(tbl_name)


def store_spotlight_chunks(entries: list[SpotlightEntry]) -> int:
    """Insert spotlight entries. Returns count stored."""
    db = _get_db()
    tbl = _get_spotlight_table(db)
    records = [
        {
            "id": e.id,
            "text": e.text,
            "file_path": e.file_path,
            "source": e.source,
            "chunk_index": e.chunk_index,
            "total_chunks": e.total_chunks,
            "file_hash": e.file_hash,
            "embedding": e.embedding,
        }
        for e in entries
    ]
    tbl.add(records)
    return len(records)


def search_spotlight(
    query_embedding: list[float],
    top_k: int = 10,
) -> list[SearchResult]:
    """Vector search over the spotlight index."""
    db = _get_db()
    tbl = _get_spotlight_table(db, create=False)
    if tbl is None:
        return []

    results = (
        tbl.search(query_embedding)
        .metric("cosine")
        .limit(top_k)
        .select(["text", "source", "file_path", "chunk_index", "_distance"])
        .to_list()
    )

    out: list[SearchResult] = []
    for r in results:
        out.append(
            SearchResult(
                text=r.get("text", ""),
                source=r.get("source", ""),
                file_path=r.get("file_path", ""),
                chunk_index=r.get("chunk_index", 0),
                vector_score=r.get("_distance", 0.0),
            )
        )
    return out


def count_spotlight_entries() -> int:
    db = _get_db()
    tbl = _get_spotlight_table(db, create=False)
    if tbl is None:
        return 0
    return tbl.count_rows()


def delete_spotlight_file(file_hash: str) -> int:
    """Remove all spotlight entries for a given file hash. Returns count removed."""
    db = _get_db()
    tbl = _get_spotlight_table(db, create=False)
    if tbl is None:
        return 0
    return tbl.delete(f"file_hash = '{file_hash}'")


def get_digest_topics() -> list[str]:
    """Return all unique topic labels found across digest items."""
    db = _get_db()
    tbl = _get_digest_table(db, create=False)
    if tbl is None:
        return []

    rows = (
        tbl.search()
        .select(["topics"])
        .limit(10_000)
        .to_list()
    )
    seen: set[str] = set()
    for r in rows:
        topics = json.loads(r.get("topics", "[]")) if isinstance(r.get("topics"), str) else r.get("topics") or []
        for t in topics:
            seen.add(t)
    return sorted(seen)
