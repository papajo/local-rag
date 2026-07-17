from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from local_rag.config import get_settings
from local_rag.extract import extract_entities
from local_rag.models import ExtractedEntity, MemoryEntry
from local_rag.store import store_memory, search_memories, list_memories, count_memories

logger = logging.getLogger(__name__)


def _embed(text: str) -> list[float]:
    """Embed a single text via SIE /v1/embeddings."""
    import httpx

    settings = get_settings()
    url = f"{settings.sie_base_url}/v1/embeddings"
    payload = {"model": settings.embed_model, "input": text}

    resp = httpx.post(url, json=payload, timeout=30.0)
    resp.raise_for_status()
    return resp.json()["data"][0]["embedding"]


def _rerank(query: str, entries: list[MemoryEntry]) -> list[MemoryEntry]:
    """Rerank memory entries using SIE cross-encoder."""
    if not entries:
        return entries

    import httpx

    settings = get_settings()
    url = f"{settings.sie_base_url}/v1/rerank"
    documents = [e.text for e in entries]

    payload = {
        "model": settings.rerank_model,
        "query": query,
        "documents": documents,
    }

    try:
        resp = httpx.post(url, json=payload, timeout=60.0)
        resp.raise_for_status()
        data = resp.json()
    except (httpx.HTTPError, httpx.TimeoutException, ValueError) as exc:
        logger.warning("Reranker unavailable (%s), returning unranked", exc)
        return entries

    raw_items = data.get("results", [])
    if not raw_items:
        return entries

    reranked: list[MemoryEntry] = []
    for r in raw_items:
        idx = r["index"]
        if idx < len(entries):
            reranked.append(entries[idx])

    return reranked


def record_memory(
    text: str,
    source: str = "cli",
    tags: list[str] | None = None,
    extract: bool = True,
) -> str:
    """Embed, extract entities from, and store a single memory entry.

    Args:
        text: The memory content to store.
        source: Where this memory came from (``"cli"``, ``"file"``, etc.).
        tags: Optional list of tags to attach.
        extract: Whether to run entity extraction on the text.

    Returns:
        The memory ID string.
    """
    embedding = _embed(text)

    entities: list[ExtractedEntity] = []
    if extract:
        try:
            results = extract_entities([text])
            if results:
                entities = results[0].entities
        except Exception as exc:
            logger.warning("Entity extraction failed for memory (%s)", exc)

    memory = MemoryEntry(
        id=str(uuid.uuid4()),
        text=text,
        source=source,
        timestamp=datetime.now(timezone.utc).isoformat(),
        tags=tags or [],
        entities=entities,
        embedding=embedding,
    )

    stored_id = store_memory(memory)
    logger.info(
        "Stored memory %s (source=%s, entities=%d, tags=%s)",
        stored_id,
        source,
        len(entities),
        tags or [],
    )
    return stored_id


def query_memories(
    query_text: str,
    top_k: int = 5,
) -> list[MemoryEntry]:
    """Query the memory store: embed query, vector search, rerank.

    Args:
        query_text: Natural language query.
        top_k: Number of results to return.

    Returns:
        List of MemoryEntry objects, best match first.
    """
    settings = get_settings()
    vec_k = max(top_k * 4, settings.vector_top_k)

    query_vec = _embed(query_text)
    candidates = search_memories(query_vec, top_k=vec_k)

    if not candidates:
        return []

    reranked = _rerank(query_text, candidates)
    return reranked[:top_k]


def recent_memories(limit: int = 20) -> list[MemoryEntry]:
    """Return most recent memories."""
    return list_memories(limit=limit)


def memory_count() -> int:
    """Return total stored memories."""
    return count_memories()
