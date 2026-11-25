"""Agent-first router: deterministic tools first, hybrid RAG as fallback.

Idea from Sam Bhagwat, "Principles of Building AI Agents" (3rd ed.,
ch. 19): build the agent with search tools first and use RAG as the
fallback. The "agent" here is a fixed, explainable router — no LLM, so it
stays stdlib-only, $0 and needs no API key. Order:

  1. list_files      — "What documents do you have?"
  2. phrase_lookup   — the question quotes an exact phrase
  3. section_lookup  — the question matches one heading closely
  4. rag             — existing hybrid BM25 + TF-IDF + relevance gate

Whichever route answers, the rules from local_rag.answer still hold:
verbatim excerpts only, every excerpt cited (file + chunk), and value
questions are declined when the cited passage says the value is not in
the documents. The route taken is recorded on the Answer (`path`).

Follow-ups: pass `previous_question` and a short or pronoun-led question
("What does it cover?") is expanded with the previous question's words
before routing. One turn of history only — deliberately simple.
"""

from __future__ import annotations

import time

from local_rag.answer import (
    DECLINE_TEXT, Answer, Citation, _excerpt, _refusal_sentence, answer,
)
from local_rag.hybrid import TOKEN_RE, Chunk, HybridIndex, tokenize
from local_rag.tools import (
    ToolHit, file_title, is_list_request, list_files, phrase_lookup,
    quoted_phrase, section_lookup,
)

ANAPHORA = {"it", "that", "this", "they", "those", "them", "there", "its"}


def is_follow_up(question: str) -> bool:
    raw = set(TOKEN_RE.findall(question.lower()))
    return len(tokenize(question)) <= 2 or bool(raw & ANAPHORA)


def expand_follow_up(question: str, previous_question: str | None) -> str:
    """Prefix the previous question's content words to a follow-up."""
    if not previous_question or not is_follow_up(question):
        return question
    return " ".join(tokenize(previous_question)) + " " + question


def _top(retrieved: list[Chunk]) -> float:
    """Top hybrid rerank score, reported for every route as a diagnostic.
    Tool routes do not produce a score of their own."""
    return retrieved[0].rerank_score if retrieved else 0.0


def _answer_from_chunks(question: str, hit: ToolHit, retrieved: list[Chunk],
                        started: float) -> Answer:
    latency = (time.monotonic() - started) * 1000
    chunks = hit.chunks
    refusal = _refusal_sentence(question, chunks[:1])
    if refusal is not None:
        return Answer(question, "declined",
                      DECLINE_TEXT + f" What the documents do say: \"{refusal}\" "
                      f"[{chunks[0].citation()}]",
                      [], _top(retrieved), retrieved, latency, hit.tool, hit.detail)
    picked: list[Chunk] = []
    for chunk in chunks:
        picked.append(chunk)
        if len(" ".join(_excerpt(c.text) for c in picked)) >= 500 or len(picked) == 2:
            break
    citations = [Citation(c.source, c.chunk_index, c.section, _excerpt(c.text), c.text)
                 for c in picked]
    text = " ".join(f"{cit.quote} [{cit.label()}]" for cit in citations)
    return Answer(question, "answered", text, citations, _top(retrieved), retrieved,
                  latency, hit.tool, hit.detail)


def _answer_file_list(question: str, hit: ToolHit, retrieved: list[Chunk],
                      started: float) -> Answer:
    citations = []
    lines = []
    for chunk in hit.chunks:
        # Quote the first section heading: it is verbatim in the chunk
        # text, so the citation check still holds.
        quote = chunk.section or _excerpt(chunk.text, 80)
        citations.append(Citation(chunk.source, chunk.chunk_index, chunk.section,
                                  quote, chunk.text))
        lines.append(f"{file_title(chunk)} [{chunk.citation()}]")
    text = "The documents I can answer from: " + "; ".join(lines) + "."
    return Answer(question, "answered", text, citations, _top(retrieved), retrieved,
                  (time.monotonic() - started) * 1000, hit.tool, hit.detail)


def route_answer(question: str, index: HybridIndex, top_k: int = 3,
                 previous_question: str | None = None) -> Answer:
    """Answer via the first tool that finds evidence, else hybrid RAG."""
    started = time.monotonic()
    query = expand_follow_up(question, previous_question)
    follow_note = f"follow-up of: {previous_question}" if query != question else ""
    # Hybrid results are always computed: they are the fallback, and the
    # eval uses them for the retrieval metrics on every route.
    retrieved = index.search(query, top_k=top_k)

    def finish(result: Answer) -> Answer:
        result.question = question
        if follow_note:
            result.path_detail = "; ".join(x for x in (result.path_detail, follow_note) if x)
        return result

    if is_list_request(question):
        return finish(_answer_file_list(question, list_files(index.chunks),
                                        retrieved, started))

    phrase = quoted_phrase(question)
    if phrase:
        hit = phrase_lookup(phrase, index.chunks)
        if hit.chunks:
            return finish(_answer_from_chunks(query, hit, retrieved, started))

    hit = section_lookup(query, index.chunks)
    if hit.chunks:
        return finish(_answer_from_chunks(query, hit, retrieved, started))

    result = answer(query, index, top_k=top_k)
    result.path = "rag"
    if phrase:
        result.path_detail = f"quoted phrase not found: {phrase}"
    return finish(result)
