# Local RAG — Operation & Maintenance

## Overview

`local-rag` is a CLI tool for private, local semantic search over your documents.
It ingests files, chunks them, computes embeddings via a local SIE (Superlinked
Inference Engine) server, stores vectors in LanceDB, and serves queries with
optional reranking and entity extraction.

---

## Architecture

```
Your files  ──→  ingest pipeline  ──→  LanceDB (vector store)
                                              │
User query  ──→  embed → vector search ──────┤
                           │                   
                    rerank (cross-encoder)      
                           │                   
                    top-k results              
                           │                   
                 (optional) entity extraction  
```

**Three-tier pipeline:**
1. **Embedding** — `BAAI/bge-m3` (1024-dim) via SIE `/v1/embeddings`
2. **Vector search** — cosine similarity in LanceDB
3. **Reranking** — `cross-encoder/ms-marco-MiniLM-L-6-v2` via SIE `/v1/rerank`

All ML inference runs on the Sie server (separate process). The `local-rag` tool
itself is a lightweight orchestrator that calls Sie's HTTP API.

---

## Prerequisites

- Python ≥ 3.12
- uv (fast Python package manager)
- A running Sie server at `http://127.0.0.1:8080` (or `SIE_BASE_URL` env var)

---

## Setup

### 1. Virtual environment

```bash
uv venv .venv
source .venv/bin/activate
```

### 2. Install dependencies

```bash
uv sync
```

### 3. Start the SIE server

