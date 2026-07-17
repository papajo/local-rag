# OKF — OpenSpec Knowledge File: local-rag

This document serves as the central knowledge graph, architectural summary, and operational manual for the `local-rag` project.

---

## 1. Architectural Map

```
                  ┌──────────────────────────────────────────────┐
                  │                 local-rag CLI                │
                  │   (Ingest, Query, Spotlight, Digest, Memory)  │
                  └─────────┬───────────────┬────────────────────┘
                            │               │
         LanceDB Chunks &   │               │ HTTP Requests
         Memories Tables    │               │ (bge-m3, ms-marco-MiniLM,
                            ▼               ▼  gliner_multi-v2.1)
                  ┌───────────┐   ┌──────────────────────────────┐
                  │  LanceDB  │   │          sie-server          │
                  │ (Parquet) │   │ (MPS/CUDA Inference engine)  │
                  └───────────┘   └──────────────────────────────┘
```

The system runs locally and uses the following model pipeline:
1. **Embedding**: `BAAI/bge-m3` (1024-dim dense vectors) for primary document retrieval.
2. **Reranking**: `cross-encoder/ms-marco-MiniLM-L-6-v2` or `BAAI/bge-reranker-v2-m3` for precision sorting.
3. **Entity Extraction / Topic Classification**: `urchade/gliner_multi-v2.1` via MessagePack endpoints.
4. **Lightweight Ingest (Spotlight)**: `sentence-transformers/all-MiniLM-L6-v2` (384-dim dense vectors) for low-overhead filesystem search.
5. **Generation / Chat**: `prism-ml/Bonsai-27B-mlx-1bit` (1-bit quantized MLX version based on Qwen3.6-27B) for high-performance 27B-class reasoning on macOS (uses ~3.9GB RAM).

---

## 2. Issues Audited & Resolved

Under the OpenSpec change proposal `fix-config-and-port-defaults`, we implemented three core fixes:

### 2.1 Default Light Embedding Model Fix
- **Problem**: Default was set to `"all-MiniLM-L6-v2"`, causing `404 Not Found` responses from the `sie-server` which registers the model under the HuggingFace repository namespace: `"sentence-transformers/all-MiniLM-L6-v2"`.
- **Solution**: Updated `LIGHT_EMBED_MODEL` in `config.py` to the correct namespace.

### 2.2 Spotlight Watch Paths Fallback
- **Problem**: The `spotlight watch` command fell back to `settings.scan_dirs` instead of `settings.spotlight_scan_dirs`, rendering the filesystem watcher unable to monitor Downloads or Desktop paths by default.
- **Solution**: Fixed the fallback assignment in `cli.py`.

### 2.3 Web Server Port Conflict
- **Problem**: Both `local-rag serve` and `sie-server` defaulted to port `8080`, leading to a socket binding collision on startup.
- **Solution**: Changed the default FastAPI web UI server port to `9000`.

---

## 3. Local Model Customizations (Apple Silicon MLX)

To support ultra-lightweight high-performance generation on Mac machines with 16GB RAM:
1. **Model Configuration**: We created the `prism-ml__Bonsai-27B-mlx-1bit.yaml` model definition file in the `sie-server` packages path.
2. **MLX Integration**: Configured `mlx_repo: prism-ml/Bonsai-27B-mlx-1bit` to leverage Apple MLX 1-bit quantized inference natively on macOS MPS backend (memory footprint ~3.9 GB RAM).
3. **Reasoning Settings**: Added `enable_thinking: false` under `chat_template_kwargs` and registered `reasoning_parser: qwen3`.
4. **Usage Guideline**: Because Bonsai-27B (derived from Qwen3.6-27B) is a reasoning-centric model, it writes out a thought process before outputting answers. Queries must be run with a token limit of at least **512 tokens** (preferably `1024`) to give the model enough headroom to complete its thoughts and populate the final response body.

