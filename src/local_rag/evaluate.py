"""Evaluation harness — runs the fixed 10-question test set and scores it.

Metrics (all computed here, none hand-entered):
  - context precision@3: fraction of the top-3 retrieved chunks whose
    source file is in the question's expected_sources.
  - context recall: fraction of expected source files present in top-3.
  - citation accuracy: for answered questions, fraction whose citations
    include at least one expected source.
  - decline accuracy: unanswerable questions correctly declined /
    all unanswerable; answerable questions wrongly declined are counted
    separately as false declines.
  - faithfulness: fraction of answer sentences found verbatim in the
    chunk they cite. (Extractive answers should score 1.0 — if this
    ever drops below 1.0, the answer builder is broken, not the metric.)
  - mean latency in milliseconds, measured per question.

Run:  python -m firm_rag eval
"""

from __future__ import annotations

import json
from pathlib import Path

from local_rag.answer import answer
from local_rag.hybrid import HybridIndex, load_corpus

# Repo root: src/local_rag/evaluate.py -> parents[2].
PACK_ROOT = Path(__file__).resolve().parents[2]


def run_eval(corpus_dir: Path | None = None, test_set: Path | None = None) -> dict:
    corpus_dir = corpus_dir or (PACK_ROOT / "sample_corpus")
    test_set = test_set or (PACK_ROOT / "eval" / "test_set.json")
    cases = json.loads(test_set.read_text(encoding="utf-8"))["questions"]
    index = HybridIndex(load_corpus(corpus_dir))

    rows: list[dict] = []
    for case in cases:
        result = answer(case["question"], index, top_k=3)
        expected = set(case["expected_sources"])
        top3_sources = [c.source for c in result.retrieved[:3]]
        relevant = sum(1 for s in top3_sources if s in expected)
        precision = relevant / max(len(top3_sources), 1) if case["answerable"] else 0.0
        recall = len(expected & set(top3_sources)) / max(len(expected), 1) if case["answerable"] else 0.0
        cited = {c.source for c in result.citations}
        citation_ok = bool(expected & cited) if result.status == "answered" else False
        # Faithfulness: every quoted excerpt must appear verbatim in
        # the text of the chunk it cites. Keyed by (source, chunk) —
        # keying by source alone was a bug: several chunks share a
        # file, and the dict kept only the last one.
        faithful = 0
        total_quotes = 0
        for cit in result.citations:
            total_quotes += 1
            chunk_text = " ".join(cit.chunk_text.split())
            quote = cit.quote.rstrip("…")
            if quote and quote in chunk_text:
                faithful += 1
        faith = faithful / total_quotes if total_quotes else 1.0
        precision_at_1 = 1.0 if top3_sources and top3_sources[0] in expected else 0.0
        if not case["answerable"]:
            precision_at_1 = 0.0
        rows.append({
            "id": case["id"],
            "question": case["question"],
            "answerable": case["answerable"],
            "status": result.status,
            "correct": (result.status == "answered") if case["answerable"]
                       else (result.status == "declined"),
            "context_precision_at_1": round(precision_at_1, 2),
            "context_precision_at_3": round(precision, 2),
            "context_recall": round(recall, 2),
            "citation_ok": citation_ok,
            "faithfulness": round(faith, 2),
            "top_score": round(result.top_score, 3),
            "latency_ms": round(result.latency_ms, 1),
            "answer": result.answer_text,
        })

    answerable = [r for r in rows if r["answerable"]]
    unanswerable = [r for r in rows if not r["answerable"]]
    summary = {
        "n_questions": len(rows),
        "answered_correctly": sum(1 for r in answerable if r["status"] == "answered"),
        "false_declines": sum(1 for r in answerable if r["status"] == "declined"),
        "declined_correctly": sum(1 for r in unanswerable if r["status"] == "declined"),
        "false_answers": sum(1 for r in unanswerable if r["status"] == "answered"),
        "mean_context_precision_at_1": round(
            sum(r["context_precision_at_1"] for r in answerable) / max(len(answerable), 1), 2),
        "mean_context_precision_at_3": round(
            sum(r["context_precision_at_3"] for r in answerable) / max(len(answerable), 1), 2),
        "mean_context_recall": round(
            sum(r["context_recall"] for r in answerable) / max(len(answerable), 1), 2),
        "citation_accuracy": round(
            sum(1 for r in answerable if r["citation_ok"]) / max(len(answerable), 1), 2),
        "decline_accuracy": round(
            sum(1 for r in unanswerable if r["status"] == "declined") / max(len(unanswerable), 1), 2),
        "mean_faithfulness": round(
            sum(r["faithfulness"] for r in rows) / max(len(rows), 1), 2),
        "mean_latency_ms": round(
            sum(r["latency_ms"] for r in rows) / max(len(rows), 1), 1),
    }
    return {"summary": summary, "rows": rows}


def main() -> int:
    """Run the eval from the command line: `python -m local_rag.evaluate`.

    Exit 0 only when every question is correct; exit 1 otherwise.
    """
    import sys

    report = run_eval()
    summary = report["summary"]
    print("\nSummary")
    for key, value in summary.items():
        print(f"  {key}: {value}")
    print("\nPer question")
    for row in report["rows"]:
        mark = "OK " if row["correct"] else "FAIL"
        print(f"  {mark} {row['id']} [{row['status']}] "
              f"P@1={row['context_precision_at_1']} "
              f"P@3={row['context_precision_at_3']} "
              f"recall={row['context_recall']} "
              f"cite={'Y' if row['citation_ok'] else 'n/a' if not row['answerable'] else 'N'} "
              f"top={row['top_score']} {row['latency_ms']}ms")
    return 0 if all(r["correct"] for r in report["rows"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
