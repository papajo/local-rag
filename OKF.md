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
5. **Generation / Chat**: `Qwen/Qwen3.5-4B` (4-bit quantized MLX version) for high-performance reasoning on macOS (uses ~2.5 - 3.0GB RAM).

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

To support highly capable, low-overhead generation on Mac machines with 16GB RAM:
1. **Model Configuration**: We utilize the curated model definition `Qwen__Qwen3.5-4B.yaml` in the `sie-server` packages path.
2. **MLX Integration**: The server automatically maps `Qwen/Qwen3.5-4B` requests to the 4-bit quantized MLX version (`mlx-community/Qwen3.5-4B-4bit`) natively on macOS MPS backend (memory footprint ~2.5 - 3.0 GB RAM).
3. **Reasoning Settings**: Configured with `enable_thinking: false` under `chat_template_kwargs` to suppress internal thought parsing into the answer body, and registered `reasoning_parser: qwen3`.


