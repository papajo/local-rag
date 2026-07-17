from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from local_rag.config import get_settings
from local_rag.extract import classify_text, extract_entities
from local_rag.models import DigestItem, ExtractedEntity
from local_rag.store import (
    list_digest_items,
    store_digest_item,
)

logger = logging.getLogger(__name__)


def _embed(text: str) -> list[float]:
    """Embed a single text via SIE /v1/embeddings."""
    import httpx

    settings = get_settings()
    url = f"{settings.sie_base_url}/v1/embeddings"
    payload = {"model": settings.embed_model, "input": text}

    resp = httpx.post(url, json=payload, timeout=30.0)
    resp.raise_for_status()
    return resp.json()["data"][0]["embedding"]


def _summarize_extractive(text: str, max_chars: int = 600) -> str:
    """Extractive summarization: first ~max_chars characters."""
    if len(text) <= max_chars:
        return text
    # Try to break at sentence or paragraph boundary
    truncated = text[:max_chars]
    last_period = truncated.rfind(". ")
    last_newline = truncated.rfind("\n\n")
    cut = max(last_period + 1, last_newline)
    if cut < max_chars * 0.3:
        cut = max_chars
    return truncated[:cut] + "…"


def _summarize_abstractive(text: str, model: str) -> str:
    """Abstractive summarization via SIE /v1/chat/completions."""
    import httpx

    settings = get_settings()
    url = f"{settings.sie_base_url}/v1/chat/completions"
    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": (
                    "Summarize the following text in 2-3 sentences. "
                    f"Be concise and factual:\n\n{text}"
                ),
            },
        ],
        "temperature": 0.3,
        "max_tokens": 200,
    }

    try:
        resp = httpx.post(url, json=payload, timeout=60.0)
        resp.raise_for_status()
        data = resp.json()
        choice = data.get("choices", [{}])[0]
        summary = choice.get("message", {}).get("content", "").strip()
        if summary:
            return summary
    except Exception as exc:
        logger.warning("Abstractive summarization failed (%s), falling back to extractive", exc)

    return _summarize_extractive(text)


def digest_item(
    text: str,
    source_type: str = "article",
    source: str = "",
    url: str = "",
    topic_labels: list[str] | None = None,
    importance_labels: list[str] | None = None,
    tags: list[str] | None = None,
    summarization_model: str | None = None,
) -> str:
    """Classify, summarize, embed, and store a single digest item.

    Args:
        text: The full article / newsletter text.
        source_type: ``"newsletter"``, ``"paper"``, ``"article"``, or ``"manual"``.
        source: Display name (newsletter title, feed name, etc.).
        url: Source URL.
        topic_labels: Override default topic labels from config.
        importance_labels: Override default importance labels from config.
        tags: Optional user tags.
        summarization_model: Override summarization model from config.

    Returns:
        The digest item ID string.
    """
    settings = get_settings()
    topic_lbls = topic_labels or settings.digest_topic_labels.split(",")
    imp_lbls = importance_labels or settings.digest_importance_labels.split(",")
    summ_model = summarization_model or settings.digest_summarization_model

    # Classify topics via GLiNER zero-shot
    topic_scores = classify_text(text, labels=[label.strip() for label in topic_lbls if label.strip()])
    matched_topics = sorted(
        [label for label, score in topic_scores.items() if score > 0.0]
    )

    # Classify importance
    imp_scores = classify_text(text, labels=[label.strip() for label in imp_lbls if label.strip()])
    best_imp = max(imp_scores, key=imp_scores.get) if imp_scores else "routine"

    # Map to importance levels
    importance_map = {
        "important announcement": "high",
        "action required": "high",
        "routine update": "medium",
        "low priority": "low",
    }
    importance = importance_map.get(best_imp, "medium")

    # Extract entities
    entities: list[ExtractedEntity] = []
    try:
        results = extract_entities([text])
        if results:
            entities = results[0].entities
    except Exception as exc:
        logger.warning("Entity extraction failed for digest item (%s)", exc)

    # Summarize
    if summ_model:
        summary = _summarize_abstractive(text, summ_model)
    else:
        summary = _summarize_extractive(text)

    # Embed
    embedding = _embed(text)

    item = DigestItem(
        id=str(uuid.uuid4()),
        text=text,
        summary=summary,
        source_type=source_type,
        source=source,
        url=url,
        topics=matched_topics,
        importance=importance,
        entities=entities,
        tags=tags or [],
        timestamp=datetime.now(timezone.utc).isoformat(),
        embedding=embedding,
    )

    stored_id = store_digest_item(item)
    logger.info(
        "Stored digest item %s (source=%s, topics=%s, importance=%s, entities=%d)",
        stored_id,
        source,
        matched_topics,
        importance,
        len(entities),
    )
    return stored_id


def fetch_recent_items(
    days: int = 1,
    topic_filter: str | None = None,
    importance_filter: str | None = None,
) -> list[DigestItem]:
    """Fetch digest items from the last N days."""
    return list_digest_items(
        limit=1000,
        topic_filter=topic_filter,
        importance_filter=importance_filter,
        days=days,
    )


def generate_daily_digest(
    days: int = 1,
    topic_filter: str | None = None,
    importance_filter: str | None = None,
) -> str:
    """Generate a daily digest in Markdown.

    Returns a pre-formatted Markdown string grouped by topic, ready for
    display or export.
    """
    items = fetch_recent_items(
        days=days,
        topic_filter=topic_filter,
        importance_filter=importance_filter,
    )

    if not items:
        return "# 📋 Daily Digest\n\n*No items in this period.*\n"

    # Group by topic
    grouped: dict[str, list[DigestItem]] = {}
    for item in items:
        for topic in item.topics or ["uncategorized"]:
            grouped.setdefault(topic, []).append(item)

    lines: list[str] = []
    lines.append("# 📋 Daily Digest")
    lines.append("")
    lines.append(f"*{len(items)} items across {len(grouped)} topics*\n")

    for topic in sorted(grouped.keys()):
        lines.append(f"## {topic.title()}")
        lines.append("")
        for item in grouped[topic]:
            imp_badge = {"high": "🔴", "medium": "🟡", "low": "⚪"}.get(
                item.importance, "⚪"
            )
            lines.append(f"### {imp_badge} {item.source or 'Untitled'}")
            lines.append("")
            lines.append(item.summary)
            lines.append("")
            if item.url:
                lines.append(f"🔗 [{item.source}]({item.url})")
            if item.entities:
                ents = ", ".join(
                    f"**{e.label}**: {e.text}" for e in item.entities[:5]
                )
                lines.append(f"🏷️ {ents}")
            lines.append(f"*{item.timestamp}*")
            lines.append("")

    return "\n".join(lines)


def export_digest_markdown(
    items: list[DigestItem],
    date: str = "",
    output_path: str = "",
) -> str:
    """Export digest items to a Markdown file.

    Args:
        items: Digest items to export.
        date: Date string for the filename and header (e.g. ``"2026-07-17"``).
        output_path: Override output path. Auto-generated from date if empty.

    Returns:
        The path to the written file.
    """
    from pathlib import Path

    from local_rag.config import DEFAULT_DATA_DIR

    if not date:
        date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    if not output_path:
        digest_dir = DEFAULT_DATA_DIR / "digests"
        digest_dir.mkdir(parents=True, exist_ok=True)
        output_path = str(digest_dir / f"digest-{date}.md")

    content = generate_daily_digest()
    Path(output_path).write_text(content, encoding="utf-8")
    logger.info("Exported digest to %s", output_path)
    return output_path
