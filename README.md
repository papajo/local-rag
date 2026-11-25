# local-rag

Private, local semantic search over your documents. Uses a local SIE (Superlinked
Inference Engine) server for embedding, vector search, and optional reranking.

## Quick start

```bash
uv sync                                  # install deps
# Start Sie in another terminal, then:
uv run local-rag ingest                  # index ~/Documents
uv run local-rag query "your question"   # search
uv run local-rag status                  # what's indexed
```

Full setup and CLI reference: [`instructions.md`](instructions.md)

---

## Incremental ingest

`local-rag ingest` is idempotent — it tracks file hashes (SHA-256) in a SQLite
state DB at `data/ingest_state.db`. Running it again:

- **Skips** files whose content hash hasn't changed
- **Re-processes** new or modified files (hash mismatch)
- **Does not** remove chunks for deleted files (use `rm data/ingest_state.db`
  to force a full re-index if you need cleanup)

```bash
uv run local-rag ingest                  # index default paths
uv run local-rag ingest ~/file.py        # add specific files
uv run local-rag ingest ~/Documents/     # index a custom path
```

To rebuild the index from scratch:

```bash
rm -rf data/lancedb data/ingest_state.db
uv run local-rag ingest
```

### Code repo ingest

For indexing a code repository with code-appropriate chunking (function/class
boundaries) and expanded skip-dirs:

```bash
uv run local-rag ingest-repo ~/projects/my-repo
```

---

## Known issues

### Generation desync after LanceDB reset

If `chunks.lance` is deleted but `ingest_state.db` / `rag_generation` are
preserved, the next run auto-detects the mismatch and resets — all files
get re-indexed. You'll see:

```
Generation mismatch (LanceDB gen=N, state gen=M). Resetting ingest state — all
files will be re-indexed.
```

This is a one-time cost. Subsequent runs resume incremental behavior.

### Reranker unavailable

If the Sie server is down, query results fall back to vector-distance sorting
(no reranking). Set `SIE_BASE_URL` to point at your running instance.

### PDF extraction noise

Some PDFs produce `"Ignoring wrong pointing object"` warnings from `pypdf`.
These are harmless — the fallback extractor (`pypdfium2`) is used automatically.

### Web UI search returns 422

The search form (`/`) submits `POST` with form field `q`. The HTML form field
name must match `q` (not `query_text`), as the FastAPI handler uses
`Form(..., alias="q")`. If you see a `422 Unprocessable Entity` with
`"Field required"` on `q`, the form field name is mismatched.

---

## All documentation

| File | Contents |
|---|---|
| [`instructions.md`](instructions.md) | Full setup, architecture, CLI reference, score interpretation, API |
| [`docs/mainIdea.md`](docs/mainIdea.md) | Original motivation and use cases |

---

## P1 upgrade — cited answers with a decline (Firm Knowledge Assistant)

`query` searches; `ask` answers. New in this branch:

```bash
uv run local-rag ask "What documents are needed for an uncontested divorce intake?"
uv run local-rag ask "When did someone last go to the moon?"   # declines, does not guess
uv run local-rag eval   # original 10 + extended 26 + review-queue tasks + fix checks; must exit 0
```

What it adds: hybrid retrieval (BM25 + TF-IDF cosine, reciprocal rank
fusion, explainable rerank), cited extractive answers (verbatim passages,
source file + chunk), a relevance gate that declines instead of guessing,
a refusal check that declines value questions (a fee, a deadline) when
the documents say the value is not in them, and a 10-question eval
harness (7 answerable, 3 unanswerable by design). Eval on the bundled
fictional sample corpus (`sample_corpus/`, Harbor & Pine Law — sample
data only): all 7 answerable questions answered with a citation to the
right source, all 3 unanswerable ones declined; precision @1 1.00,
citation accuracy 1.00. A question only counts as correct if it is
answered *and* cites an expected source. Full numbers:
[`eval/results-2026-11-24.md`](eval/results-2026-11-24.md).

**Known limitations (read before using it on real documents):**

- `ask` builds its own in-memory index from a folder of Markdown files.
  It does not yet read the LanceDB index built by `ingest`, so PDFs and
  other ingested documents can't be asked about yet. Wiring `ask` to the
  existing SIE/LanceDB search is the next step (swap points in
  [`docs/p1-rag-upgrade.md`](docs/p1-rag-upgrade.md)).
- The eval is 10 questions on 6 fictional files. It shows the pipeline
  works end to end; it is not a benchmark.
- Answers are extractive (verbatim passages), so there is no
  faithfulness score to report: the quote check is 1.0 by construction.
- The relevance gate is keyword-based (term coverage + shared terms).
  Very short questions that share only one word with the right passage
  can be declined (e.g. "How much is a consultation?").
- `sample_corpus/` and `eval/` ship with the source checkout, not the
  installed package. Run from the repo folder, or pass `--corpus`.

**Principles upgrades (branch `feat/principles-upgrades`, 2026-11-25).**
Three ideas from Sam Bhagwat, *Principles of Building AI Agents* (3rd ed.,
Mastra, 2026), ch. 19, 14 and 27, built stdlib-only, $0, no API key:

1. **Search tools first, RAG as the fallback** (`src/local_rag/agent.py`,
   `src/local_rag/tools.py`). `ask` now tries three deterministic tools —
   list the documents, find an exact "quoted phrase", match a section
   heading — and falls back to the hybrid retrieval above when none finds
   evidence. Same rules on every route: verbatim excerpts, file + chunk
   citations, value questions declined when the passage says the value is
   not there. The route is shown (`path`) and is in `--json`.
   `--rag-only` gives the old behaviour. `--previous "..."` handles a
   one-turn follow-up ("What does it cover?").
