# P1 — Firm Knowledge Assistant: production-ready RAG upgrade for local-rag

**What this is:** the Sundas Khalid Project 1 build, reframed for joshi's
service business. It upgrades his pinned repo
[github.com/papajo/local-rag](https://github.com/papajo/local-rag) from
"local semantic search" to a production-ready RAG demo: cited answers,
a decline when the documents do not contain the answer, hybrid retrieval,
and a published evaluation table. The demo runs on a fictional law firm's
sample documents — no real firm, no real client data.

**Status: built and tested in the sandbox, Nov 13 2026. Eval: 10/10
questions correct** — 7 answered, 3 correctly declined, 0 false declines,
0 false answers. Full numbers in `eval/results-2026-11-13.md`.
Cost to run: $0. No API key, no server, no new install.

## What the audit found in local-rag as it exists today

Cloned and read Nov 13 2026 (`papajo/local-rag`, Python, LanceDB + a local
SIE server for embeddings, ~4,700 lines). What it already does well:

- Private, local semantic search over documents; incremental ingest with
  SHA-256 file tracking; code-aware chunking; a cross-encoder reranker
  via SIE with a vector-score fallback; a web UI and CLI.
- Retrieval results already carry source file + chunk index — the raw
  material for citations is there.

What it does **not** do yet (the P1 gaps):

1. **No answer generation.** `query` returns ranked snippets. There is no
   LLM answer, and therefore no cited answer a firm owner can read.
2. **No decline.** LanceDB always returns the top 50 by cosine distance,
   however irrelevant. An off-topic question still gets results.
3. **No hybrid retrieval.** Vector search only (cosine). No keyword
   retrieval, so exact terms ("affidavit", "flat fee") get no boost.
4. **No evaluation.** No test set, no precision / recall / faithfulness /
   citation-accuracy numbers anywhere in the repo.
5. **Hard SIE dependency.** Embeddings and reranking need the SIE server
   on `127.0.0.1:8080` with BAAI/bge-m3. Without it, nothing runs — which
   is why this demo pack is self-contained (see below).

## What this pack adds (and what it deliberately does not)

| Added | Where |
|---|---|
| Hybrid retrieval: BM25 + TF-IDF cosine, fused with reciprocal rank fusion, explainable rerank | `src/local_rag/hybrid.py` |
| Cited, extractive answers (verbatim passages, source + chunk citation) | `src/local_rag/answer.py` |
| Relevance gate + refusal check → decline with evidence, never a guess | `src/local_rag/answer.py` |
| 10-question eval harness (7 answerable, 3 unanswerable by design) | `src/local_rag/evaluate.py`, `eval/test_set.json` |
| Sample firm corpus: 6 fictional law-firm docs, sample-only | `sample_corpus/` |
| CLI: `ask` and `eval` commands | `src/local_rag/cli.py` |
| Wiring: thresholds in config, commands in CLI | `src/local_rag/config.py`, `src/local_rag/cli.py` |
| 2–3 minute demo script | `demo-script.md` |

Deliberately **not** in this pack: no LLM answer generation (the demo
answers are extractive, so faithfulness is verifiable by string match),
no new dependencies (stdlib only — it runs on plain Python 3.10+), no
change to the existing SIE path in local-rag (that stays the production
embedder; see the integration note), no real firm or client data.

The honest limit: TF-IDF is a stand-in for the SIE bge-m3 embeddings so
the demo runs anywhere with $0 spend. On a real firm's documents, swap
the TF-IDF scorer for the existing `store.search` call and keep BM25,
the gate and the eval harness unchanged. That swap is spelled out in
`docs/p1-rag-upgrade.md` (this file).

## How to run it (from this folder, Python 3.10+, nothing to install)

```bash
uv run local-rag ask "What documents are needed for an uncontested divorce intake?"
uv run local-rag ask "When did someone last go to the moon?"
uv run local-rag ask "What is the deadline for my specific case filed last Tuesday?"
uv run local-rag eval
```

`ask` prints `[ANSWERED]` or `[DECLINED]`, the answer with citations,
and the retrieved chunks with rerank scores. Add `--json` for
machine-readable output. `eval` runs the 10-question test set, prints
the summary and per-question table, and exits 0 only if every question
is correct (exit 1 otherwise — it is a real gate, not a report).

## Eval results — Nov 13 2026 (measured, not claimed)

| Metric | Result |
|---|---|
| Questions correct | 10 / 10 |
| Answered correctly | 7 / 7 (0 false declines) |
| Declined correctly | 3 / 3 (0 false answers) |
| Context precision @1 | 1.00 |
| Context precision @3 | 0.57 |
| Context recall | 0.93 |
| Citation accuracy | 1.00 |
| Decline accuracy | 1.00 |
| Faithfulness (verbatim in cited chunk) | 1.00 |
| Mean latency | 0.2 ms per question (in-memory, 16 chunks) |

Read the numbers honestly: precision @3 is 0.57 because the 2nd and 3rd
retrieved chunks are often neighbours from another file — the top chunk
(@1) is right every time, which is what the answer is built from. Recall
0.93: one question (Q3) has two expected source files and only one
appears in the top 3. Latency is meaningless at this corpus size; it
only proves the harness measures it. Full per-question table and the
three bugs the first eval run caught are in `eval/results-2026-11-13.md`.

## The demo in one line

Ask the documents question, show the 5-item list with its citation.
Ask the moon question, show the decline. Ask the specific-deadline
question, show the decline *with the policy sentence as evidence*.
That third one is the selling point: the system refuses to invent a
deadline, and shows you the sentence that says why. Full script in
`demo-script.md`.

## This doc in the repo

This file is the P1 pack doc, kept for the record. The pack is merged:
the modules live in `src/local_rag/` (`hybrid.py`, `answer.py`,
`evaluate.py`), the commands in `src/local_rag/cli.py`, the sample
corpus in `sample_corpus/`, the test set and results in `eval/`.
Run `uv run local-rag eval` from the repo root — it must exit 0.

## Files in this pack

```
local-rag/  (this repo, P1 files)
├── src/local_rag/
│   ├── hybrid.py      — BM25 + TF-IDF, RRF fusion, rerank, chunking
│   ├── answer.py      — cited extractive answers, gate, refusal check
│   ├── evaluate.py    — eval harness (`python -m local_rag.evaluate`)
│   ├── cli.py         — `ask` and `eval` commands (added)
│   └── config.py      — relevance threshold settings (added)
├── sample_corpus/     — 6 fictional firm docs (SAMPLE ONLY)
├── eval/              — test_set.json + results-2026-11-13.{json,md}
└── docs/
    ├── p1-rag-upgrade.md   — this file
    └── p1-demo-script.md   — 2–3 minute screen demo
```

## Guardrails (same as the plan)

- Sample / fictional data only. No real firm documents, no real client
  names, no real phone numbers in any demo.
- Decline beats inventing. A decline is a feature to show, not a bug.
- No live service. Demos are recorded; the sold version is the $750
  pilot with a human in the loop.
- No invented results. Every number above comes from the eval run in
  `eval/results-2026-11-13.json`, dated Nov 13 2026.
- No course or certificate purchase. Nothing here needs one.
