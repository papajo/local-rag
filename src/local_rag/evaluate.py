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
runs five parts and exits 0 only if all pass:
  1. the original 10 questions through the router (tools first, RAG
     fallback), with the RAG-only numbers printed alongside for comparison;
  2. the extended set (eval/test_set_extended.json): answer-vs-decline
     classification, router path choice, citation + cited-section
     correctness, follow-up (multi-turn) cases. known_limitation cases are
     reported but do not gate the exit code;
  3. review-queue tasks: suspend, survive a restart (new process), approve,
     edit-then-approve, reject, refuse a double decision;
  4. direct checks for the Qodo PR #2 fixes (apostrophes, paired
     citations, refusal in a second cited chunk, listing citations, empty
     corpora, --rag-only follow-ups);
  5. the plain-English behaviour specs in features/*.feature (Gherkin,
     run by local_rag.specs), plus a check that every eval case id has a
     spec. @known-failure scenarios are reported but do not gate.
Extended cases may set "answerable": null (either outcome acceptable) plus
forbidden_paths / forbidden_sources / forbidden_sections — regression guards
for routes or passages that must not be used.
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


def paired_section_ok(citations, expected_sources: set[str],
                      expected_section: str | None) -> bool:
    """True when ONE citation has both an expected source and the expected
    section. Checking source and section on separate citations let a case
    pass when the expected file and the expected heading came from two
    unrelated citations (Qodo PR #2, finding 7)."""
    if not expected_section:
        return True
    return any(c.source in expected_sources and c.section == expected_section
               for c in citations)


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
        answerable = case["answerable"]  # True, False, or None = either outcome ok
        if answerable is None:
            status_ok = True
            citation_ok = bool(expected & cited) if result.status == "answered" else not cited
        else:
            status_ok = (result.status == "answered") == answerable
            citation_ok = (bool(expected & cited) if answerable else not cited)
        path_ok = ("expected_path" not in case or result.path == case["expected_path"])
        section_ok = paired_section_ok(result.citations, expected, case.get("expected_section"))
        quotes_ok = all(" ".join(c.quote.rstrip("…").split()) in " ".join(c.chunk_text.split())
                        for c in result.citations)
        # Regression guards: routes, files or sections that must NOT be used.
        forbidden_ok = (result.path not in case.get("forbidden_paths", [])
                        and not (cited & set(case.get("forbidden_sources", [])))
                        and not any(c.section in case.get("forbidden_sections", [])
                                    for c in result.citations))
        rows.append({
            "id": case["id"], "category": case["category"], "corpus": name,
            "question": case["question"],
            "previous_question": case.get("previous_question"),
            "answerable": case["answerable"], "status": result.status,
            "path": result.path, "expected_path": case.get("expected_path"),
            "status_ok": status_ok, "citation_ok": citation_ok, "path_ok": path_ok,
            "section_ok": section_ok, "quotes_ok": quotes_ok, "forbidden_ok": forbidden_ok,
            "correct": (status_ok and citation_ok and path_ok and section_ok and quotes_ok
                        and forbidden_ok),
            "known_limitation": case.get("known_limitation", False),
            "why": case.get("why", ""),
            "cited": sorted(cited),
            "answer": result.answer_text,
        })
    gated = [r for r in rows if not r["known_limitation"]]
    tp = sum(1 for r in gated if r["answerable"] is True and r["status"] == "answered")
    fn = sum(1 for r in gated if r["answerable"] is True and r["status"] == "declined")
    tn = sum(1 for r in gated if r["answerable"] is False and r["status"] == "declined")
    fp = sum(1 for r in gated if r["answerable"] is False and r["status"] == "answered")
    with_path = [r for r in gated if r["expected_path"]]
    with_section = [r for r in gated if r["answerable"] is True]
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


def run_self_checks() -> dict:
    """Small direct checks for the Qodo PR #2 fixes that the question sets
    cannot exercise on their own (synthetic inputs, temp folders)."""
    import tempfile

    from local_rag.agent import _answer_from_chunks, rag_only_answer
    from local_rag.answer import Citation
    from local_rag.hybrid import Chunk
    from local_rag.tools import ToolHit, quoted_phrase

    checks: list[dict] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        checks.append({"task": name, "ok": bool(ok), "detail": detail})

    # Finding 8 — apostrophes are not quote marks; real quotes still are.
    check("apostrophes are not read as a quoted phrase (finding 8)",
          quoted_phrase("What's the client's fee?") is None
          and quoted_phrase("Don't they say it's fine?") is None)
    check("real double and single quotes still give a phrase (finding 8)",
          quoted_phrase('Which policy mentions "locked filing cabinet"?') == "locked filing cabinet"
          and quoted_phrase("Which policy mentions 'locked filing cabinet'?") == "locked filing cabinet")

    # Finding 7 — expected source and section on different citations fails.
    a = Citation("expected.md", 0, "Other heading", "q")
    b = Citation("unrelated.md", 1, "Wanted heading", "q")
    check("mismatched source/section citations fail the paired check (finding 7)",
          not paired_section_ok([a, b], {"expected.md"}, "Wanted heading")
          and paired_section_ok([Citation("expected.md", 0, "Wanted heading", "q")],
                                {"expected.md"}, "Wanted heading"))

    # Finding 9 — a refusal sentence in the SECOND cited chunk declines.
    first = Chunk("Distribution schedule. Food is handed out at the pantry hall.",
                  "x.md", "x.md", 0, "Distribution schedule")
    second = Chunk("Distribution dates. This page does not state the date of the next "
                   "food distribution.", "x.md", "x.md", 1, "Distribution dates")
    res = _answer_from_chunks("What is the date of the next food distribution?",
                              ToolHit("section_lookup", [first, second], "t"), [], 0.0)
    check("refusal sentence in the second cited chunk declines (finding 9)",
          res.status == "declined" and not res.citations, res.status)

    # Finding 3 — every listed title is inside its cited evidence.
    index = HybridIndex(load_corpus(find_demo_dir("sample_corpus")))
    listing = route_answer("What documents do you have?", index)
    check("document listing titles are inside their cited evidence (finding 3)",
          listing.path == "list_files" and listing.citations and all(
              c.level == "document" and c.quote in c.chunk_text
              and f"{c.quote} [{c.label()}]" in listing.answer_text
              for c in listing.citations))

    # Finding 4 — empty / headings-only corpora are rejected.
    rejected = []
    for name, body in (("empty.md", ""), ("headings.md", "# Title\n\n## Section\n")):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / name).write_text(body, encoding="utf-8")
            try:
                load_corpus(tmp)
                rejected.append(False)
            except FileNotFoundError:
                rejected.append(True)
    check("empty and headings-only corpora raise a corpus error (finding 4)", all(rejected))

    # Finding 5 — --rag-only does not inherit an old topic for a full question.
    fresh = rag_only_answer("What should a client bring to the first consultation?", index,
                            previous_question="What is the flat fee for an uncontested divorce?")
    plain = rag_only_answer("What should a client bring to the first consultation?", index)
    follow = rag_only_answer("What does it cover?", index,
                             previous_question="What is the flat fee for an uncontested divorce?")
    check("rag-only ignores --previous for a self-contained question (finding 5)",
          [c.chunk_index for c in fresh.retrieved] == [c.chunk_index for c in plain.retrieved]
          and fresh.path_detail == "")
    check("rag-only still expands a real follow-up (finding 5)",
          follow.path_detail.startswith("follow-up of:"))

    # ── Qodo PR #3 findings (review of 2026-11-25) ─────────────────────────
    # PR3-1 — a refusal sentence with repeated whitespace in the SECOND
    # picked chunk must be cited to that chunk, not to the first one.
    spaced = Chunk("Distribution dates. This page  does not state the date of the next "
                   "food distribution.", "x.md", "x.md", 1, "Distribution dates")
    res = _answer_from_chunks("What is the date of the next food distribution?",
                              ToolHit("section_lookup", [first, spaced], "t"), [], 0.0)
    check("refusal with repeated whitespace cites its own chunk (Qodo PR #3, finding 1)",
          res.status == "declined" and res.answer_text.endswith("[x.md (chunk 1)]"),
          res.answer_text[-40:])
    # Same root cause: "does  not" (two spaces) must still read as a refusal.
    gap = Chunk("Distribution dates. This page does  not state the date of the next "
                "food distribution.", "x.md", "x.md", 1, "Distribution dates")
    res = _answer_from_chunks("What is the date of the next food distribution?",
                              ToolHit("section_lookup", [first, gap], "t"), [], 0.0)
    check("a refusal phrase split by extra spaces still declines (Qodo PR #3, finding 1)",
          res.status == "declined" and res.answer_text.endswith("[x.md (chunk 1)]"),
          res.status)

    # PR3-2 — JSON and review-queue citations for a document listing say
    # they are document-level, and do not point at a section chunk.
    def _listing_dicts_ok(dicts: list[dict]) -> bool:
        return bool(dicts) and all(
            d.get("level") == "document" and d.get("chunk") is None
            and d.get("section") is None and d.get("label", "").endswith("(document title)")
            and d.get("evidence", "").startswith("#")
            for d in dicts)
    try:
        json_ok = _listing_dicts_ok([c.to_dict() for c in listing.citations])
    except AttributeError:
        json_ok = False
    check("JSON listing citations are document-level, no chunk pointer (Qodo PR #3, finding 2)",
          json_ok)
    from local_rag.review import ReviewQueue
    with tempfile.TemporaryDirectory() as tmp:
        rq = ReviewQueue(Path(tmp) / "q.json")
        draft = rq.get(rq.suspend(listing))["draft"]["citations"]
        rag_draft = rq.get(rq.suspend(route_answer(
            "What should a client bring to the first consultation?", index)))["draft"]["citations"]
    check("review-queue listing citations are document-level (Qodo PR #3, finding 2)",
          _listing_dicts_ok(draft))
    check("chunk citations still serialise with chunk and section (Qodo PR #3, finding 2)",
          bool(rag_draft) and all(d.get("level") == "chunk" and isinstance(d.get("chunk"), int)
                                  and d.get("section") for d in rag_draft))

    # PR3-3 — listing evidence is the H1 line read from the file, so the
    # "title inside evidence" check can actually fail.
    from local_rag.agent import file_title_line
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "t.md"
        raw_h1 = "#   Spaced   Title  "
        p.write_text(raw_h1 + "\n\n## A\nText here.\n", encoding="utf-8")
        title, evidence = file_title_line(Chunk("A. Text here.", "t.md", str(p), 0, "A"))
    check("listing evidence is the H1 line exactly as in the file (Qodo PR #3, finding 3)",
          title == "Spaced   Title" and evidence == raw_h1, repr(evidence))
    check("every listing evidence line is a real line of its file (Qodo PR #3, finding 3)",
          all(c.chunk_text in Path(ch.file_path).read_text(encoding="utf-8").splitlines()
              for c, ch in zip(listing.citations, listing_hit_chunks(index))))

    done = sum(1 for c in checks if c["ok"])
    return {"summary": {"checks": len(checks), "passed": done}, "checks": checks}


def listing_hit_chunks(index: HybridIndex) -> list:
    """The representative chunk per file, in the order the listing uses."""
    from local_rag.tools import list_files
    return list_files(index.chunks).chunks


def main() -> int:
    """Run all five eval parts. Exit 0 only when every gated check passes."""
    base = run_eval(use_router=False)
    report = run_eval(use_router=True)
    ext = run_extended()
    rev = run_review_tasks()
    selfc = run_self_checks()
    from local_rag.specs import print_report, run_specs
    specs = run_specs()

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
                                            "section_ok", "quotes_ok", "forbidden_ok")
                        if not row[k])
        print(f"  {mark} {row['id']} {row['category']} [{row['status']}] "
              f"path={row['path']}{flags} — {row['question']}")

    print("\nPart 3 — review queue tasks")
    for t in rev["tasks"]:
        print(f"  {'OK ' if t['ok'] else 'FAIL'} {t['task']}"
              f"{' (' + t['detail'] + ')' if t['detail'] else ''}")
    print(f"  completed: {rev['summary']['completed']}/{rev['summary']['tasks']}")

    print("\nPart 4 — direct checks for the Qodo PR #2 and PR #3 fixes")
    for c in selfc["checks"]:
        print(f"  {'OK ' if c['ok'] else 'FAIL'} {c['task']}"
              f"{' (' + c['detail'] + ')' if c['detail'] and not c['ok'] else ''}")
    print(f"  passed: {selfc['summary']['passed']}/{selfc['summary']['checks']}")

    print("\nPart 5 — plain-English behaviour specs (features/*.feature)")
    print_report(specs)

    ok = (all(r["correct"] for r in report["rows"])
          and all(r["correct"] for r in ext["rows"] if not r["known_limitation"])
          and rev["summary"]["completed"] == rev["summary"]["tasks"]
          and selfc["summary"]["passed"] == selfc["summary"]["checks"]
          and specs["summary"]["all_gated_pass"])
    print(f"\nRESULT: {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
