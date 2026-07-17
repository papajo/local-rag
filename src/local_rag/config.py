"""Central configuration for the local RAG stack."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

# ── Project root ────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATA_DIR = PROJECT_ROOT / "data"

# ── SIE server ──────────────────────────────────────────────────────────────
SIE_BASE_URL = os.getenv("SIE_BASE_URL", "http://127.0.0.1:8080")
EMBED_MODEL = os.getenv("LOCAL_RAG_EMBED_MODEL", "BAAI/bge-m3")
LIGHT_EMBED_MODEL = os.getenv("LOCAL_RAG_LIGHT_EMBED_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
RERANK_MODEL = os.getenv("LOCAL_RAG_RERANK_MODEL", "cross-encoder/ms-marco-MiniLM-L-6-v2")
EXTRACT_MODEL = os.getenv("LOCAL_RAG_EXTRACT_MODEL", "urchade/gliner_multi-v2.1")

# ── Chunking ────────────────────────────────────────────────────────────────
CHUNK_MAX_TOKENS = int(os.getenv("LOCAL_RAG_CHUNK_TOKENS", "512"))
CHUNK_OVERLAP_TOKENS = int(os.getenv("LOCAL_RAG_CHUNK_OVERLAP", "64"))

# ── Retrieval ────────────────────────────────────────────────────────────────
VECTOR_TOP_K = int(os.getenv("LOCAL_RAG_VECTOR_TOP_K", "50"))
FINAL_TOP_K = int(os.getenv("LOCAL_RAG_FINAL_TOP_K", "5"))

# ── Smart Spotlight (Stage 5) ─────────────────────────────────────────────────
# Lightweight model & dimension for the always-on background indexer
SPOTLIGHT_EMBED_DIM = int(os.getenv("LOCAL_RAG_SPOTLIGHT_DIM", "384"))
SPOTLIGHT_TABLE = os.getenv("LOCAL_RAG_SPOTLIGHT_TABLE", "spotlight")
# Default paths scanned by the spotlight indexer
SPOTLIGHT_SCAN_DIRS: list[Path] = [
    Path.home() / "Documents",
    Path.home() / "Desktop",
    Path.home() / "Downloads",
]
# Directories skipped when walking spotlight scan paths
SPOTLIGHT_SKIP_DIRS: set[str] = {
    "node_modules", ".git", ".svn", "__pycache__", ".venv", "venv",
    ".next", ".turbo", "build", "dist", "target", ".build",
    ".cache", ".npm", ".yarn", "coverage", ".coverage",
    "tmp", "temp", "logs", ".trash", ".Trash", "Library",
}

# ── Deduplication ────────────────────────────────────────────────────────────
# Cosine similarity threshold for semantic dedup (0.0–1.0).
# Chunks above this threshold are considered duplicates and get source-attributed
# to the existing chunk rather than stored separately.
DEDUP_THRESHOLD = float(os.getenv("LOCAL_RAG_DEDUP_THRESHOLD", "0.95"))

# ── Ingestion ────────────────────────────────────────────────────────────────
# Default folders to scan when no explicit paths are given
DEFAULT_SCAN_DIRS: list[Path] = [
    Path.home() / "Documents",
]
# File extensions to consider
SUPPORTED_EXTENSIONS: set[str] = {".pdf", ".md", ".txt", ".docx", ".py", ".pyi", ".rs", ".ts", ".tsx", ".js", ".go", ".java", ".yaml", ".yml", ".toml", ".json", ".sql"}

# ── Code repo scanning (Stage 2) ─────────────────────────────────────────────
# Directories skipped when indexing a code repository (build output, test dirs, etc.)
CODE_SKIP_DIRS: set[str] = {
    # Build / output
    "build", "dist", "target", "out", "_build", "bin", "obj",
    "node_modules", ".next", ".turbo", "public/build",
    # Test directories (too granular; test code is indexed separately)
    "__tests__", "__test__", "tests", "test", "spec", "specs",
    "integration", "integration-test", "e2e",
    # Coverage / reports
    "coverage", ".coverage", "htmlcov", ".nyc_output",
    # Docs / generated
    "docs", "apidoc", "site", ".docusaurus",
    # Type stubs
    "typings", "types", "@types",
    # Misc
    ".cache", "tmp", "temp", "logs",
}

MAX_SCAN_DEPTH = int(os.getenv("LOCAL_RAG_MAX_DEPTH", "10"))
# Max file size in bytes — skip files larger than this (default: 10 MB)
MAX_FILE_SIZE_BYTES = int(os.getenv("LOCAL_RAG_MAX_FILE_SIZE", str(10 * 1024 * 1024)))

# Ingest state database (SQLite for file hashes)
INGEST_STATE_DB = DEFAULT_DATA_DIR / "ingest_state.db"

# ── Newsletter / Paper Digestor (Stage 4) ────────────────────────────────────
# Default topic labels for GLiNER zero-shot classification.
# Classified topics get grouped in the daily digest output.
DIGEST_TOPIC_LABELS = os.getenv(
    "LOCAL_RAG_DIGEST_TOPIC_LABELS",
    "machine learning,artificial intelligence,infrastructure,startups,ai safety,research,programming,tools,industry news",
)
# Importance labels for zero-shot classification.
DIGEST_IMPORTANCE_LABELS = os.getenv(
    "LOCAL_RAG_DIGEST_IMPORTANCE_LABELS",
    "important announcement,action required,routine update,low priority",
)
# How many days of digest items to keep in the table
DIGEST_DAYS_TO_KEEP = int(os.getenv("LOCAL_RAG_DIGEST_DAYS_TO_KEEP", "90"))
# Generative model for abstractive summarization (e.g. "Qwen/Qwen3.5-4B").
# Set to None or empty to use extractive fallback only.
DIGEST_SUMMARIZATION_MODEL = os.getenv("LOCAL_RAG_DIGEST_SUMMARIZATION_MODEL") or None


@dataclass
class Settings:
    """Runtime settings — writable so the CLI can override paths."""

    lancedb_dir: Path = DEFAULT_DATA_DIR / "lancedb"
    scan_dirs: list[Path] = field(default_factory=lambda: DEFAULT_SCAN_DIRS.copy())
    spotlight_scan_dirs: list[Path] = field(default_factory=lambda: SPOTLIGHT_SCAN_DIRS.copy())
    embed_model: str = EMBED_MODEL
    light_embed_model: str = LIGHT_EMBED_MODEL
    rerank_model: str = RERANK_MODEL
    extract_model: str = EXTRACT_MODEL
    chunk_max_tokens: int = CHUNK_MAX_TOKENS
    chunk_overlap_tokens: int = CHUNK_OVERLAP_TOKENS
    vector_top_k: int = VECTOR_TOP_K
    final_top_k: int = FINAL_TOP_K
    sie_base_url: str = SIE_BASE_URL
    dedup_threshold: float = DEDUP_THRESHOLD
    code_skip_dirs: set[str] = field(default_factory=lambda: set(CODE_SKIP_DIRS))
    digest_topic_labels: str = DIGEST_TOPIC_LABELS
    digest_importance_labels: str = DIGEST_IMPORTANCE_LABELS
    digest_days_to_keep: int = DIGEST_DAYS_TO_KEEP
    digest_summarization_model: str | None = DIGEST_SUMMARIZATION_MODEL


# Singleton
_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
