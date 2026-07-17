# Known Issues & Resolutions

## Generation desync after LanceDB reset

**Symptoms:** `chunks.lance` was deleted (manually or by a cleanup script) but
`ingest_state.db` still has old file hashes. Next `local-rag ingest` re-processes
everything from scratch.

**Root cause:** LanceDB's internal generation counter increments on every write.
When the table is recreated from scratch, the counter resets. The `rag_generation`
file on disk and the value in `ingest_state.db` then disagree, triggering a full
re-index.

**Resolution (automatic):** The `_check_generation()` function detects the
mismatch on startup, prints a yellow warning, wipes `ingest_state`, and
re-syncs both sides to the current generation. No manual intervention needed.

**Resolution (manual):** To force a clean reset and skip the one-time re-index cost:

```bash
rm -rf data/lancedb data/ingest_state.db
local-rag ingest
```

---

## Reranker unavailable

**Symptoms:** Query results fall back to vector-distance sorting (no reranking).
Score shown is `vector_score` instead of `rerank_score`.

**Root cause:** The Sie server is down or unreachable at `SIE_BASE_URL`. The
cross-encoder reranker can't be called.

**Resolution:** Start Sie:

```bash
sie --host 127.0.0.1 --port 8080
```

---

## Reranker score is always -11.44

**Symptoms:** All query results show `rerank_score = -11.44`.

**Root cause:** The cross-encoder returned a negative logit for every candidate,
meaning it considers none of them relevant to the query. This is normal behavior,
not a bug.

**Resolution:** None needed. The CLI falls back to displaying `vector_score`
when the reranker score is negative.

---

## `local-rag query --extract` fails with `UnicodeDecodeError`

**Symptoms:** Entity extraction crashes with a Unicode decode error.

**Root cause:** The Sie `/v1/extract/` endpoint may not be running or the
response format is unexpected. Likely GLiNER model not loaded on the Sie server.

**Resolution:** Check Sie is started with the GLiNER model loaded. Verify with
a direct call to `http://127.0.0.1:8080/v1/extract/`.

---

## Schema errors on existing table

**Symptoms:** LanceDB throws schema mismatch errors on an existing table.

**Root cause:** Upgraded from an older version that lacked `source_refs` or
`metadata` columns. The table schema is frozen at creation time.

**Resolution:** Drop the table and re-ingest:

```bash
rm -rf data/lancedb
local-rag ingest
```

---

## PDF extraction warnings

**Symptoms:** `Ignoring wrong pointing object 23 0 (offset 0)` messages during
ingest.

**Root cause:** Some PDFs have malformed internal cross-reference tables that
`pypdf` warns about.

**Resolution:** These warnings are harmless. The fallback extractor
(`pypdfium2`) is used automatically when `pypdf` fails.
