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
  - verbatim quote check: for answered questions only, fraction of
    quoted excerpts found verbatim in the chunk they cite. This is a
    sanity check on the answer builder, NOT a faithfulness score:
    answers are cut from the cited chunk, so it is 1.0 by construction.
    A real faithfulness metric needs generated (non-extractive) answers.
  - correct: an answerable question counts as correct only if it was
    answered AND cites an expected source; an unanswerable one only if
    it was declined.
  - mean latency in milliseconds, measured per question.

Since the principles upgrade (feat/principles-upgrades) `local-rag eval`
runs three parts and exits 0 only if all pass:
  1. the original 10 questions through the router (tools first, RAG
     fallback), with the RAG-only numbers printed alongside for comparison;
  2. the extended set (eval/test_set_extended.json): answer-vs-decline
     classification, router path choice, citation + cited-section
     correctness, follow-up (multi-turn) cases. known_limitation cases are
     reported but do not gate the exit code;
  3. review-queue tasks: suspend, survive a restart (new process), approve,
     edit-then-approve, reject, refuse a double decision.
Categories follow Bhagwat, "Principles of Building AI Agents" ch. 27.

Run:  uv run local-rag eval   (or: python -m local_rag.evaluate)
"""

from __future__ import annotations

import json
from pathlib import Path

from local_rag.agent import route_answer
from local_rag.answer import answer
from local_rag.config import find_demo_dir
from local_rag.hybrid import HybridIndex, load_corpus


def run_eval(corpus_dir: Path | None = None, test_set: Path | None = None,
             use_router: bool = True) -> dict:
    corpus_dir = corpus_dir or find_demo_dir("sample_corpus")
    test_set = test_set or (find_demo_dir("eval") / "test_set.json")
    cases = json.loads(test_set.read_text(encoding="utf-8"))["questions"]
    index = HybridIndex(load_corpus(corpus_dir))

    rows: list[dict] = []
    for case in cases:
        if use_router:
            result = route_answer(case["question"], index, top_k=3)
        else:
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
        # None for declined rows: no quotes, nothing to check, and they
        # must not be averaged in as a perfect score.
        faith = faithful / total_quotes if total_quotes else None
        precision_at_1 = 1.0 if top3_sources and top3_sources[0] in expected else 0.0
        if not case["answerable"]:
            precision_at_1 = 0.0
        rows.append({
            "id": case["id"],
            "question": case["question"],
            "answerable": case["answerable"],
            "status": result.status,
            "path": result.path,
            "correct": (result.status == "answered" and citation_ok)
                       if case["answerable"] else (result.status == "declined"),
            "context_precision_at_1": round(precision_at_1, 2),
            "context_precision_at_3": round(precision, 2),
            "context_recall": round(recall, 2),
            "citation_ok": citation_ok,
            "verbatim_quote_check": round(faith, 2) if faith is not None else None,
            "top_score": round(result.top_score, 3),
            "latency_ms": round(result.latency_ms, 1),
            "answer": result.answer_text,
        })

    answerable = [r for r in rows if r["answerable"]]
    unanswerable = [r for r in rows if not r["answerable"]]
    summary = {
        "n_questions": len(rows),
        "answered_correctly": sum(1 for r in answerable if r["correct"]),
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
        "verbatim_quote_check_answered": round(
            sum(r["verbatim_quote_check"] for r in rows if r["verbatim_quote_check"] is not None)
            / max(sum(1 for r in rows if r["verbatim_quote_check"] is not None), 1), 2),
        "mean_latency_ms": round(
            sum(r["latency_ms"] for r in rows) / max(len(rows), 1), 1),
    }
    return {"summary": summary, "rows": rows}


def run_extended(test_set: Path | None = None) -> dict:
    """The extended eval: classification, path choice, citations, follow-ups."""
    test_set = test_set or (find_demo_dir("eval") / "test_set_extended.json")
    cases = json.loads(test_set.read_text(encoding="utf-8"))["questions"]
    indexes: dict[str, HybridIndex] = {}
    rows: list[dict] = []
    for case in cases:
        name = case["corpus"]
        if name not in indexes:
            indexes[name] = HybridIndex(load_corpus(find_demo_dir(name)))
        result = route_answer(case["question"], indexes[name], top_k=3,
                              previous_question=case.get("previous_question"))
        expected = set(case["expected_sources"])
        cited = {c.source for c in result.citations}
        status_ok = (result.status == "answered") == case["answerable"]
        citation_ok = (bool(expected & cited) if case["answerable"] else not cited)
        path_ok = ("expected_path" not in case or result.path == case["expected_path"])
        section_ok = ("expected_section" not in case
                      or any(c.section == case["expected_section"] for c in result.citations))
        quotes_ok = all(" ".join(c.quote.rstrip("…").split()) in " ".join(c.chunk_text.split())
                        for c in result.citations)
        rows.append({
            "id": case["id"], "category": case["category"], "corpus": name,
            "question": case["question"],
            "previous_question": case.get("previous_question"),
            "answerable": case["answerable"], "status": result.status,
            "path": result.path, "expected_path": case.get("expected_path"),
            "status_ok": status_ok, "citation_ok": citation_ok, "path_ok": path_ok,
            "section_ok": section_ok, "quotes_ok": quotes_ok,
            "correct": status_ok and citation_ok and path_ok and section_ok and quotes_ok,
            "known_limitation": case.get("known_limitation", False),
            "why": case.get("why", ""),
            "cited": sorted(cited),
            "answer": result.answer_text,
        })
    gated = [r for r in rows if not r["known_limitation"]]
    tp = sum(1 for r in gated if r["answerable"] and r["status"] == "answered")
    fn = sum(1 for r in gated if r["answerable"] and r["status"] == "declined")
    tn = sum(1 for r in gated if not r["answerable"] and r["status"] == "declined")
    fp = sum(1 for r in gated if not r["answerable"] and r["status"] == "answered")
    with_path = [r for r in gated if r["expected_path"]]
    with_section = [r for r in gated if r["answerable"]]
    multi = [r for r in gated if r["category"] == "multi_turn"]
    summary = {
        "n_cases": len(rows),
        "n_gated": len(gated),
        "n_known_limitations": len(rows) - len(gated),
        "correct": sum(1 for r in gated if r["correct"]),
        "classification": {"answered_answerable": tp, "false_declines": fn,
                           "declined_unanswerable": tn, "false_answers": fp},
        "path_choice_correct": f"{sum(1 for r in with_path if r['path_ok'])}/{len(with_path)}",
        "citation_correct_answerable": f"{sum(1 for r in with_section if r['citation_ok'] and r['section_ok'])}/{len(with_section)}",
        "multi_turn_correct": f"{sum(1 for r in multi if r['correct'])}/{len(multi)}",
        "paths_used": {p: sum(1 for r in rows if r["path"] == p)
                       for p in sorted({r["path"] for r in rows})},
        "known_limitations_still_failing": sum(1 for r in rows
                                               if r["known_limitation"] and not r["correct"]),
    }
    return {"summary": summary, "rows": rows}


def run_review_tasks() -> dict:
    """Task-completion checks for the suspend/resume review queue.

    Uses a throwaway queue file in a temp folder; the restart check reads
    it from a separate Python process, so nothing is shared in memory.
    """
    import subprocess
    import sys
    import tempfile

    from local_rag.review import ReviewError, ReviewQueue

    index = HybridIndex(load_corpus(find_demo_dir("sample_corpus_nonprofit")))
    tasks: list[dict] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        tasks.append({"task": name, "ok": bool(ok), "detail": detail})

    with tempfile.TemporaryDirectory() as tmp:
        qpath = Path(tmp) / "queue.json"
        rq = ReviewQueue(qpath)
        a = route_answer("Who approves new AI tools?", index)
        b = route_answer("How do I get a receipt for my donation?", index)
        c = route_answer("Is there parking at the pantry?", index)
        ids = [rq.suspend(x) for x in (a, b, c)]
        item = rq.get(ids[0])
        check("suspend holds the answer (pending, nothing released)",
              item["state"] == "pending" and item["final_answer"] is None)
        check("suspend keeps citations and route",
              item["draft"]["citations"] and item["draft"]["path"] == a.path)
        check("declined draft is queued as declined",
              rq.get(ids[2])["draft"]["status"] == "declined")
        code = ("import json,sys; d=json.load(open(sys.argv[1])); "
                "print(sum(1 for i in d['items'] if i['state']=='pending'))")
        out = subprocess.run([sys.executable, "-c", code, str(qpath)],
                             capture_output=True, text=True, check=False)
        check("queue survives a restart (read by a new process)",
              out.stdout.strip() == "3", f"pending seen by new process: {out.stdout.strip()}")
        rq2 = ReviewQueue(qpath)  # fresh object = resumed after restart
        approved = rq2.approve(ids[0])
        check("approve releases the draft unchanged",
              approved["state"] == "approved" and approved["final_answer"] == a.answer_text
              and not approved["edited"])
        edited = rq2.approve(ids[1], edited_text="Receipts go out within 5 business days.",
                             note="shortened")
        check("edit-then-approve releases the reviewer's text, marked edited",
              edited["final_answer"] == "Receipts go out within 5 business days."
              and edited["edited"] and edited["reviewer_note"] == "shortened")
        rejected = rq2.reject(ids[2], note="needs a human reply")
        check("reject never releases", rejected["state"] == "rejected"
              and rejected["final_answer"] is None)
        check("nothing left pending", rq2.pending() == [])
        try:
            rq2.approve(ids[2])
            double_ok = False
        except ReviewError:
            double_ok = True
        check("a decided item cannot be decided again", double_ok)
    done = sum(1 for t in tasks if t["ok"])
    return {"summary": {"tasks": len(tasks), "completed": done}, "tasks": tasks}


def main() -> int:
    """Run all three eval parts. Exit 0 only when every gated check passes."""
    base = run_eval(use_router=False)
    report = run_eval(use_router=True)
    ext = run_extended()
    rev = run_review_tasks()

    summary = report["summary"]
    print("\nPart 1 — original 10 questions (router: tools first, RAG fallback)")
    for key, value in summary.items():
        print(f"  {key}: {value}")
    b = base["summary"]
    print(f"  (RAG-only baseline: {b['answered_correctly']} answered correctly, "
          f"{b['declined_correctly']} declined correctly, {b['false_declines']} false "
          f"declines, {b['false_answers']} false answers)")
    print("\n  Per question")
    for row in report["rows"]:
        mark = "OK " if row["correct"] else "FAIL"
        print(f"  {mark} {row['id']} [{row['status']}] path={row['path']} "
              f"P@1={row['context_precision_at_1']} "
              f"P@3={row['context_precision_at_3']} "
              f"recall={row['context_recall']} "
              f"cite={'Y' if row['citation_ok'] else 'n/a' if not row['answerable'] else 'N'} "
              f"top={row['top_score']} {row['latency_ms']}ms")

    print("\nPart 2 — extended eval")
    for key, value in ext["summary"].items():
        print(f"  {key}: {value}")
    for row in ext["rows"]:
        if row["known_limitation"]:
            mark = "KNOWN-FAIL" if not row["correct"] else "KNOWN-NOW-OK"
        else:
            mark = "OK " if row["correct"] else "FAIL"
        flags = "".join(f" {k}=N" for k in ("status_ok", "citation_ok", "path_ok",
                                            "section_ok", "quotes_ok") if not row[k])
        print(f"  {mark} {row['id']} {row['category']} [{row['status']}] "
              f"path={row['path']}{flags} — {row['question']}")

    print("\nPart 3 — review queue tasks")
    for t in rev["tasks"]:
        print(f"  {'OK ' if t['ok'] else 'FAIL'} {t['task']}"
              f"{' (' + t['detail'] + ')' if t['detail'] else ''}")
    print(f"  completed: {rev['summary']['completed']}/{rev['summary']['tasks']}")

    ok = (all(r["correct"] for r in report["rows"])
          and all(r["correct"] for r in ext["rows"] if not r["known_limitation"])
          and rev["summary"]["completed"] == rev["summary"]["tasks"])
    print(f"\nRESULT: {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