2. **Suspend/resume human review** (`src/local_rag/review.py`, off by
   default). `ask --review` holds the drafted answer in a JSON queue on disk
   (`data/review_queue.json`, or `--queue`, or `$LOCAL_RAG_REVIEW_QUEUE`)
   instead of releasing it. Then: `local-rag review list`,
   `review show ID`, `review approve ID [--edit "text"]`,
   `review reject ID --note "why"`. Every command re-reads the file and
   writes atomically, so pending items survive a restart.
3. **Bigger eval** (`eval/test_set_extended.json`). 26 more cases:
   answer-vs-decline, router path choice, citation + cited section,
   follow-ups, plus 9 review-queue task checks. Most cases use
   `sample_corpus_nonprofit/` — **Bayside Community Pantry is an invented
   nonprofit; every file is labelled sample data and nothing in it is
   real.**

**Qodo review fixes on PR #2 (2026-11-25).** Qodo flagged 10 findings on
this branch; 7 are fixed here:

- Section matches must cover the whole question: a heading that shares two
  words ("What the flat fee covers") no longer answers "What is the
  deadline for the flat fee?" — the passage must contain every content word
  of the question, otherwise it falls back to gated RAG (finding 1).
- Apostrophes are not quote marks: "What's the client's fee?" used to be
  read as the exact phrase "s the client" and answered from the
  confidentiality policy. Only double quotes, or single quotes around a
  phrase (not inside a word), count; a quoted phrase needs 2+ content
  words (finding 8).
- The refusal check now covers every chunk that will be cited, not only
  the first, on both the RAG and tool routes (finding 9).
- Document listings cite each file's title line, so the displayed title is
  in the cited evidence (finding 3).
- The extended eval checks source and section on the same citation
  (finding 7).
- A folder of empty or headings-only Markdown files is now a corpus error,
  not a silent decline-everything (finding 4).
- `--rag-only --previous` uses the previous question only for real
  follow-ups (finding 5).

Not changed (low practical risk, noted for later): the review queue has no
cross-process lock (finding 2); RAG fallback runs the hybrid search twice
(finding 6, performance only); the default review queue path for a wheel
install points inside the package (finding 10 — use `--queue` or
`$LOCAL_RAG_REVIEW_QUEUE` until fixed).

Eval on 2026-11-25 after the Qodo fixes (`python -m local_rag.evaluate`,
exit 0; full numbers in
[`eval/results-2026-11-25-qodo-pr2.md`](eval/results-2026-11-25-qodo-pr2.md)):

| Part | Result |
|---|---|
| Original 10 (router) | 7 answered with the right citation, 3 declined, 0 false answers — same as before (RAG-only also 7 / 3). Q1, Q2, Q3, Q6 answered by the section tool; the rest by RAG. |
| Extended, gated (23) | 23/23 correct: 15 answered, 6 declined, 2 regression cases where either outcome is allowed (both answered, from allowed sources); 0 false answers, 0 false declines; path choice 13/13; citation + section on the same citation 15/15; follow-ups 4/4 |
| Known limitations (3) | still failing, shown every run, not counted (see below) |
| Review queue tasks | 9/9 |
| Direct checks for the Qodo fixes | 8/8 |

Also fixed: possessives (`pantry's`) tokenised to a stray `s` that counted
as a shared word and let off-topic chunks pass the gate; `s`/`t` are now
stopwords. The original 10 are unchanged by it.

**Known limitations of the upgrades:**

- Still true: `ask` (router included) reads Markdown folders only — it
  does **not** read the LanceDB index built by `ingest`.
- The router is rules, not an LLM. Section matching uses word overlap with
  light plural stripping; two equally good headings (e.g. "How long
  records are kept" vs "Where household records are kept") count as
  ambiguous and go to RAG.
- Keyword gate misses, kept visible as eval cases K1/K2: a synonym the
  documents don't use ("homemade" vs "home-cooked") is declined even
  though the answer is there; a question that shares a name with an
  unrelated passage ("executive director's salary") gets that passage
  quoted. Embeddings (the SIE swap) are the fix, not threshold tuning.
- K3: after the finding 1 fix, "What is the deadline for the flat fee?"
  no longer goes through the section tool, but the RAG fallback still
  quotes "What the flat fee covers" first (then the fee schedule, which
  does give the two payment points). The keyword gate passes on 2 of 3
  words. A literal "the passage must mention the deadline" rule was tried
  and dropped: it wrongly declined "How much does document review cost?"
  (the schedule says "$200 per hour", not "cost").
- Follow-ups are one turn only (`--previous`), triggered by short or
  pronoun-led questions.
- An edited approval is the reviewer's wording, flagged `edited: true`;
  it is no longer a verbatim quote of the cited chunks. The queue is a
  single local JSON file for one reviewer at a time — no locking across
  simultaneous reviewers.
- Path, precision and recall numbers for tool routes use the hybrid
  retrieval run alongside every question, so the Part 1 retrieval metrics
  match the RAG-only run by construction.
- 36 questions on 11 invented files is a regression check, not a benchmark.

Notes: the demo runs with $0 and no server (TF-IDF is a stand-in for
the SIE embeddings so it runs anywhere). In production, swap the TF-IDF
scorer for the existing SIE embedding search — see
[`docs/p1-rag-upgrade.md`](docs/p1-rag-upgrade.md). The sample corpus
stays fictional; never replace it with real firm documents in this repo.
Demo script: [`docs/p1-demo-script.md`](docs/p1-demo-script.md).
