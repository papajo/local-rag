# Progress Log

## Session 1 — 2026-07-15

### Done
- Researched SIE on M5/16GB. **Verdict: worth installing** for embeddings + rerank + small extractors; full generation stack needs 32GB+.
- Brainstormed use cases; user picked "start at #1, move down" — i.e., Stages 1-5 in order, but #1 first.
- Created project at `~/Projects/local-rag`
- Wrote `task_plan.md` with the 5-stage roadmap
- Wrote `findings.md` with the model sizing matrix and Stage 1 design decisions
- Stack chosen: SIE + LanceDB + bge-m3 + ms-marco-MiniLM reranker

## Session 2 — 2026-07-15

### Done
- Installed all Python deps: `lancedb`, `pypdf`, `tiktoken`, `typer`, `rich` in `.venv`
- Created `src/local_rag/` package with full pipeline code:
  - `config.py` — Settings, chunking params, scan dirs, model names
  - `models.py` — DocumentChunk (dataclass), SearchResult
  - `store.py` — LanceDB wrapper with PyArrow schema (1024-dim fixed-size list)
  - `ingest.py` — Walker with SKIP_DIRS, PDF/MD/TXT/DOCX extraction, sliding-window chunking (512/64), SIE batch embedding (batch_size=64)
  - `query.py` — Two-stage: SIE embed → LanceDB cos-top-50 → SIE rerank → final 5
  - `cli.py` — Typer CLI with `ingest`, `query`, `status` commands
- `pyproject.toml` — metadata + pip-installable `local-rag` CLI entry point
- Verification: ingested 4 test files → 8 chunks → queried "What is the local RAG project about?" → got relevant results
- Fixes during smoke test:
  - `pydantic_to_schema()` fails on dataclass → manual PyArrow schema
  - `create_scalar_index("id", "hash")` not supported → removed (not needed)
  - SIE 503 on 3000+ batch → `embed_texts()` batches at 64
  - `walk_docs()` picked up `.venv` site-packages → `SKIP_DIRS` + hidden dir filter

### In progress
- Nothing — Phase 1.1 through 1.5 complete, Stage 1 fully working

### Next actions
1. Ingest `~/Documents` for real usage: `local-rag ingest ~/Documents`
2. (optional) Clear test data first: `rm -rf data/`
3. Stage 2: Codebase Q&A

### Test results
- `local-rag status` → 8 chunks, 4 files (findings.md, mainIdea.md, progress.md, task_plan.md)
- `local-rag query "What is the local RAG project about?"` → top result: *"Build a fully-local, private RAG system using SIE..."* (score 1.88, reranked from -4.3 vector score)

---

## Session 3 — 2026-07-17

### Done — Stage 5: Smart Spotlight

#### Code changes
- `config.py`:
  - Added `LIGHT_EMBED_MODEL` (all-MiniLM-L6-v2), `SPOTLIGHT_EMBED_DIM` (384), `SPOTLIGHT_TABLE`, `SPOTLIGHT_SCAN_DIRS`, `SPOTLIGHT_SKIP_DIRS` constants
  - Added `light_embed_model` and `spotlight_scan_dirs` fields to Settings dataclass

- `models.py`:
  - Added `SpotlightEntry` dataclass (minimal: id, text, file_path, source, chunk_index, total_chunks, file_hash, embedding)

- `store.py`:
  - Added spotlight table functions: `_spotlight_schema`, `_get_spotlight_table`, `store_spotlight_chunks`, `search_spotlight`, `count_spotlight_entries`, `delete_spotlight_file`
  - Uses 384-dim FixedSizeList for the light embedding model

- `spotlight.py` (new module):
  - `_file_hash()` — SHA-256 for idempotency
  - `_should_skip()` — skips hidden files, unsupported extensions, >5 MB files
  - `_read_file()` — reads PDF/DOCX via existing ingest helper, plain text otherwise
  - `_chunk_text()` — token-bounded chunking with overlap (384 tokens, 32 overlap)
  - `_embed()` — embeds via SIE `/v1/embeddings` using `all-MiniLM-L6-v2`
  - `_get_existing_hashes()` — reads existing hashes from spotlight table
  - `init_index()` — walks `SPOTLIGHT_SCAN_DIRS` (~/Documents, ~/Desktop, ~/Downloads), chunks, embeds, stores; skips unchanged files via hash
  - `search()` — embed query → vector top-k×4 → cross-encoder rerank → sorted results
  - `status()` — returns total chunk count
  - `_reindex_file()` — re-indexes a single file on change (for the file watcher)

- `cli.py`:
  - Added `spotlight` command group with:
    - `spotlight init [PATHS...]` — build/refresh the spotlight index
    - `spotlight search <TEXT>` — semantic search with score table
    - `spotlight status` — show index statistics
    - `spotlight watch [PATHS...]` — file watcher (requires `watch` extra)

- `pyproject.toml`:
  - Added `[project.optional-dependencies] watch = ["watchdog>=6.0"]`

#### Design decisions
- **Separate table** (384-dim `spotlight`) from main chunks (1024-dim) — keeps the main pipeline unaffected
- **all-MiniLM-L6-v2** for speed (tiny model, fast embedding)
- **Cross-encoder rerank** shares the same `ms-marco-MiniLM-L-6-v2` model as the main pipeline
- **Size cap** of 5 MB — spotlight is meant for fast ad-hoc search, not full batch ingest
- **File watcher** with watchdog, but in an optional dependency group (not everyone needs it)

### Next actions
1. Test: sink the SIE server with `all-MiniLM-L6-v2`, run `local-rag spotlight init`
2. Test: `local-rag spotlight search "some query"` and verify reranking works
3. Test: `local-rag spotlight watch` with real file changes
</content>
</invoke>