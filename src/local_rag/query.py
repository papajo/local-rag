"""Query pipeline — embed → vector search → rerank → results."""

from __future__ import annotations

import logging

from local_rag.config import get_settings
from local_rag.models import SearchResult
from local_rag.store import search as vector_search

logger = logging.getLogger(__name__)


def embed_query(text: str) -> list[float]:
    """Embed a single query string via SIE /v1/embeddings."""
    import httpx

    settings = get_settings()
    url = f"{settings.sie_base_url}/v1/embeddings"
    payload = {"model": settings.embed_model, "input": text}

    resp = httpx.post(url, json=payload, timeout=30.0)
    resp.raise_for_status()
    data = resp.json()

    return data["data"][0]["embedding"]


def rerank(query: str, results: list[SearchResult]) -> list[SearchResult]:
    """Rerank results using SIE cross-encoder reranker.

    Falls back to vector-score ordering when the reranker is unavailable
    or returns unusable data (e.g. negative logits for every result).
    """
    if not results:
        return results

    import httpx

    settings = get_settings()
    url = f"{settings.sie_base_url}/v1/rerank"
    documents = [r.text for r in results]

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
        logger.warning("Reranker unavailable (%s), falling back to vector scores", exc)
        return sorted(results, key=lambda x: x.vector_score, reverse=False)

    raw_items = data.get("results", [])
    if not raw_items:
        return sorted(results, key=lambda x: x.vector_score, reverse=False)

    # Map rerank results back to our SearchResult objects
    reranked: list[SearchResult] = []
    for r in raw_items:
        idx = r["index"]
        score = r["relevance_score"]
        if idx < len(results):
            original = results[idx]
            original.rerank_score = score
            reranked.append(original)

    # If the reranker returned fewer items than we sent (e.g. partial failure),
    # append any results that weren't covered
    covered = len(reranked)
    if covered < len(results):
        reranked.extend(results[covered:])

    return reranked


def query(text: str, top_k: int | None = None) -> list[SearchResult]:
    """Full query pipeline: embed → vector search → rerank → top-k results.

    Args:
        text: Natural language query.
        top_k: Number of final results to return. Defaults to config.

    Returns:
        List of SearchResult objects, sorted by relevance (best first).
    """
    settings = get_settings()
    k = top_k or settings.final_top_k

    # Step 1: Embed the query
    query_vec = embed_query(text)

    # Step 2: Vector search (get more candidates for reranking)
    candidates = vector_search(query_vec)

    if not candidates:
        return []

    # Step 3: Rerank
    reranked = rerank(text, candidates)

    # Step 4: Return top-k
    return reranked[:k]
