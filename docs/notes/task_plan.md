# Task Plan: Local RAG Stack on SIE

## Goal
Build a fully-local, private RAG system using SIE (Superlinked Inference Engine) on an M5/16GB Mac, starting with a personal document search engine and evolving through codebase Q&A, agent memory, content triage, and smart Spotlight replacement.

## Current Phase
Stage 1 — **Complete**. The local RAG pipeline is built, installed, and verified with test data.
Stage 5 — **Implemented**. Smart Spotlight module, CLI commands, and docs are in place. (Stages 2–4 also complete.)
Next: Test spotlight end-to-end, then iterate on any stage.

## Roadmap (5 stages, each must be usable before moving on)

### Stage 1: Local RAG over `~/Documents`
Build a working, queryable index of the user's documents. CLI + Python REPL access. This is the foundation.

### Stage 2: Codebase Q&A
Point the same stack at a local git repo. Add code-aware chunking and a query interface for plain-English code questions.

### Stage 3: Agent semantic memory
Add a write-path: every conversation/note/snippet gets embedded and indexed. Other agents can query past context. Add the entity extractor for structured recall.

### Stage 4: Content triage / digestor
Use the structured-output model to classify and summarize incoming content (newsletters, papers, feeds). Add a daily-digest output.

### Stage 5: Smart Spotlight (optional)
Background indexer + semantic search across the home directory. Discoverable from any tool that speaks OpenAI-compatible embeddings.

---

## Stage 1 Phases (current focus)

### Phase 1.1: Requirements & Discovery
- [x] Confirm SIE fits M5/16GB hardware (done in research)
- [x] Confirm Python 3.12 is required (per SIE docs)
- [x] Identify which document formats to support initially
- [x] Decide on vector DB (Qdrant in-memory vs LanceDB file-based vs Chroma)
- [x] Decide on chunking strategy
- [x] Document scope in findings.md
- **Status:** complete

### Phase 1.2: Setup & Install
- [x] Verify Python 3.12 available (3.12.8 confirmed)
- [x] Create project venv
- [x] Install `sie-server[local]` and `sie-sdk`
- [x] Install `lancedb`, `pypdf`, `tiktoken`, `typer`, `rich`
- [x] Start SIE server, verify `/readyz`
- [x] Smoke test: embed a single string
- **Status:** complete

### Phase 1.3: Ingestion Pipeline
- [x] Build a walker that finds docs in `~/Documents` (and any other configured folders)
- [x] Support: `.pdf`, `.md`, `.txt`, `.docx` (and more — pluggable extractors)
- [x] Chunking strategy (sliding window, 512 tokens, 64 overlap)
- [x] Embed chunks via SIE `/v1/embeddings` using `bge-m3` with batch_size=64
- [x] Persist vectors + metadata to LanceDB
- [x] Make ingestion idempotent (hash-based skip via LanceDB merge)
- [x] SKIP_DIRS + hidden-dir filter to avoid venv/node_modules garbage
- **Status:** complete

### Phase 1.4: Query Pipeline
- [x] CLI: `local-rag query "..."` returns top-k with snippets + sources
- [x] Two-stage retrieval: embed → vector top-50 → rerank → top-5
- [ ] Optional: OpenAI-compatible HTTP server so any client (chat UIs, agents) can use it
- **Status:** complete (HTTP server deferred to later)

### Phase 1.5: Test & Verify
- [x] Ingest a small test folder (project's own .md files)
- [x] Run real queries, eyeball the top results
- [x] Document results in progress.md
- [x] Decide if Stage 1 is done → **YES, Stage 1 is usable**
- **Status:** complete

---

## Key Questions (Stage 1)
1. **Vector DB choice:** Qdrant (battle-tested, in-memory or on-disk), LanceDB (file-based, zero-config), or Chroma (simple, easy)? Trade-off: query speed vs. setup complexity.
2. **Chunking strategy:** Fixed-size (simple) vs. semantic (slower, better boundaries) vs. structure-aware for markdown (best for `.md`).
3. **Watch folders:** Just `~/Documents`, or also `~/Downloads`, `~/Notes`, etc.?
4. **Update strategy:** Manual re-ingest, file-watcher (watchdog), or scheduled cron?
5. **Persistence format:** Plain LanceDB/Parquet files (human-readable, durable) vs SQLite (familiar, queryable)?

## Decisions Made
| Decision | Rationale |
|----------|-----------|
| Use SIE for inference | User-confirmed fit for M5/16GB; OpenAI-compatible API; on-demand model loading fits unified memory |
| Embed with `bge-m3` (~2.3GB) | Best MTEB score in the small-model tier; multilingual (handles mixed docs); 568-dim vectors |
| Rerank with `ms-marco-MiniLM-L-6-v2` | Tiny (~100MB), standard choice, two-stage retrieval pattern |
| Native install (`pip install sie-server[local]`) | No Docker overhead; uses MLX backend on Apple Silicon; matches user's hardware |
| Start with Stage 1 only | Smallest end-to-end win, validates the stack, foundation for stages 2-5 |
| Skip OCR / Doc-to-MD in Stage 1 | PDF text extraction only; OCR can be added when/if needed in later stages |

## Errors Encountered
| Error | Attempt | Resolution |
|-------|---------|------------|
| `pydantic_to_schema()` receives dataclass, not BaseModel | Replaced with manual `pa.struct()` schema | Use `pa.struct()` with explicit field types |
| `create_scalar_index("id", "hash")` — index_type "hash" not supported in lancedb 0.18 | Removed call | Not needed for `merge_insert` upsert by primary key |
| SIE `/v1/embeddings` returns 503 on large single batch (3000+ tokens) | Added `batch_size=64` loop in `embed_texts()` | Batches of 64 pass cleanly; batch_size is configurable in config.py |
| `walk_docs()` descending into `.venv/Lib/site-packages/` | Maintained `SKIP_DIRS` set + hidden-dir filter | Set-based O(1) check against dir basename; hidden filter catches .venv, .git, etc. |

## Notes
- After each phase, update status: `pending` → `in_progress` → `complete`
- Re-read this plan before deciding on libraries, structures, or approach changes
- Log every error immediately, even if fixed
- Stage 1 must be **usable** (a real CLI that returns real results) before moving to Stage 2
- The user has a large `~/` with many project folders — be careful about what we index
</content>
</invoke>