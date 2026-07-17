"""FastAPI web UI for local-rag."""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from local_rag.digest import digest_item, fetch_recent_items, generate_daily_digest
from local_rag.ingest import ingest as run_ingest
from local_rag.memory import memory_count, query_memories, recent_memories, record_memory
from local_rag.query import query as run_query
from local_rag.spotlight import init_index as run_spotlight_init, search as run_spotlight_search
from local_rag.store import count_digest_items, count_spotlight_entries, get_digest_topics, get_stats

logger = logging.getLogger(__name__)

_HERE = Path(__file__).parent
templates = Jinja2Templates(directory=str(_HERE / "templates"))

# ── Globals for all templates ──────────────────────────────────────────────────


def _spotlight_chunks() -> int:
    try:
        return count_spotlight_entries()
    except Exception:
        return 0


templates.env.globals["spotlight_chunks"] = _spotlight_chunks

app = FastAPI(title="local-rag", version="0.1.0")


# ── Favicon ──────────────────────────────────────────────────────────────────


@app.get("/favicon.ico", response_class=HTMLResponse, include_in_schema=False)
async def favicon():
    """Inline SVG favicon — no external file needed."""
    return HTMLResponse(
        content='<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">'
        '<rect width="32" height="32" rx="6" fill="#14b8a6"/>'
        '<text x="16" y="23" text-anchor="middle" font-size="20" font-weight="bold" fill="white">R</text>'
        "</svg>",
        media_type="image/svg+xml",
    )


# ── Routes ───────────────────────────────────────────────────────────────────


@app.get("/", response_class=HTMLResponse)
async def search_page(request: Request):
    stats = get_stats()
    mc = memory_count()
    return templates.TemplateResponse(
        request,
        "index.html",
        {"results": None, "query_text": "", "stats": stats, "memory_count": mc},
    )


@app.post("/", response_class=HTMLResponse)
async def search_results(
    request: Request,
    query_text: str = Form(..., alias="q"),
    top_k: int = Form(5),
):
    stats = get_stats()
    mc = memory_count()
    try:
        results = run_query(query_text, top_k=top_k)
    except Exception as exc:
        logger.error("Query failed: %s", exc)
        return templates.TemplateResponse(
            request,
            "index.html",
            {"results": None, "query_text": query_text, "error": str(exc), "stats": stats, "memory_count": mc},
        )

    return templates.TemplateResponse(
        request,
        "index.html",
        {"results": results, "query_text": query_text, "top_k": top_k, "stats": stats, "memory_count": mc},
    )


@app.get("/memories", response_class=HTMLResponse)
async def memories_page(
    request: Request,
    q: str = Query(""),
    recent: bool = Query(True),
    top_k: int = Query(5),
):
    stats = get_stats()
    mc = memory_count()
    entries = []
    if q.strip():
        entries = query_memories(q.strip(), top_k=top_k)
    elif recent:
        entries = recent_memories(limit=top_k)

    return templates.TemplateResponse(
        request,
        "memories.html",
        {"entries": entries, "query_text": q, "recent": recent, "stats": stats, "memory_count": mc},
    )


@app.post("/memories", response_class=HTMLResponse)
async def add_memory(
    request: Request,
    text: str = Form(...),
    tags: str = Form(""),
):
    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []
    try:
        record_memory(text=text, source="web", tags=tag_list)
    except Exception as exc:
        logger.error("Failed to store memory: %s", exc)
        return templates.TemplateResponse(
            request,
            "memories.html",
            {"entries": recent_memories(), "query_text": "", "recent": True, "error": str(exc), "stats": get_stats(), "memory_count": memory_count()},
        )
    return RedirectResponse(url="/memories?recent=1", status_code=303)


@app.get("/status", response_class=HTMLResponse)
async def status_page(request: Request):
    stats = get_stats()
    mc = memory_count()
    return templates.TemplateResponse(
        request,
        "status.html",
        {"stats": stats, "memory_count": mc},
    )


@app.post("/ingest", response_class=HTMLResponse)
async def trigger_ingest(
    request: Request,
    paths: str = Form(""),
    repo: str = Form(""),
):
    result = None
    error = None
    try:
        if repo.strip():
            from local_rag.ingest import ingest_repo as run_ingest_repo
            result = run_ingest_repo(repo.strip())
        else:
            parsed = [Path(p.strip()) for p in paths.split(",") if p.strip()] if paths.strip() else None
            result = run_ingest(parsed)
    except Exception as exc:
        logger.error("Ingest failed: %s", exc)
        error = str(exc)

    stats = get_stats()
    mc = memory_count()
    return templates.TemplateResponse(
        request,
        "status.html",
        {"stats": stats, "memory_count": mc, "ingest_result": result, "ingest_error": error},
    )


