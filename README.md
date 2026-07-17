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
| `mainIdea.md` | Original motivation and use cases |
