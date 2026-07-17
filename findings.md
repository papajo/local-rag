# Findings: Local RAG Stack on SIE

## Hardware target
- **Mac M5, 16GB unified memory**
- 16GB is the *floor* per SIE docs — small models work, large models force SSD swap
- Native install path: `pip install "sie-server[local]"` (uses MLX backend on Apple Silicon)

## SIE core facts (from research)
- OpenAI-compatible API: `/v1/embeddings`, `/v1/chat/completions`, `/v1/completions`, `/v1/responses`
- Python SDK: `pip install sie-sdk`
- TypeScript SDK: `npm install @superlinked/sie-sdk`
- 100+ models in catalog; load on demand with LRU eviction
- Telemetry is opt-out via `SIE_TELEMETRY_DISABLED=1` or `DO_NOT_TRACK=1`
- Apache 2.0 license
- Repo: github.com/superlinked/sie, 2.1k stars, active (latest release v0.6.19 2026-07-14)

## Model sizing on 16GB (verified claims)
| Model | RAM (approx) | Fits? |
|---|---|---|
| `all-MiniLM-L6-v2` (embed) | ~100MB | trivially |
| `bge-m3` (embed, multilingual) | ~2.3GB | yes |
| `cross-encoder/ms-marco-MiniLM-L-6-v2` (rerank) | ~100MB | trivially |
| `gliner_multi-v2.1` (extract) | ~500MB | yes |
| `granite-guardian-2b` (guard) | ~2GB | yes (4-bit) |
| `Qwen3-0.6B` / `1.7B` (generate) | ~1–3GB | yes (4-bit) |
| `Qwen3-4B` (generate) | ~3-5GB | yes solo, tight with others |
| `Qwen3-27B` (generate) | ~14GB 4-bit | possible solo only |

LRU eviction means SIE doesn't preload all models — only what's serving.

## Stage 1 stack choices

### Vector DB
- **LanceDB** chosen: file-based, zero-config, single `lancedb` package, persistent as Parquet. Perfect for local single-user. No server to run.
- Alternative considered: Qdrant (overkill for single-machine local), Chroma (works but LanceDB is more modern).
- Reconsider if: scale beyond 1M chunks on this machine.

### Chunking
- Start with **fixed-size sliding window: 512 tokens, 64 token overlap** with sentence-boundary snapping.
- Rationale: simple, fast, well-understood. We can swap in semantic chunking later.
- For markdown later: structure-aware (per-header) chunking — but not in Stage 1.

### Embedding model
- **`BAAI/bge-m3`** — 568-dim, multilingual, top-tier MTEB scores, ~2.3GB RAM
- Falls back to `all-MiniLM-L6-v2` (384-dim, 100MB) if RAM pressure

### Reranking
- `cross-encoder/ms-marco-MiniLM-L-6-v2` (default)
- Optional later: `BAAI/bge-reranker-v2-m3` for multilingual coverage

### Persistence
- LanceDB stores vectors as Parquet — human-readable, no lock-in
- Metadata as columns in the same table
- Ingest state (file hashes) in a small SQLite or JSON file

### Supported file types (Stage 1)
- `.md`, `.txt` (trivial)
- `.pdf` (text extraction via `pypdf` or `pdfplumber`)
- `.docx` (via `python-docx`)
- (Optional later: `.epub`, `.html`, `.rtf`)

## Things deliberately deferred
- OCR (PDFs that are scanned images) — Stage 2+
- Code-aware chunking — Stage 2
- File-watcher / auto-ingest — Stage 2 (manual + scheduled in Stage 1)
- Multi-user / auth — not needed
- Distributed / cloud — explicitly out of scope
- Telemetry — opt out via env var

## Open questions (to resolve during build)
1. Should we ingest `~/Documents` recursively by default, or require explicit folder config? (Default + whitelist pattern seems safest)
2. PDF strategy: extract text only first; if PDF has <100 chars/page, treat as scan and skip (with warning)?
3. CLI UX: simple `query` subcommand, or also `ingest`, `status`, `reindex`, `serve` subcommands?
4. Re-ingest cost: first run on a large `~/Documents` could take hours. Background it? Progress bar? Cache aggressively?
</content>
</invoke>