SIE (Superlinked Inference Engine, <https://github.com/superlinked/sie>) is an
open-source, self-hosted inference server that serves HuggingFace models behind
an OpenAI-compatible HTTP API. This project uses it for three model types:

| Model | Purpose | Endpoint |
|---|---|---|
| `BAAI/bge-m3` (1024-dim) | Embedding text chunks & queries | `POST /v1/embeddings` |
| `cross-encoder/ms-marco-MiniLM-L-6-v2` | Reranking search results | `POST /v1/rerank` |
| `urchade/gliner_multi-v2.1` | Entity extraction from results | `POST /v1/extract/{model}` |

All three are built-in — no custom YAML configs needed. Models load on first
request, so the first call will be slow (downloads weights from HuggingFace).

**Important:** The SIE `default` bundle loads **all** models including a LLM
(`Qwen/Qwen3.5-4B`, ~9 GB download) that `local-rag` doesn't use. Use the
`--models` flag to load only the three models you actually need:

**Install & start (Apple Silicon / Linux, Python 3.12):**

```bash
pip install "sie-server[local]"
sie-server serve --host 127.0.0.1 --port 8080 \
  --models BAAI/bge-m3,cross-encoder/ms-marco-MiniLM-L-6-v2,urchade/gliner_multi-v2.1
```

The `--models` flag skips the 9 GB LLM download — start time drops from minutes
to seconds. If the port is busy, pick a different one (e.g. `--port 8082`) and
set `SIE_BASE_URL` to match.

**Docker:**

```bash
docker run -p 8080:8080 \
  -e SIE_MODEL_FILTER=BAAI/bge-m3,cross-encoder/ms-marco-MiniLM-L-6-v2,urchade/gliner_multi-v2.1 \
  ghcr.io/superlinked/sie-server:latest-cuda12-default
```

**Verify it's running:**

```bash
curl -s http://127.0.0.1:8080/healthz | head -c 200
```

Without SIE, `ingest` and `query` will fail with `Connection refused` errors.

---

## CLI Commands

### Query

```bash
# Basic search (returns top 5 results)
local-rag query "your search query"

# Control result count
local-rag query "your search query" --top-k 3

# Raw output (machine-friendly)
local-rag query "your search query" --raw

# Extract entities from results (requires Sie extract endpoint)
local-rag query "your search query" --extract

# Custom entity labels for extraction
local-rag query "your search query" --extract --extract-labels "person,organization,technology"

# Choose a different GLiNER model for extraction
local-rag query "your search query" --extract --extract-model "urchade/gliner_multi-v2.1"

# Code-relevant entity labels (useful for repo Q&A)
local-rag query "explain the chunking logic" --extract --extract-labels "function,parameter,technology,class"
```

### Ingest

`local-rag ingest` is **idempotent** — it tracks file hashes (SHA-256) in
`data/ingest_state.db`. Running it again skips unchanged files and re-processes
only new or modified ones.

```bash
# Index default paths (~/Documents)
local-rag ingest

# Index specific files or directories
local-rag ingest /path/to/file.py /path/to/project/

# Re-index (file changes detected by SHA-256 hash)
local-rag ingest
```

### Ingest (code repo)

```bash
# Index a local git repo with code-appropriate chunking
local-rag ingest-repo ~/projects/my-repo

# Index a GitHub repo (shallow-cloned, cleaned up after)
local-rag ingest-repo https://github.com/user/repo
local-rag ingest-repo git@github.com:user/repo.git
```

### Status

```bash
local-rag status
```

Shows total chunk count, file count, indexed file names, and total memories.

---

## Personal Semantic Memory (Stage 3)

Record notes, decisions, and conversation snippets as personal memories. Each
memory is embedded, entity-extracted, and stored in a dedicated `memories` table
in LanceDB — searchable with the same pipeline architecture.

### Record a memory

```bash
# Record a quick note
local-rag remember "Decided to use LanceDB for vector storage — avoids extra infra dependencies."

# Record with tags for grouping
local-rag remember "Benchmarks show bge-m3 is 2x faster than gtr-large on M5" --tags "benchmark,embedding"

# Skip entity extraction for short/factual notes
local-rag remember "Team standup moved to 10am" --no-extract

# Record with a custom source label
local-rag remember "Perf: reranker adds ~50ms per query" --source "experiment"
```

### Search memories

```bash
# Semantic search — finds related memories by meaning
local-rag memory "what did I decide about vector stores?"

# Show extracted entities for each result
local-rag memory "why did we pick bge-m3" --entities

# Browse recent memories
local-rag memory "" --recent

# Control result count
local-rag memory "embedding strategies" --top-k 10

# Raw output (machine-friendly)
local-rag memory "M5 benchmarks" --raw
```

**How it works:**

1. **`remember`** → embeds the text via SIE `/v1/embeddings` → extracts entities
   via SIE `/v1/extract` → stores text, embedding, entities, tags, and timestamp
   in the `memories` LanceDB table.
2. **`memory`** → embeds the query → vector search in `memories` table →
   optionally reranks via SIE `/v1/rerank` → returns results sorted by relevance.

Memories live in `data/lancedb/memories.lance` alongside the document chunks.

---

## Web UI

`local-rag` includes a FastAPI web interface for searching documents, browsing
memories, and managing the index from a browser.

### Start the server

```bash
# Launch on the default address (127.0.0.1:8080)
local-rag serve

# Custom host/port
local-rag serve --host 0.0.0.0 --port 9000

# Auto-reload on code changes (development)
local-rag serve --reload
```

### Pages

| Route | Description |
|---|---|
| `/` | Search documents — enter a query, see results with scores and entity tags |
| `/memories` | Browse recent memories, search semantically, or record new ones |
| `/status` | Index statistics, file list, and an inline form to trigger re-ingest |

The sidebar shows chunk/file/memory counts at a glance.

---

## Score Interpretation

Results display one of two scores:

| Score field | Range | Meaning |
|---|---|---|
| `rerank_score` | > 0 (shown) | Relevance score from cross-encoder (higher = more relevant) |
| `vector_score` | 0–1 (shown) | Cosine *distance* from query vector (lower = more similar) |

A negative `rerank_score` (−11.44 etc.) means the reranker considers the
document not relevant — the CLI falls back to `vector_score` for display.

If the Sie reranker is unreachable, results are sorted by vector distance
(the default fallback).

---

## Newsletter / Paper Digestor (Stage 4)

Classify, summarize, and export newsletters, articles, and papers. Each item
is classified by topic and importance (zero-shot via GLiNER), extracted for
entities, and optionally abstractively summarized if a generative LLM is
loaded on the Sie server.

### Add an item

```bash
local-rag digest add "text content here" --type newsletter --source "TLDR AI" --url "https://..."
```

```bash
# With tags
local-rag digest add "Article text..." --type article --source "ArXiv" --tags "transformer,attention"
```

### List items

```bash
# Recent 20 items
local-rag digest list

# Filter by topic
local-rag digest list --topic "machine learning"

# Filter by importance
local-rag digest list --importance high

# Only last 7 days
local-rag digest list --days 7

# Rich table output
local-rag digest list --table
```

### Generate daily digest

```bash
# Today's items in a formatted Markdown report
local-rag digest daily

# Last 7 days, filtered by topic
local-rag digest daily --days 7 --topic "infrastructure"

# Export to a .md file
local-rag digest daily --days 7 --export
```

Exports go to `data/digests/digest-YYYY-MM-DD.md`.

### Web UI

| Route | Description |
|---|---|
| `/digest` | Browse, filter, and add digest items |
| `/digest/daily` | View a rendered daily digest |

### How it works

1. **`digest add`** — embeds text → classifies topics (GLiNER zero-shot) →
   classifies importance → extracts entities → optionally summarizes via LLM
   → stores in the `digest` LanceDB table.
2. **`digest daily`** — fetches recent items → groups by topic → formats as
   Markdown → prints or exports.
3. **Topic classification** uses the same GLiNER model as entity extraction
   (`urchade/gliner_multi-v2.1`) — each configured topic label is treated as
   an entity type; matched labels become the item's topics.
4. **Abstractive summarization** uses SIE `/v1/chat/completions`. Set
   `LOCAL_RAG_DIGEST_SUMMARIZATION_MODEL` to a generative model (e.g.
   `Qwen/Qwen3.5-4B`) to enable it. Falls back to extractive (first ~600 chars)
   when no generative model is available.

---

## Smart Spotlight

Spotlight is a lightweight background indexer for always-on semantic search
across your home directory.  It uses a tiny embedding model
(all-MiniLM-L6-v2, 384-dim) to keep indexing fast and memory-efficient.

### Architecture

Spotlight uses a **separate LanceDB table** (`spotlight`, 384-dim) from the
main chunks table (1024-dim), so it doesn't interfere with the primary RAG
pipeline.

```
Your files  ──→  scan + chunk (384 tok, 32 overlap)  ──→  embed (all-MiniLM-L6-v2)
                                                                    │
                                                            LanceDB `spotlight`
                                                                    │
User query  ──→  embed (all-MiniLM-L6-v2)  ──→  vector search  ──┤
                                                                    │
                                                            rerank (cross-encoder)
                                                                    │
                                                            top-k results
```

### CLI Commands

#### Initialize / refresh the index

```bash
# Index default paths (~/Documents, ~/Desktop, ~/Downloads)
local-rag spotlight init

# Index specific paths
local-rag spotlight init ~/Documents ~/Projects/notes

# Re-run to index new/changed files (skips unchanged via SHA-256)
```

#### Search

```bash
# Simple search
local-rag spotlight search "meeting notes about Q3 planning"

# Custom result count
local-rag spotlight search "python async patterns" --top-k 10

# Raw score output (no rich formatting)
local-rag spotlight search "quantum computing" --raw
```

#### Index statistics

```bash
local-rag spotlight status
```

#### File watching (requires `watch` extra)

```bash
# Install watchdog first
uv sync --extra watch

# Watch default directories
local-rag spotlight watch

# Watch custom directories
local-rag spotlight watch ~/Documents ~/Desktop
```

Press Ctrl+C to stop the file watcher.

### How it works

1. **`spotlight init`** — walks `SPOTLIGHT_SCAN_DIRS` (~/Documents, ~/Desktop,
   ~/Downloads), reads each file, chunks at 384 tokens (32 overlap), embeds via
   SIE `/v1/embeddings` using `all-MiniLM-L6-v2`, and stores in the `spotlight`
   LanceDB table.
2. **Idempotency** — each file's SHA-256 hash is stored alongside its chunks.
   On subsequent runs, unchanged files are skipped.
3. **Eligibility** — files must be ≤5 MB, have a supported extension (.pdf,
   .md, .txt, .docx, .py, .rs, .ts, .tsx, .js, .go, .java, .yaml, .yml, .toml,
   .json, .sql, .c, .cpp, .h, .hpp, .swift, .kt, .rb, .php, .html, .css, .scss,
   .less), and not be in a skip directory (node_modules, .git, __pycache__, etc.).
4. **`spotlight search`** — embeds the query with the light model → retrieves
   `top_k × 4` candidates via cosine similarity → re-ranks with the cross-encoder
   (same `ms-marco-MiniLM-L-6-v2` model as the main pipeline) → returns the
   top-k results sorted by rerank score.
5. **`spotlight watch`** — uses `watchdog` to listen for file modifications and
   automatically re-indexes changed files.

### Environment Variables

| Variable | Default | Description |
|---|---|---|
| `LOCAL_RAG_LIGHT_EMBED_MODEL` | `all-MiniLM-L6-v2` | Embedding model for spotlight |
| `LOCAL_RAG_SPOTLIGHT_DIM` | `384` | Spotlight embedding dimension |
| `LOCAL_RAG_SPOTLIGHT_TABLE` | `spotlight` | LanceDB table name for spotlight |

---

## Configuration (Environment Variables)

| Variable | Default | Description |
|---|---|---|
| `SIE_BASE_URL` | `http://127.0.0.1:8080` | Sie server address |
| `LOCAL_RAG_EMBED_MODEL` | `BAAI/bge-m3` | Embedding model on Sie |
| `LOCAL_RAG_RERANK_MODEL` | `cross-encoder/ms-marco-MiniLM-L-6-v2` | Reranker model on Sie |
| `LOCAL_RAG_EXTRACT_MODEL` | `urchade/gliner_multi-v2.1` | NER model on Sie |
| `LOCAL_RAG_CHUNK_TOKENS` | `512` | Max tokens per chunk |
| `LOCAL_RAG_CHUNK_OVERLAP` | `64` | Overlap tokens between chunks |
| `LOCAL_RAG_VECTOR_TOP_K` | `50` | Candidate count from vector search |
| `LOCAL_RAG_FINAL_TOP_K` | `5` | Final result count after rerank |
| `LOCAL_RAG_DEDUP_THRESHOLD` | `0.95` | Cosine similarity for semantic dedup |
| `LOCAL_RAG_MAX_DEPTH` | `10` | Max directory scan depth |
| `LOCAL_RAG_MAX_FILE_SIZE` | `10485760` | Max file size in bytes |
| `LOCAL_RAG_DIGEST_TOPIC_LABELS` | `machine learning,artificial intelligence,infrastructure,...` | Comma-separated topic labels for GLiNER classification |
| `LOCAL_RAG_DIGEST_IMPORTANCE_LABELS` | `important announcement,action required,...` | Comma-separated importance labels for GLiNER |
| `LOCAL_RAG_DIGEST_DAYS_TO_KEEP` | `90` | Days to retain digest items |
| `LOCAL_RAG_DIGEST_SUMMARIZATION_MODEL` | (none) | Generative model for abstractive summarization (e.g. `Qwen/Qwen3.5-4B`) |

---

## Key Features

### Smart Code Chunking

Code files (.py, .rs, .ts, .go, .java, .sql) are chunked at function/class
boundary lines rather than by sliding window. Each chunk stays under
`CHUNK_MAX_TOKENS` but preserves declaration integrity.

Supported languages and their boundary patterns:

| Language | Extensions | Boundary markers |
|---|---|---|
| Python | .py, .pyi | `class`, `def`, `async def`, `@decorator` |
| Rust | .rs | `fn`, `struct`, `enum`, `trait`, `impl`, `mod` |
| TypeScript/JS | .ts, .tsx, .js | `export function`, `class`, `interface`, `type`, `const` |
| Go | .go | `func`, `type struct`, `type interface`, `const (` |
| Java | .java | `class`, `interface`, `enum`, method signatures |
| SQL | .sql | `CREATE`, `ALTER`, `DROP` |

### Semantic Deduplication

When ingesting, each chunk is compared against existing chunks using cosine
similarity. If a match exceeds `DEDUP_THRESHOLD`, the new chunk is recorded
as a **source reference** on the existing chunk rather than stored separately.
This allows tracking which files contain identical content without duplication.

Source references appear in query results as `source_refs` — a list of
`{source, file_path, chunk_ids}` dicts.

### Project Metadata

During ingestion, each file's nearest project-config ancestor is scanned for
metadata:

| Config file | Project type | Extracted fields |
|---|---|---|
| `pyproject.toml` | Python | name, version, dependencies |
| `Cargo.toml` | Rust | name, version, dependencies |
| `package.json` | JavaScript/Node | name, version, dependencies |
| `go.mod` | Go | module name, Go version, dependencies |
| `pom.xml` | Java/Maven | artifactId, version, dependencies |
| `Gemfile` | Ruby | name, gem dependencies |
| `CMakeLists.txt` | C++ | project name |

Metadata is attached to each chunk from the same file as a `metadata` JSON
field.

### Entity Extraction

With `local-rag query --extract`, result snippets are sent to Sie's GLiNER
endpoint for named-entity recognition. Default labels:
`person, organization, technology, product, location, date`.

Entity deduplication merges same-label,nearby-text entries keeping the
highest confidence score.

---

## Data Storage

All state lives under `data/` in the project root:

| Path | Purpose |
|---|---|
| `data/lancedb/` | LanceDB vector store (chunks + embeddings) |
| `data/ingest_state.db` | SQLite — tracks file hashes for idempotent re-ingest |
| `data/rag_generation` | Counter to detect LanceDB / ingest-state desync |

To reset the index:

```bash
rm -rf data/lancedb data/ingest_state.db
```

---

## Troubleshooting

### "Reranker unavailable" warning in logs
Sie is down or unreachable at `SIE_BASE_URL`. Results still work — they use
vector-distance fallback. Fix: start Sie.

### Score always shows `-11.44`
The cross-encoder returned a negative logit (document considered not relevant
to query). This is normal — the CLI now falls back to `vector_score`.

### `local-rag query --extract` returns empty entities
The default extraction labels (`person,organization,technology,product,location`)
are designed for documents, not code snippets. Use code-relevant labels instead:

```bash
local-rag query "your query" --extract --extract-labels "function,parameter,technology,class"
```

### Entity extraction always returns empty for code queries
Sie's `/v1/extract` endpoint returns MessagePack binary (`application/msgpack`),
not JSON. This is handled automatically — if you see extraction working in tests
but not in CLI output, the labels you're using don't match the content (see above).

### Schema errors on existing table
If you upgraded from an older version that lacked `source_refs` or `metadata`
columns, drop the table to force recreation:

```bash
rm -rf data/lancedb
```
Then re-ingest.

### Generation desync after table reset
If `chunks.lance` is deleted but `ingest_state.db` / `rag_generation` are
preserved, the next run auto-detects:

```
Generation mismatch (LanceDB gen=N, state gen=M). Resetting ingest state — all
files will be re-indexed.
```

The entire index is rebuilt once. Subsequent runs return to incremental
(skip-unchanged) behavior.

---

## Maintenance

### Adding a new supported file type

1. Add the extension to `SUPPORTED_EXTENSIONS` in `config.py`
2. Add extraction logic to `extract_text()` in `ingest.py`
3. If it's a code file, add boundary patterns in `_CODE_BOUNDARY_PATTERNS`
4. Optionally add a `_detect_code_lang()` mapping and config-file parser in
   `metadata.py`

### Adding a new config-file parser

1. Write a parser function in `metadata.py` registered with `@_register("filename")`
2. The function receives a `Path` and returns `dict[str, Any]` or `None`
3. The output is attached as the `metadata` field on every chunk from that project

### Adding a new entity label

Pass `--extract-labels` to `local-rag query`, or modify `DEFAULT_LABELS` in
`extract.py`.

---

## Python API

```python
from local_rag.ingest import ingest
from local_rag.query import query
from local_rag.store import search, get_stats

# Ingest documents
ingest(["/path/to/file.py"])

# Search
results = query("your question", top_k=5)

# Each result has: text, source, file_path, chunk_index, score,
#                  rerank_score, vector_score, entities, source_refs, metadata
```
