"""Deterministic search tools over the corpus (agent-first, RAG as fallback).

Idea from Sam Bhagwat, "Principles of Building AI Agents" (3rd ed., ch. 19,
"Alternatives to RAG"): give the agent simple search tools over its
corpus first, and keep RAG as the fallback. Here the "agent" is a fixed,
explainable router (see local_rag.agent) — no LLM, stdlib only, $0.

Three tools, all exact and checkable:

  - list_files      — which documents exist (titles + file names).
  - phrase_lookup   — chunks containing an exact quoted phrase.
  - section_lookup  — the chunk(s) under the heading that matches the
                      question's words most closely.

Every tool returns real chunks, so answers built from them carry the same
source-file + chunk citations as the hybrid RAG path.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from local_rag.hybrid import TOKEN_RE, Chunk, tokenize

QUOTED_RE = re.compile(r"[\"“”']([^\"“”']{3,})[\"“”']")

# A question is a file-listing request when it asks *which documents
# exist*, not what a document says. Matched on the raw lowercase text.
LIST_PATTERNS = (
    re.compile(r"^(what|which) (documents|files|policies|docs) (do you have|are (there|available|loaded)|can you (answer|search)( from)?)\W*$"),
    re.compile(r"^(please )?list (all |the |your )?(documents|files|policies|docs)\W*$"),
)

# Section match thresholds. Tuned on both eval sets; re-run the full
# eval (`local-rag eval`) after any change.
SECTION_MIN_SHARED = 2        # heading must share >= 2 content words
SECTION_MIN_Q_COVERAGE = 0.6  # >= 60% of the question's words in the heading
SECTION_MIN_H_COVERAGE = 0.5  # >= 50% of the heading's words in the question


def _stem(term: str) -> str:
    """Very light stemming for heading matching only (starts -> start)."""
    for suffix in ("ies", "es", "s"):
        if len(term) > 4 and term.endswith(suffix):
            return term[: -len(suffix)] + ("y" if suffix == "ies" else "")
    return term


def _stems(text: str) -> set[str]:
    return {_stem(t) for t in tokenize(text)}


@dataclass
class ToolHit:
    tool: str            # "list_files" | "phrase_lookup" | "section_lookup"
    chunks: list[Chunk]
    detail: str = ""     # human-readable: the phrase or heading matched


def is_list_request(question: str) -> bool:
    q = " ".join(question.lower().split())
    return any(p.search(q) for p in LIST_PATTERNS)


def list_files(chunks: list[Chunk]) -> ToolHit:
    """One representative chunk (the first) per source file, in file order."""
    seen: dict[str, Chunk] = {}
    for chunk in chunks:
        seen.setdefault(chunk.source, chunk)
    return ToolHit("list_files", list(seen.values()), f"{len(seen)} files")


def file_title(chunk: Chunk) -> str:
    """The H1 title of the chunk's file, read from disk (falls back to name)."""
    try:
        for line in Path(chunk.file_path).read_text(encoding="utf-8").splitlines():
            if line.startswith("# "):
                return line[2:].strip()
    except OSError:
        pass
    return chunk.source


def quoted_phrase(question: str) -> str | None:
    m = QUOTED_RE.search(question)
    return m.group(1).strip() if m else None


def phrase_lookup(phrase: str, chunks: list[Chunk]) -> ToolHit:
    """Chunks whose text contains the phrase verbatim (case-insensitive,
    whitespace-normalised)."""
    needle = " ".join(phrase.lower().split())
    hits = [c for c in chunks if needle in " ".join(c.text.lower().split())]
    return ToolHit("phrase_lookup", hits, phrase)


def section_lookup(question: str, chunks: list[Chunk]) -> ToolHit:
    """Chunks under the single best-matching heading, or no chunks.

    Returns nothing when the best heading is weak, or when two different
    headings tie for best (ambiguous) — the router then falls back to
    hybrid RAG instead of guessing.
    """
    q = _stems(question)
    if not q:
        return ToolHit("section_lookup", [], "")
    scored: dict[str, tuple[float, list[Chunk]]] = {}
    for chunk in chunks:
        if not chunk.section:
            continue
        key = f"{chunk.source}::{chunk.section}"
        if key in scored:
            scored[key][1].append(chunk)
            continue
        h = _stems(chunk.section)
        shared = len(q & h)
        if not h or shared < SECTION_MIN_SHARED:
            continue
        q_cov = shared / len(q)
        h_cov = shared / len(h)
        if q_cov < SECTION_MIN_Q_COVERAGE or h_cov < SECTION_MIN_H_COVERAGE:
            continue
        scored[key] = (q_cov + h_cov, [chunk])
    if not scored:
        return ToolHit("section_lookup", [], "")
    ranked = sorted(scored.items(), key=lambda kv: kv[1][0], reverse=True)
    if len(ranked) > 1 and abs(ranked[0][1][0] - ranked[1][1][0]) < 1e-9:
        return ToolHit("section_lookup", [], "ambiguous")
    key, (_, hit_chunks) = ranked[0]
    return ToolHit("section_lookup", hit_chunks, key.split("::", 1)[1])


__all__ = [
    "TOKEN_RE", "ToolHit", "is_list_request", "list_files", "file_title",
    "quoted_phrase", "phrase_lookup", "section_lookup",
]
