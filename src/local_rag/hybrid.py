"""Hybrid retrieval for the P1 Firm Knowledge Assistant demo.

Zero new dependencies (stdlib only). Two retrievers, fused:

  1. BM25 keyword retrieval — catches exact terms ("affidavit", "flat fee").
  2. TF-IDF cosine retrieval — catches wording that differs from the query.

They are combined with reciprocal rank fusion (RRF), then re-ranked by an
explainable scorer (fused score + query-term coverage + exact-phrase bonus).

The TF-IDF scorer here is a stand-in so the demo runs anywhere with $0
and no server. In production, swap `tfidf_scores` for the existing SIE
embedding search (`store.search` + `query.rerank` in local_rag) and keep
BM25, RRF, the gate and the evaluation harness unchanged — the fusion
takes rankings, not scores, so the embedding ranking drops in as-is.
See `docs/p1-rag-upgrade.md` for the swap points.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from pathlib import Path

STOPWORDS = {
    "a", "an", "the", "and", "or", "of", "to", "in", "on", "for", "is",
    "are", "was", "were", "be", "by", "with", "what", "how", "when",
    "where", "who", "does", "do", "did", "can", "could", "should",
    "would", "it", "its", "this", "that", "my", "your", "i", "we",
    "you", "they", "them", "their", "there", "here", "from", "at",
    "as", "if", "so", "not", "no", "me", "am", "an", "have", "has",
    "had", "will", "just", "about", "into", "than", "then", "but",
    "all", "any", "each", "which", "please", "tell", "give", "know",
}

TOKEN_RE = re.compile(r"[a-z0-9]+")


def tokenize(text: str) -> list[str]:
    """Lowercase word tokens, stopwords removed."""
    return [t for t in TOKEN_RE.findall(text.lower()) if t not in STOPWORDS]


@dataclass
class Chunk:
    text: str
    source: str          # filename, e.g. "01-intake-checklist.md"
    file_path: str
    chunk_index: int
    section: str = ""    # heading the chunk sits under
    bm25_score: float = 0.0
    tfidf_score: float = 0.0
    fused_score: float = 0.0
    rerank_score: float = 0.0

    def citation(self) -> str:
        return f"{self.source} (chunk {self.chunk_index})"


def chunk_document(path: Path, max_chars: int = 900) -> list[Chunk]:
    """Split one markdown file into chunks, accumulating paragraphs
    under each heading until max_chars, then flushing.

    Accumulation matters: a short intro paragraph ("An uncontested
    divorce turns on…") and the numbered list under it ("1. marriage
    certificate…") belong in ONE chunk. Splitting them put the list in
    a chunk with none of the question's words in it, so retrieval
    ranked the actual answer below the intro — the flagship documents
    question then answered without showing the document list. That
    was a real miss in the first eval run, fixed here.
    """
    text = path.read_text(encoding="utf-8")
    # Drop the SAMPLE banner blockquote lines — they are not content.
    lines = [ln for ln in text.splitlines() if not ln.strip().startswith(">")]
    chunks: list[Chunk] = []
    section = ""
    buf: list[str] = []
    buf_len = 0

    def flush() -> None:
        nonlocal buf, buf_len
        joined = " ".join(p.strip() for p in buf if p.strip())
        if joined:
            # Prepend the section heading to the indexed text: headings
            # carry the question's words ("Documents needed for an
            # uncontested divorce intake"), and without them the list
            # chunk shared almost no terms with its own question and
            # ranked below a neighbouring file. The heading is part of
            # the passage a reader sees, so it belongs in the excerpt too.
            text = f"{section}. {joined}" if section else joined
            chunks.append(Chunk(
                text=text, source=path.name, file_path=str(path),
                chunk_index=len(chunks), section=section,
            ))
        buf = []
        buf_len = 0

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("#"):
            flush()
            section = stripped.lstrip("#").strip()
            continue
        if not stripped:
            continue
        if buf and buf_len + len(stripped) > max_chars:
            flush()
        buf.append(stripped)
        buf_len += len(stripped) + 1
    flush()
    return chunks


def load_corpus(corpus_dir: str | Path) -> list[Chunk]:
    """Load every .md file in a directory, in filename order."""
    chunks: list[Chunk] = []
    for path in sorted(Path(corpus_dir).glob("*.md")):
        chunks.extend(chunk_document(path))
    # Re-number chunk_index globally so citations are unambiguous.
    for i, chunk in enumerate(chunks):
        chunk.chunk_index = i
    return chunks


class HybridIndex:
    """BM25 + TF-IDF over a small in-memory chunk list, fused with RRF."""

    def __init__(self, chunks: list[Chunk]):
        self.chunks = chunks
        self.docs = [tokenize(c.text) for c in chunks]
        self.doc_lens = [len(d) for d in self.docs]
        self.avg_len = sum(self.doc_lens) / max(len(self.doc_lens), 1)
        self.n_docs = len(chunks)
        # Document frequencies.
        self.df: dict[str, int] = {}
        for doc in self.docs:
            for term in set(doc):
                self.df[term] = self.df.get(term, 0) + 1
        # TF-IDF vectors (sparse dicts), built once.
        self.tfidf_vecs: list[dict[str, float]] = []
        for doc in self.docs:
            vec: dict[str, float] = {}
            counts: dict[str, int] = {}
            for term in doc:
                counts[term] = counts.get(term, 0) + 1
            for term, count in counts.items():
                idf = math.log(1 + (self.n_docs - self.df[term] + 0.5) / (self.df[term] + 0.5))
                vec[term] = (1 + math.log(count)) * idf
            norm = math.sqrt(sum(v * v for v in vec.values())) or 1.0
            self.tfidf_vecs.append({t: v / norm for t, v in vec.items()})

    # -- BM25 ---------------------------------------------------------------
    def bm25_scores(self, query_terms: list[str], k1: float = 1.5, b: float = 0.75) -> list[float]:
        scores = [0.0] * self.n_docs
        for term in query_terms:
            df = self.df.get(term, 0)
            if df == 0:
                continue
            idf = math.log(1 + (self.n_docs - df + 0.5) / (df + 0.5))
            for i, doc in enumerate(self.docs):
                tf = doc.count(term)
                if tf == 0:
                    continue
                denom = tf + k1 * (1 - b + b * self.doc_lens[i] / (self.avg_len or 1))
                scores[i] += idf * tf * (k1 + 1) / denom
        return scores

    # -- TF-IDF cosine --------------------------------------------------------
    def tfidf_scores(self, query_terms: list[str]) -> list[float]:
        qvec: dict[str, float] = {}
        counts: dict[str, int] = {}
        for term in query_terms:
            counts[term] = counts.get(term, 0) + 1
        for term, count in counts.items():
            idf = math.log(1 + (self.n_docs - self.df.get(term, 0) + 0.5) / (self.df.get(term, 0) + 0.5))
            qvec[term] = (1 + math.log(count)) * idf
        qnorm = math.sqrt(sum(v * v for v in qvec.values())) or 1.0
        qvec = {t: v / qnorm for t, v in qvec.items()}
        scores = []
        for vec in self.tfidf_vecs:
            scores.append(sum(qvec.get(t, 0.0) * v for t, v in vec.items()))
        return scores

    # -- Fusion + rerank ------------------------------------------------------
    @staticmethod
    def _rrf(rankings: list[list[int]], k: int = 60) -> dict[int, float]:
        fused: dict[int, float] = {}
        for ranking in rankings:
            for rank, doc_id in enumerate(ranking):
                fused[doc_id] = fused.get(doc_id, 0.0) + 1.0 / (k + rank + 1)
        return fused

    def search(self, query: str, top_k: int = 5, fetch_k: int = 10) -> list[Chunk]:
        """Return the top_k chunks after BM25 + TF-IDF fusion and reranking."""
        query_terms = tokenize(query)
        if not query_terms:
            return []
        bm25 = self.bm25_scores(query_terms)
        tfidf = self.tfidf_scores(query_terms)

        bm25_rank = sorted(range(self.n_docs), key=lambda i: bm25[i], reverse=True)
        tfidf_rank = sorted(range(self.n_docs), key=lambda i: tfidf[i], reverse=True)
        fused = self._rrf([bm25_rank, tfidf_rank])

        # Candidate pool: union of the top fetch_k from each retriever.
        pool = sorted(set(bm25_rank[:fetch_k]) | set(tfidf_rank[:fetch_k]),
                      key=lambda i: fused.get(i, 0.0), reverse=True)
        max_fused = max((fused.get(i, 0.0) for i in pool), default=1.0) or 1.0

        results: list[Chunk] = []
        query_set = set(query_terms)
        query_lower = query.lower()
        for i in pool:
            chunk = self.chunks[i]
            chunk.bm25_score = bm25[i]
            chunk.tfidf_score = tfidf[i]
            chunk.fused_score = fused.get(i, 0.0)
            # Explainable rerank: fused score + term coverage + phrase bonus.
            # This stands in for the SIE cross-encoder in local-rag; see
            # local-rag-integration.md for the swap.
            coverage = len(query_set & set(self.docs[i])) / max(len(query_set), 1)
            phrase_bonus = 0.15 if query_lower in chunk.text.lower() else 0.0
            chunk.rerank_score = (
                0.6 * (chunk.fused_score / max_fused)
                + 0.4 * coverage
                + phrase_bonus
            )
            results.append(chunk)
        results.sort(key=lambda c: c.rerank_score, reverse=True)
        return results[:top_k]
