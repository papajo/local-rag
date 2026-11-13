"""Cited, extractive answers with a relevance gate (the decline).

Design rules, all deliberate:
  - The answer is built ONLY from verbatim sentences in the retrieved
    chunks. No LLM generation in this demo, so nothing can be invented
    and faithfulness is verifiable by string match.
  - Every answer sentence carries a citation: source file + chunk index
    (+ section). A citation is only counted as correct if the cited
    chunk actually contains the sentence — checked in the eval harness.
  - If the best chunk is not relevant enough, the system declines with
    a fixed message. A decline is a correct outcome for an unanswerable
    question, and a failure if it fires on an answerable one.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field

from local_rag.hybrid import Chunk, HybridIndex, tokenize

# Relevance gate: the top reranked chunk must score at least this, and
# share at least two query terms with the question. Tuned on the
# 10-question eval set — see eval/results-2026-11-13.md. Do not lower
# it to make a single question pass; re-run the full eval instead.
# Defaults live here; local_rag.config overrides them when present.
RELEVANCE_THRESHOLD = 0.35
MIN_SHARED_TERMS = 2
try:
    from local_rag.config import get_settings as _get_settings

    _settings = _get_settings()
    RELEVANCE_THRESHOLD = _settings.relevance_threshold
    MIN_SHARED_TERMS = _settings.min_shared_terms
except Exception:
    pass

DECLINE_TEXT = (
    "I can't answer that from the documents provided. "
    "The sample firm documents do not contain that information, "
    "so I won't guess. Please ask the firm directly, or rephrase "
    "the question using the firm's own wording."
)

SENTENCE_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z])")


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in SENTENCE_RE.split(text.strip()) if s.strip()]


def _excerpt(text: str, max_chars: int = 900) -> str:
    """First ~900 chars of a chunk, cut at a word boundary.

    Excerpts are used instead of cherry-picked sentences: a numbered
    list ("1. marriage certificate. 2. financial affidavit…") survives
    intact, and the answer stays a verbatim passage, not a synthesis.
    900 matches the chunk size, so an excerpt is usually the whole
    chunk — the 500-char limit cut the flagship documents question
    off mid-list in the first eval run.
    """
    text = " ".join(text.split())
    if len(text) <= max_chars:
        return text
    cut = text[:max_chars].rsplit(" ", 1)[0]
    return cut + "…"


@dataclass
class Citation:
    source: str
    chunk_index: int
    section: str
    quote: str
    chunk_text: str = ""  # full text of the cited chunk (faithfulness check)

    def label(self) -> str:
        return f"{self.source} (chunk {self.chunk_index})"


@dataclass
class Answer:
    question: str
    status: str  # "answered" or "declined"
    answer_text: str
    citations: list[Citation] = field(default_factory=list)
    top_score: float = 0.0
    retrieved: list[Chunk] = field(default_factory=list)
    latency_ms: float = 0.0


def _shared_terms(question: str, chunk: Chunk) -> int:
    return len(set(tokenize(question)) & set(tokenize(chunk.text)))


def answer(question: str, index: HybridIndex, top_k: int = 3) -> Answer:
    """Answer one question from the index, or decline."""
    started = time.monotonic()
    retrieved = index.search(question, top_k=top_k)
    latency_ms = (time.monotonic() - started) * 1000

    if not retrieved:
        return Answer(question, "declined", DECLINE_TEXT, [], 0.0, [], latency_ms)

    top = retrieved[0]
    shared = _shared_terms(question, top)
    if top.rerank_score < RELEVANCE_THRESHOLD or shared < MIN_SHARED_TERMS:
        return Answer(question, "declined", _decline_with_evidence(question, retrieved),
                      [], top.rerank_score, retrieved, latency_ms)

    # Refusal check: if the question asks for a *value* (a fee, a
    # deadline, a date) and the best passage says the documents do not
    # contain that value, decline instead of quoting general text as
    # if it were the answer. Example: a specific-case deadline question
    # retrieves the policy sentence "It does not state the deadline for
    # any specific client's case" — quoting that as an answer would
    # mislead; declining with it as evidence is correct. A question
    # that asks *what* is refused ("What cases does the firm not take
    # on?") is not value-seeking, so it is answered, not declined.
    refusal = _refusal_sentence(question, retrieved)
    if refusal is not None:
        return Answer(question, "declined",
                      DECLINE_TEXT + f" What the documents do say: \"{refusal}\"",
                      [], top.rerank_score, retrieved, latency_ms)

    # Extractive answer: verbatim excerpts from the top chunks, in
    # rerank order. The top chunk's excerpt first; a second chunk only
    # if the first is short. No sentence cherry-picking across chunks —
    # that pulled in off-topic sentences (e.g. a fee sentence for a
    # documents question) in the first eval run.
    picked: list[tuple[str, Chunk]] = []
    for chunk in retrieved:
        picked.append((_excerpt(chunk.text), chunk))
        if len(" ".join(p[0] for p in picked)) >= 500:
            break
    picked = picked[:2]

    citations = [
        Citation(chunk.source, chunk.chunk_index, chunk.section, excerpt, chunk.text)
        for excerpt, chunk in picked
    ]
    answer_text = " ".join(
        f"{excerpt} [{citation.label()}]"
        for (excerpt, _), citation in zip(picked, citations)
    )
    return Answer(question, "answered", answer_text, citations,
                  top.rerank_score, retrieved, latency_ms)


VALUE_TERMS = {"fee", "cost", "price", "deadline", "date", "when",
               "amount", "much", "specific", "long"}
REFUSAL_PHRASES = ("does not", "do not", "will not", "never")


def _refusal_sentence(question: str, retrieved: list[Chunk]) -> str | None:
    """A refusal sentence that denies the value the question asks for.

    Returns the sentence, or None. Only fires for value-seeking
    questions, so "what do you not take on?" still gets answered.
    """
    query_terms = set(tokenize(question))
    if not (query_terms & VALUE_TERMS):
        return None
    for chunk in retrieved:
        for sentence in _sentences(chunk.text):
            lowered = sentence.lower()
            if not any(p in lowered for p in REFUSAL_PHRASES):
                continue
            if len(query_terms & set(tokenize(sentence))) >= MIN_SHARED_TERMS:
                return sentence
    return None


def _decline_with_evidence(question: str, retrieved: list[Chunk]) -> str:
    """Decline, plus the closest thing the documents do say, if any.

    When the top chunk shares at least two query terms, quote its most
    relevant sentence as evidence — e.g. for a specific-case deadline
    question, the policy sentence that says the policy does not state
    a specific client's deadline. The status stays "declined": the
    evidence explains the decline, it does not turn it into an answer.
    """
    query_terms = set(tokenize(question))
    for chunk in retrieved:
        if _shared_terms(question, chunk) < MIN_SHARED_TERMS:
            continue
        best: tuple[int, str] | None = None
        for sentence in _sentences(chunk.text):
            overlap = len(query_terms & set(tokenize(sentence)))
            if best is None or overlap > best[0]:
                best = (overlap, sentence)
        if best and best[0] >= MIN_SHARED_TERMS:
            return (DECLINE_TEXT + f" What the documents do say: "
                    f"\"{best[1]}\" [{chunk.citation()}]")
    return DECLINE_TEXT
