"""Smart Spotlight — lightweight background indexer for always-on semantic search.

Uses a tiny embedding model (all-MiniLM-L6-v2, 384-dim) to continuously index
your home directory.  Search is fast, low-memory, and optionally re-ranked with
the cross-encoder for higher precision on top results.
"""

from __future__ import annotations

import hashlib
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

import httpx
import tiktoken

from local_rag.config import get_settings
from local_rag.models import SearchResult, SpotlightEntry
from local_rag.store import (
    count_spotlight_entries,
    delete_spotlight_file,
    search_spotlight,
    store_spotlight_chunks,
)

# ── Tokeniser for chunking ─────────────────────────────────────────────────
_CHUNK_ENCODING = "cl100k_base"

# ── Helpers ────────────────────────────────────────────────────────────────


def _file_hash(path: Path) -> str:
    """SHA-256 of file contents."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(8192)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _should_skip(path: Path) -> str | None:
    """Return a reason string if *path* should be skipped, else ``None``."""
    settings = get_settings()

    # Directories
    if path.is_dir():
        name = path.name
        if name.startswith(".") and name != ".":
            return "hidden-dir"
        if name in settings.code_skip_dirs or name in {
            "node_modules", ".git", "__pycache__", ".venv", "venv",
            ".next", ".turbo", "build", "dist", "target",
            ".cache", "Library", ".Trash",
        }:
            return "skip-dir"
        return None

    # Files
    if path.name.startswith("."):
        return "hidden-file"

    ext = path.suffix.lower()
    supported = {
        ".pdf", ".md", ".txt", ".docx",
        ".py", ".pyi", ".rs", ".ts", ".tsx", ".js", ".go", ".java",
        ".yaml", ".yml", ".toml", ".json", ".sql",
        ".c", ".cpp", ".h", ".hpp", ".swift", ".kt", ".rb", ".php",
        ".html", ".css", ".scss", ".less",
    }
    if ext not in supported:
        return "unsupported-ext"

    # Size limit: skip files larger than 5 MB (spotlight is meant to be fast)
    max_bytes = 5 * 1024 * 1024
    try:
        if path.stat().st_size > max_bytes:
            return "too-large"
    except OSError:
        return "unreadable"

    return None


def _read_file(path: Path) -> str | None:
    """Read text content from *path*.  Returns ``None`` on failure."""
    ext = path.suffix.lower()
    try:
        if ext == ".pdf":
            # Use the existing ingest helper
            from local_rag.ingest import read_single_file
            content, _ = read_single_file(path)
            return content
        if ext == ".docx":
            from local_rag.ingest import read_single_file
            content, _ = read_single_file(path)
            return content
        # Plain text / code
        return path.read_text("utf-8", errors="replace")
    except Exception:
        return None


def _chunk_text(text: str, max_tokens: int = 384, overlap: int = 32) -> list[str]:
    """Split *text* into token-bounded chunks with overlap."""
    enc = tiktoken.get_encoding(_CHUNK_ENCODING)
    tokens = enc.encode(text)
    if not tokens:
        return []

    chunks: list[str] = []
    start = 0
    while start < len(tokens):
        end = min(start + max_tokens, len(tokens))
        chunk_tokens = tokens[start:end]
        chunks.append(enc.decode(chunk_tokens))
        start += max_tokens - overlap
    return chunks


def _embed(texts: list[str], model: str | None = None) -> list[list[float]]:
    """Embed a batch of texts via the SIE server."""
    settings = get_settings()
    url = f"{settings.sie_base_url}/v1/embeddings"
    payload = {
        "model": model or settings.light_embed_model,
        "input": texts,
    }
    try:
        resp = httpx.post(url, json=payload, timeout=120.0)
        resp.raise_for_status()
        data = resp.json()
        return [item["embedding"] for item in data["data"]]
    except Exception as exc:
        logger.warning("Embedding failed: %s", exc)
        return []


def _get_existing_hashes() -> set[str]:
    """Return the set of file hashes already in the spotlight table."""
    from local_rag.store import _get_db, _get_spotlight_table

    db = _get_db()
    tbl = _get_spotlight_table(db, create=False)
    if tbl is None:
        return set()
    rows = tbl.search().select(["file_hash"]).limit(500_000).to_list()
    return {r.get("file_hash", "") for r in rows if r.get("file_hash")}


# ── Public API ─────────────────────────────────────────────────────────────


def init_index(paths: list[Path] | None = None) -> dict:
    """Walk paths, chunk, embed with the light model, and store.

    Args:
        paths: Directories/files to scan.  Defaults to
               ``SPOTLIGHT_SCAN_DIRS`` from config.

    Returns:
        Stats dict with keys ``chunks``, ``new_files``, ``skipped_files``,
        ``errors``.
    """
    settings = get_settings()
    scan_paths = paths or settings.spotlight_scan_dirs

    stats: dict = {"chunks": 0, "new_files": 0, "skipped_files": 0, "errors": 0}

    # Gather all eligible files
    all_files: list[Path] = []
    for sp in scan_paths:
        sp = Path(sp).expanduser().resolve()
        if not sp.exists():
            continue
        if sp.is_file():
            reason = _should_skip(sp)
            if reason is None:
                all_files.append(sp)
            continue
        # Walk directory (max depth 8 for performance)
        try:
            for root, dirs, names in os.walk(sp):
                # Prune skip dirs in-place
                dirs[:] = [d for d in dirs if _should_skip(Path(root) / d) is None]
                depth = root.replace(str(sp), "").count(os.sep)
                if depth > 8:
                    dirs.clear()
                    continue
                for name in names:
                    fp = Path(root) / name
                    if _should_skip(fp) is None:
                        all_files.append(fp)
        except Exception as exc:
            logger.warning("init_index: walk error: %s", exc)
            stats["errors"] += 1

    # Check existing hashes for idempotency
    existing_hashes = _get_existing_hashes()

    for fp in all_files:
        try:
            fhash = _file_hash(fp)
            if fhash in existing_hashes:
                stats["skipped_files"] += 1
                continue

            text = _read_file(fp)
            if text is None or not text.strip():
                stats["skipped_files"] += 1
                continue

            chunks = _chunk_text(text)
            if not chunks:
                stats["skipped_files"] += 1
                continue

            embeddings = _embed(chunks)
            if not embeddings or len(embeddings) != len(chunks):
                logger.warning("init_index: embedding failed for %s (SIE running?)", fp)
                stats["errors"] += 1
                continue

            total = len(chunks)
            entries: list[SpotlightEntry] = []
            for i, (chunk_text, emb) in enumerate(zip(chunks, embeddings)):
                raw = f"{fhash}:{i}"
                cid = hashlib.sha256(raw.encode()).hexdigest()[:24]
                entries.append(
                    SpotlightEntry(
                        id=cid,
                        text=chunk_text,
                        file_path=str(fp),
                        source=fp.name,
                        chunk_index=i,
                        total_chunks=total,
                        file_hash=fhash,
                        embedding=emb,
                    )
                )

            # Remove stale entries for this file before inserting
            delete_spotlight_file(fhash)
            stored = store_spotlight_chunks(entries)
            stats["chunks"] += stored
            stats["new_files"] += 1

        except Exception as exc:
            logger.error("init_index: error processing %s: %s", fp, exc)
            stats["errors"] += 1

    return stats


def search(query: str, top_k: int = 5) -> list[SearchResult]:
    """Semantic search across the spotlight index.

    Embeds *query* with the light model, retrieves ``top_k * 4`` candidates
    via cosine similarity, then re-ranks with the cross-encoder if available.
    """
    settings = get_settings()

    # 1 — embed query
    query_vec = _embed([query])
    if not query_vec:
        return []
    query_vec = query_vec[0]

    # 2 — vector search (fetch more candidates for reranking)
    candidates = search_spotlight(query_vec, top_k=top_k * 4)
    if not candidates:
        return []

    # 3 — rerank with cross-encoder if available
    try:
        url = f"{settings.sie_base_url}/v1/rerank"
        payload = {
            "model": settings.rerank_model,
            "query": query,
            "documents": [c.text for c in candidates],
        }
        resp = httpx.post(url, json=payload, timeout=60.0)
        if resp.status_code == 200:
            data = resp.json()
            scores = [r.get("relevance_score", 0.0) for r in data.get("results", [])]
            for c, s in zip(candidates, scores):
                c.rerank_score = s
            # Sort by rerank score descending
            candidates.sort(key=lambda r: r.rerank_score, reverse=True)
    except Exception:
        # Fall through — keep vector-score ordering
        candidates.sort(key=lambda r: r.vector_score)

    return candidates[:top_k]


def status() -> dict:
    """Return spotlight index statistics."""
    total = count_spotlight_entries()
    return {"total_chunks": total}


# ── Optional file watcher ─────────────────────────────────────────────────


def _reindex_file(file_path: str) -> dict:
    """Re-index a single file (called by the watcher on change events).

    Returns stats dict with keys ``chunks``, ``ok``.
    """
    fp = Path(file_path)
    if _should_skip(fp) is not None:
        return {"chunks": 0, "ok": False}

    try:
        fhash = _file_hash(fp)
        text = _read_file(fp)
        if text is None or not text.strip():
            return {"chunks": 0, "ok": False}

        chunks = _chunk_text(text)
        if not chunks:
            return {"chunks": 0, "ok": False}

        embeddings = _embed(chunks)
        if not embeddings or len(embeddings) != len(chunks):
            return {"chunks": 0, "ok": False}

        total = len(chunks)
        entries: list[SpotlightEntry] = []
        for i, (chunk_text, emb) in enumerate(zip(chunks, embeddings)):
            raw = f"{fhash}:{i}"
            cid = hashlib.sha256(raw.encode()).hexdigest()[:24]
            entries.append(
                SpotlightEntry(
                    id=cid,
                    text=chunk_text,
                    file_path=str(fp),
                    source=fp.name,
                    chunk_index=i,
                    total_chunks=total,
                    file_hash=fhash,
                    embedding=emb,
                )
            )

        delete_spotlight_file(fhash)
        store_spotlight_chunks(entries)
        return {"chunks": len(entries), "ok": True}
    except Exception:
        return {"chunks": 0, "ok": False}