# ── Spotlight routes ────────────────────────────────────────────────────────────


@app.get("/spotlight", response_class=HTMLResponse)
async def spotlight_page(request: Request):
    stats = get_stats()
    mc = memory_count()
    return templates.TemplateResponse(
        request,
        "spotlight.html",
        {"results": None, "query_text": "", "stats": stats, "memory_count": mc},
    )


@app.post("/spotlight", response_class=HTMLResponse)
async def spotlight_search(
    request: Request,
    q: str = Form(..., alias="q"),
    top_k: int = Form(5),
):
    stats = get_stats()
    mc = memory_count()
    try:
        results = run_spotlight_search(q.strip(), top_k=top_k)
    except Exception as exc:
        logger.error("Spotlight search failed: %s", exc)
        return templates.TemplateResponse(
            request,
            "spotlight.html",
            {
                "results": None,
                "query_text": q,
                "error": f"Search failed: {exc}",
                "stats": stats,
                "memory_count": mc,
            },
        )

    return templates.TemplateResponse(
        request,
        "spotlight.html",
        {"results": results, "query_text": q, "top_k": top_k, "stats": stats, "memory_count": mc},
    )


@app.post("/spotlight/init", response_class=HTMLResponse)
async def spotlight_init(request: Request):
    stats = get_stats()
    mc = memory_count()
    error = None
    init_result = None
    try:
        init_result = run_spotlight_init()
    except Exception as exc:
        logger.error("Spotlight init failed: %s", exc)
        error = f"Indexing failed: {exc}"

    return templates.TemplateResponse(
        request,
        "spotlight.html",
        {
            "results": None,
            "query_text": "",
            "stats": stats,
            "memory_count": mc,
            "init_result": init_result,
            "error": error,
        },
    )


# ── Digest routes ─────────────────────────────────────────────────────────────


@app.get("/digest", response_class=HTMLResponse)
async def digest_page(
    request: Request,
    topic: str = Query(""),
    importance: str = Query(""),
    days: int = Query(7),
    limit: int = Query(50),
):
    stats = get_stats()
    mc = memory_count()
    dc = count_digest_items()
    all_topics = get_digest_topics()

    items = fetch_recent_items(
        days=days,
        topic_filter=topic or None,
        importance_filter=importance or None,
    )
    items = items[:limit]

    return templates.TemplateResponse(
        request,
        "digest.html",
        {
            "items": items,
            "all_topics": all_topics,
            "active_topic": topic,
            "active_importance": importance,
            "days": days,
            "stats": stats,
            "memory_count": mc,
            "digest_count": dc,
        },
    )


@app.post("/digest", response_class=HTMLResponse)
async def add_digest_item(
    request: Request,
    text: str = Form(...),
    source_type: str = Form("article"),
    source: str = Form(""),
    url: str = Form(""),
    tags: str = Form(""),
):
    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []
    try:
        digest_item(
            text=text,
            source_type=source_type,
            source=source or source_type,
            url=url,
            tags=tag_list,
        )
    except Exception as exc:
        logger.error("Failed to store digest item: %s", exc)
        stats = get_stats()
        mc = memory_count()
        dc = count_digest_items()
        return templates.TemplateResponse(
            request,
            "digest.html",
            {
                "items": fetch_recent_items(days=7),
                "all_topics": get_digest_topics(),
                "active_topic": "",
                "active_importance": "",
                "days": 7,
                "stats": stats,
                "memory_count": mc,
                "digest_count": dc,
                "error": str(exc),
            },
        )
    return RedirectResponse(url="/digest", status_code=303)


@app.get("/digest/daily", response_class=HTMLResponse)
async def daily_digest_page(
    request: Request,
    days: int = Query(1),
    topic: str = Query(""),
    importance: str = Query(""),
):
    stats = get_stats()
    mc = memory_count()
    dc = count_digest_items()

    content = generate_daily_digest(
        days=days,
        topic_filter=topic or None,
        importance_filter=importance or None,
    )

    return templates.TemplateResponse(
        request,
        "digest_daily.html",
        {
            "digest_content": content,
            "days": days,
            "stats": stats,
            "memory_count": mc,
            "digest_count": dc,
        },
    )
