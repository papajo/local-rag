"""CLI interface for local-rag."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.markup import escape
from rich.table import Table

app = typer.Typer(
    name="local-rag",
    help="Private, local semantic search over your documents.",
    no_args_is_help=True,
)
console = Console()


@app.command()
def ingest(
    paths: list[Path] = typer.Argument(
        None,
        help="Files or directories to index (default: ~/Documents)",
        exists=False,
    ),
) -> None:
    """Index documents into the vector store."""
    from local_rag.ingest import ingest as run_ingest

    result = run_ingest(paths if paths else None)

    if result["chunks"] > 0:
        console.print(f"\n[green]✓ Indexed {result['chunks']} chunk(s) from {result['new']} file(s).[/]")
    elif result["found"] > 0:
        console.print("[yellow]Nothing new to index.[/]")
    else:
        console.print("[yellow]No documents found.[/]")


@app.command()
def query(
    text: str = typer.Argument(..., help="Search query"),
    top_k: int = typer.Option(5, "--top-k", "-k", help="Number of results"),
    raw: bool = typer.Option(False, "--raw", help="Show raw scores without rich formatting"),
    extract: bool = typer.Option(False, "--extract", "-e", help="Extract structured entities from results"),
    extract_labels: str = typer.Option(
        "person,organization,technology,product,location",
        "--extract-labels",
        help="Comma-separated entity labels for extraction (requires --extract)",
    ),
    extract_model: str | None = typer.Option(
        None,
        "--extract-model",
        help="GLiNER model for extraction (default: settings.extract_model)",
    ),
) -> None:
    """Search indexed documents."""
    from local_rag.query import query as run_query

    results = run_query(text, top_k=top_k)

    if not results:
        console.print("[yellow]No results found.[/]")
        raise typer.Exit()

    # ── Optional entity extraction ──────────────────────────────────────
    if extract:
        from local_rag.extract import DEFAULT_LABELS, extract_entities

        labels = [lbl.strip() for lbl in extract_labels.split(",")] if extract_labels else DEFAULT_LABELS

        with console.status("[dim]Extracting entities...[/]"):
            texts = [r.text for r in results]
            extraction_results = extract_entities(texts, labels=labels, model=extract_model)

        for r, er in zip(results, extraction_results):
            r.entities = er.entities

    # ── Display results ─────────────────────────────────────────────────
    if raw:
        for i, r in enumerate(results, 1):
            console.print(f"{i}. [score={r.score:.4f}] {r.source} (chunk {r.chunk_index})")
            console.print(escape(r.text[:200]) + "...")
            if extract and r.entities:
                by_label: dict[str, list[str]] = {}
                for e in r.entities:
                    by_label.setdefault(e.label, []).append(e.text)
                parts = [f"[dim]{lbl}:[/] {', '.join(vals[:5])}" for lbl, vals in by_label.items()]
                console.print("  [bold]Entities:[/] " + " | ".join(parts))
            console.print()
    else:
        table = Table(title=f"Top {len(results)} results")
        table.add_column("#", style="dim", width=3)
        table.add_column("Score", justify="right", width=8)
        table.add_column("Source", style="cyan")
        table.add_column("Snippet", style="white")

        for i, r in enumerate(results, 1):
            score_str = f"{r.rerank_score:.2f}" if r.rerank_score > 0.0 else f"{r.vector_score:.4f}"
            snippet = escape(r.text[:150].replace("\n", " "))
            table.add_row(str(i), score_str, r.source, snippet)

        console.print(table)

        # Print entities below the table if extracted
        if extract:
            any_entities = any(r.entities for r in results)
            if any_entities:
                console.print()
                console.print("[bold]Extracted Entities:[/]")
                for i, r in enumerate(results, 1):
                    if r.entities:
                        by_label: dict[str, list[str]] = {}
                        for e in r.entities:
                            by_label.setdefault(e.label, []).append(e.text)
                        parts = [f"[dim]{lbl}:[/] {', '.join(vals[:5])}" for lbl, vals in by_label.items()]
                        console.print(f"  #{i}: {' | '.join(parts)}")


@app.command()
def ingest_repo(
    path: str = typer.Argument(
        ...,
        help="Local path or GitHub URL (HTTPS/SSH) of a repository to index",
    ),
) -> None:
    """Index a code repository for code-aware Q&A.

    Accepts a local filesystem path or a GitHub URL (HTTPS or SSH).  GitHub
    repos are shallow-cloned to a temp directory which is cleaned up after
    indexing.

    Uses code-specific chunking (by function/class boundaries), skips
    test and build directories automatically, and extracts project
    metadata from pyproject.toml, Cargo.toml, package.json, etc.
    """
    from local_rag.ingest import ingest_repo as run_ingest_repo

    result = run_ingest_repo(path)
    if result["chunks"] > 0:
        console.print(f"\n[green]✓ Indexed {result['chunks']} chunk(s) from {result['new']} file(s).[/]")


@app.command()
def status() -> None:
    """Show index statistics."""
    from local_rag.store import get_stats

    stats = get_stats()
    console.print(f"[bold]Local RAG Index Status[/]")
    console.print(f"  Total chunks:  {stats['total_chunks']}")
    console.print(f"  Total files:   {stats['total_files']}")
    if stats["sources"]:
        console.print(f"\n  [dim]Indexed files:[/]")
        for s in stats["sources"]:
            console.print(f"    • {s}")

    # Memory stats
    from local_rag.memory import memory_count
    mc = memory_count()
    console.print(f"  Total memories: {mc}")


@app.command()
def remember(
    text: str = typer.Argument(..., help="The memory to record"),
    source: str = typer.Option("cli", "--source", help="Source label (cli, file, conversation, etc.)"),
    tags: str = typer.Option("", "--tags", "-t", help="Comma-separated tags"),
    no_extract: bool = typer.Option(False, "--no-extract", help="Skip entity extraction"),
) -> None:
    """Record a personal semantic memory."""
    from local_rag.memory import record_memory

    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []

    mid = record_memory(
        text=text,
        source=source,
        tags=tag_list,
        extract=not no_extract,
    )

    suffix = ""
    if tag_list:
        suffix = f" ({', '.join(tag_list)})"
    console.print(f"[green]✓ Stored memory {mid[:8]}…[/]{escape(suffix)}")


@app.command()
def memory(
    text: str = typer.Argument(..., help="Search query for memories"),
    top_k: int = typer.Option(5, "--top-k", "-k", help="Number of results"),
    raw: bool = typer.Option(False, "--raw", help="Show raw scores"),
    recent: bool = typer.Option(False, "--recent", "-r", help="Show recent memories instead of searching"),
    show_entities: bool = typer.Option(False, "--entities", "-e", help="Show extracted entities for each memory"),
) -> None:
    """Search or browse personal semantic memories."""
    from local_rag.memory import query_memories, recent_memories

    if recent:
        results = recent_memories(limit=top_k)
    else:
        results = query_memories(text, top_k=top_k)

    if not results:
        console.print("[yellow]No memories found.[/]")
        raise typer.Exit()

    if raw:
        for i, m in enumerate(results, 1):
            console.print(f"{i}. [{m.timestamp}] ({m.source})")
            console.print(escape(m.text[:300]))
            if show_entities and m.entities:
                by_label: dict[str, list[str]] = {}
                for e in m.entities:
                    by_label.setdefault(e.label, []).append(e.text)
                parts = [f"[dim]{lbl}:[/] {', '.join(vals[:5])}" for lbl, vals in by_label.items()]
                console.print("  [bold]Entities:[/] " + " | ".join(parts))
            if m.tags:
                console.print(f"  [dim]Tags:[/] {', '.join(m.tags)}")
            console.print()
    else:
        for i, m in enumerate(results, 1):
            timestamp = m.timestamp[:19].replace("T", " ")
            header = f"[bold]#{i}[/] [dim]{timestamp}[/] [cyan]({m.source})[/]"
            if m.tags:
                header += f" [yellow]{', '.join(m.tags)}[/]"
            console.print(header)
            console.print(f"  {escape(m.text[:200])}")
            if show_entities and m.entities:
                by_label = {}
                for e in m.entities:
                    by_label.setdefault(e.label, []).append(e.text)
                parts = [f"[dim]{lbl}:[/] {', '.join(vals[:5])}" for lbl, vals in by_label.items()]
                console.print(f"  [bold]Entities:[/] {' | '.join(parts)}")
            console.print()


# ── Spotlight commands ─────────────────────────────────────────────────────────

spotlight_app = typer.Typer(
    name="spotlight",
    help="Lightweight background indexer for always-on semantic search.",
    no_args_is_help=True,
)
app.add_typer(spotlight_app)


@spotlight_app.command()
def init(
    paths: list[Path] = typer.Argument(
        None,
        help="Files or directories to index (default: ~/Documents, ~/Desktop, ~/Downloads)",
        exists=False,
    ),
) -> None:
    """Build or refresh the spotlight index."""
    from local_rag.spotlight import init_index as run_init

    with console.status("[dim]Indexing files…[/]"):
        result = run_init(paths if paths else None)

    if result["chunks"] > 0:
        console.print(f"\n[green]✓ Indexed {result['chunks']} chunk(s) from {result['new_files']} file(s).[/]")
    if result["errors"] > 0:
        console.print(f"[yellow]Completed with {result['errors']} error(s).[/]")
        if result["chunks"] == 0:
            console.print("[dim]  → Ensure SIE is running: [bold]uv run sie[/bold][/]")
            console.print("[dim]  → Run with [bold]--log-level DEBUG[/bold] to see individual errors[/]")
    if result["skipped_files"] > 0:
        console.print(f"[dim](Skipped {result['skipped_files']} unchanged or unsupported files.)[/]")


@spotlight_app.command()
def search(
    text: str = typer.Argument(..., help="Search query"),
    top_k: int = typer.Option(5, "--top-k", "-k", help="Number of results"),
    raw: bool = typer.Option(False, "--raw", help="Show raw scores without rich formatting"),
) -> None:
    """Semantic search across the spotlight index."""
    from local_rag.spotlight import search as run_search

    results = run_search(text, top_k=top_k)

    if not results:
        console.print("[yellow]No results found. Run `local-rag spotlight init` first.[/]")
        raise typer.Exit()

    if raw:
        for i, r in enumerate(results, 1):
            score_str = f"{r.rerank_score:.2f}" if r.rerank_score > 0.0 else f"{r.vector_score:.4f}"
            console.print(f"{i}. [score={score_str}] {r.source} (chunk {r.chunk_index})")
            console.print(escape(r.text[:200]) + "...")
            console.print()
    else:
        table = Table(title=f"Spotlight — Top {len(results)} results")
        table.add_column("#", style="dim", width=3)
        table.add_column("Score", justify="right", width=8)
        table.add_column("Source", style="cyan")
        table.add_column("Snippet", style="white")
        for i, r in enumerate(results, 1):
            score_str = f"{r.rerank_score:.2f}" if r.rerank_score > 0.0 else f"{r.vector_score:.4f}"
            snippet = escape(r.text[:150].replace("\n", " "))
            table.add_row(str(i), score_str, r.source, snippet)
        console.print(table)


@spotlight_app.command()
def status() -> None:
    """Show spotlight index statistics."""
    from local_rag.spotlight import status as spotlight_status

    stats = spotlight_status()
    console.print("[bold]Spotlight Index Status[/]")
    console.print(f"  Total chunks:  {stats['total_chunks']}")
    if stats["total_chunks"] == 0:
        console.print("[yellow]  (Run `local-rag spotlight init` to build the index.)[/]")


@spotlight_app.command()
def watch(
    paths: list[Path] = typer.Argument(
        None,
        help="Directories to watch (default: spotlight scan dirs)",
        exists=False,
    ),
) -> None:
    """Watch files for changes and re-index automatically (requires watchdog)."""
    try:
        from watchdog.observers import Observer
        from watchdog.events import FileSystemEventHandler
    except ImportError:
        console.print("[red]watchdog is required for file watching.[/]")
        console.print("Install it with: [bold]uv sync --extra watch[/]")
        raise typer.Exit(1)

    from local_rag.config import get_settings

    settings = get_settings()
    watch_paths = [Path(p).expanduser().resolve() for p in (paths or settings.spotlight_scan_dirs)]

    class SpotlightHandler(FileSystemEventHandler):
        def on_modified(self, event):
            if event.is_directory:
                return
            from local_rag.spotlight import _reindex_file
            result = _reindex_file(event.src_path)
            if result["ok"] and result["chunks"] > 0:
                console.print(f"[dim]Re-indexed[/] {event.src_path} ({result['chunks']} chunks)")

        def on_created(self, event):
            self.on_modified(event)

    console.print("[bold]Spotlight file watcher started[/]")
    for wp in watch_paths:
        console.print(f"  Watching: [cyan]{wp}[/]")
    console.print("[dim]Press Ctrl+C to stop.[/]")

    event_handler = SpotlightHandler()
    observer = Observer()
    for wp in watch_paths:
        wp.mkdir(parents=True, exist_ok=True)
        observer.schedule(event_handler, str(wp), recursive=True)

    try:
        observer.start()
        while True:
            import time
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()
    console.print("\n[yellow]File watcher stopped.[/]")


# ── Digest commands ────────────────────────────────────────────────────────────


digest_app = typer.Typer(
    name="digest",
    help="Newsletter / paper digest: classify, summarize, and export.",
    no_args_is_help=True,
)
app.add_typer(digest_app)


@digest_app.command()
def add(
    text: str = typer.Argument(..., help="The article / newsletter text"),
    source_type: str = typer.Option("article", "--type", help="newsletter, paper, article, or manual"),
    source: str = typer.Option("", "--source", "-s", help="Display name for the source"),
    url: str = typer.Option("", "--url", "-u", help="Source URL"),
    tags: str = typer.Option("", "--tags", "-t", help="Comma-separated tags"),
) -> None:
    """Add a single item to the digest store."""
    from local_rag.digest import digest_item

    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []
    item_id = digest_item(
        text=text,
        source_type=source_type,
        source=source or source_type,
        url=url,
        tags=tag_list,
    )
    console.print(f"[green]✓ Stored digest item {item_id[:8]}…[/]")


@digest_app.command()
def list_items(
    limit: int = typer.Option(20, "--limit", "-l", help="Number of items"),
    topic: str | None = typer.Option(None, "--topic", help="Filter by topic label"),
    importance: str | None = typer.Option(None, "--importance", help="Filter by importance (high/medium/low)"),
    days: int | None = typer.Option(None, "--days", "-d", help="Only last N days"),
    table: bool = typer.Option(False, "--table", "-t", help="Show rich table output"),
) -> None:
    """List digest items, newest first."""
    from local_rag.digest import fetch_recent_items

    items = fetch_recent_items(
        days=days or 365 * 10,
        topic_filter=topic,
        importance_filter=importance,
    )
    items = items[:limit]

    if not items:
        console.print("[yellow]No digest items found.[/]")
        raise typer.Exit()

    if table:
        tbl = Table(title=f"Digest Items ({len(items)})")
        tbl.add_column("#", style="dim", width=3)
        tbl.add_column("Date", width=12)
        tbl.add_column("Source", style="cyan")
        tbl.add_column("Topics")
        tbl.add_column("Importance")
        for i, item in enumerate(items, 1):
            ts = item.timestamp[:10] if item.timestamp else ""
            topics = ", ".join(item.topics[:3])
            tbl.add_row(str(i), ts, item.source, topics, item.importance)
        console.print(tbl)
    else:
        for i, item in enumerate(items, 1):
            ts = item.timestamp[:19].replace("T", " ")
            console.print(f"[bold]#{i}[/] [dim]{ts}[/] [cyan]{item.source}[/]")
            if item.topics:
                console.print(f"  Topics: {', '.join(item.topics)}")
            console.print(f"  Importance: {item.importance}")
            console.print(f"  {item.summary[:200]}...")
            console.print()


@digest_app.command()
def daily(
    days: int = typer.Option(1, "--days", "-d", help="Number of days to cover"),
    topic: str | None = typer.Option(None, "--topic", help="Filter by topic label"),
    importance: str | None = typer.Option(None, "--importance", help="Filter by importance (high/medium/low)"),
    export: bool = typer.Option(False, "--export", "-e", help="Write digest to a .md file"),
) -> None:
    """Generate and optionally export a daily digest."""
    from local_rag.digest import generate_daily_digest, export_digest_markdown, fetch_recent_items

    if export:
        items = fetch_recent_items(
            days=days,
            topic_filter=topic,
            importance_filter=importance,
        )
        path = export_digest_markdown(items)
        console.print(f"[green]✓ Exported digest to {path}[/]")
    else:
        content = generate_daily_digest(
            days=days,
            topic_filter=topic,
            importance_filter=importance,
        )
        console.print(content)


@digest_app.command()
def stats() -> None:
    """Show digest store statistics."""
    from local_rag.store import count_digest_items, get_digest_topics

    total = count_digest_items()
    topics = get_digest_topics()
    console.print(f"[bold]Digest Store Status[/]")
    console.print(f"  Total items: {total}")
    if topics:
        console.print(f"  Topics: {', '.join(topics)}")


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", "--host", help="Bind address"),
    port: int = typer.Option(9000, "--port", "-p", help="Port to listen on"),
    reload: bool = typer.Option(False, "--reload", help="Auto-reload on code changes"),
) -> None:
    """Launch the web UI (FastAPI + uvicorn)."""
    import uvicorn

    uvicorn.run("local_rag.web:app", host=host, port=port, reload=reload)


@app.command()
def ask(
    text: str = typer.Argument(..., help="Question to answer from the corpus"),
    corpus: Path | None = typer.Option(
        None, "--corpus", help="Folder of .md files (default: sample_corpus)"
    ),
    top_k: int = typer.Option(3, "--top-k", "-k", help="Chunks to cite from"),
    json_out: bool = typer.Option(False, "--json", help="Machine-readable output"),
    rag_only: bool = typer.Option(
        False, "--rag-only", help="Skip the search tools; hybrid RAG only (old behaviour)"
    ),
    previous: str | None = typer.Option(
        None, "--previous", help="Previous question, for a follow-up like 'What does it cover?'"
    ),
    review: bool = typer.Option(
        False, "--review",
        help="Suspend the drafted answer in the review queue instead of releasing it",
    ),
    queue: Path | None = typer.Option(
        None, "--queue", help="Review queue file (default: data/review_queue.json)"
    ),
) -> None:
    """Answer one question with citations, or decline if the corpus has no answer.

    Search tools first (file list, exact quoted phrase, section heading),
    hybrid RAG as the fallback; the route taken is shown. Default corpus
    is the bundled sample firm corpus (sample_corpus/, fictional data
    only). Pass --corpus to point at any other folder of Markdown files.
    With --review the answer is held for a human (see `local-rag review`).
    """
    import json as _json

    from local_rag.agent import route_answer
    from local_rag.answer import answer as run_answer
    from local_rag.config import find_demo_dir
    from local_rag.hybrid import HybridIndex, load_corpus

    try:
        corpus_dir = corpus or find_demo_dir("sample_corpus")
        index = HybridIndex(load_corpus(corpus_dir))
    except FileNotFoundError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=2)
    if rag_only:
        query = text if not previous else f"{previous} {text}"
        result = run_answer(query, index, top_k=top_k)
        result.question = text
    else:
        result = route_answer(text, index, top_k=top_k, previous_question=previous)

    if review:
        from local_rag.review import ReviewQueue

        rq = ReviewQueue(queue)
        item_id = rq.suspend(result)
        if json_out:
            print(_json.dumps({"question": result.question, "review_id": item_id,
                               "state": "pending", "queue": str(rq.path)}, indent=2))
        else:
            console.print(escape(f"\n[SUSPENDED FOR REVIEW] id {item_id} "
                                 f"(draft {result.status}, path {result.path})"))
            console.print(f"Queue: {escape(str(rq.path))}")
            console.print(f"Approve: local-rag review approve {item_id}   "
                          f"Reject: local-rag review reject {item_id}")
        return

    if json_out:
        # Plain stdout, not the Rich console: Rich wraps long lines at
        # terminal width, which breaks JSON when piped.
        print(_json.dumps({
            "question": result.question, "status": result.status,
            "answer": result.answer_text,
            "path": result.path, "path_detail": result.path_detail,
            "citations": [{"source": c.source, "chunk": c.chunk_index,
                           "section": c.section} for c in result.citations],
            "top_score": round(result.top_score, 3),
            "latency_ms": round(result.latency_ms, 1),
        }, indent=2))
        return

    console.print(f"\n[{result.status.upper()}] (path {result.path}"
                  f"{' — ' + escape(result.path_detail) if result.path_detail else ''}, "
                  f"top score {result.top_score:.3f}, {result.latency_ms:.0f} ms)")
    console.print(escape(result.answer_text))
    if result.retrieved:
        console.print("\nRetrieved (hybrid):")
        for chunk in result.retrieved:
            console.print(f"  - {chunk.citation()} | {chunk.section} | "
                          f"rerank {chunk.rerank_score:.3f}")


# ── Review queue (suspend/resume) ─────────────────────────────────────────────

review_app = typer.Typer(help="Human review of suspended answers (ask --review).")
app.add_typer(review_app, name="review")

_QUEUE_OPT = typer.Option(None, "--queue", help="Review queue file")


def _rq(queue: Path | None):
    from local_rag.review import ReviewQueue

    return ReviewQueue(queue)


@review_app.command("list")
def review_list(
    queue: Path | None = _QUEUE_OPT,
    all_items: bool = typer.Option(False, "--all", help="Include decided items"),
) -> None:
    """List pending (or all) suspended answers."""
    rq = _rq(queue)
    items = rq.all() if all_items else rq.pending()
    if not items:
        console.print("No items." if all_items else "Nothing pending.")
        return
    for item in items:
        console.print(f"{item['id']}  " + escape(f"[{item['state']}]") + f"  draft {item['draft']['status']} "
                      f"via {item['draft']['path']}  — {escape(item['question'])}")


@review_app.command("show")
def review_show(item_id: str, queue: Path | None = _QUEUE_OPT) -> None:
    """Show one item: question, draft, citations, decision."""
    import json as _json

    from local_rag.review import ReviewError

    try:
        print(_json.dumps(_rq(queue).get(item_id), indent=2, ensure_ascii=False))
    except ReviewError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1)


@review_app.command("approve")
def review_approve(
    item_id: str,
    edit: str | None = typer.Option(None, "--edit", help="Release this text instead of the draft"),
    note: str = typer.Option("", "--note", help="Reviewer note"),
    queue: Path | None = _QUEUE_OPT,
) -> None:
    """Approve (optionally edit) and release a suspended answer."""
    from local_rag.review import ReviewError

    try:
        item = _rq(queue).approve(item_id, edited_text=edit, note=note)
    except ReviewError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1)
    console.print(escape(f"[APPROVED{' — EDITED' if item['edited'] else ''}] {item_id}"))
    console.print(escape(item["final_answer"]))


@review_app.command("reject")
def review_reject(
    item_id: str,
    note: str = typer.Option("", "--note", help="Why it was rejected"),
    queue: Path | None = _QUEUE_OPT,
) -> None:
    """Reject a suspended answer; it is never released."""
    from local_rag.review import ReviewError

    try:
        _rq(queue).reject(item_id, note=note)
    except ReviewError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1)
    console.print(escape(f"[REJECTED] {item_id}"))


@app.command()
def eval() -> None:
    """Run the original 10-question eval plus the extended eval. Exits 1 on any failure."""
    from local_rag.evaluate import main as run_eval_main

    try:
        code = run_eval_main()
    except FileNotFoundError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=2)
    raise typer.Exit(code=code)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
