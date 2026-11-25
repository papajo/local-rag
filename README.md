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
uv run local-rag eval   # 10-question test set; must exit 0
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

Notes: the demo runs with $0 and no server (TF-IDF is a stand-in for
the SIE embeddings so it runs anywhere). In production, swap the TF-IDF
scorer for the existing SIE embedding search — see
[`docs/p1-rag-upgrade.md`](docs/p1-rag-upgrade.md). The sample corpus
stays fictional; never replace it with real firm documents in this repo.
Demo script: [`docs/p1-demo-script.md`](docs/p1-demo-script.md).
