# CLAUDE.md — local-rag

## Stack
- Python 3.12+, managed with `uv`; package in `src/local_rag/`, CLI via Typer (`local-rag`)
- LanceDB vector store, local inference (via httpx), tiktoken chunking, pypdf
- Web UI: FastAPI + Jinja2 + uvicorn

## Commands
```
uv sync                                 # install deps
uv run local-rag ingest [PATH]          # incremental, hash-tracked ingest
uv run local-rag ingest-repo <repo>     # code-aware ingest
uv run local-rag query "question"
uv run local-rag status
```

## Conventions
- Nothing leaves the machine: no hosted APIs for embeddings or generation.
- Ingest is idempotent (SHA-256 file hashes in SQLite); keep it that way.
- Full reference: `instructions.md`; motivation: `docs/mainIdea.md`; working notes: `docs/notes/`.
