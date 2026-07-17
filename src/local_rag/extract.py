"""Structured fact extraction from retrieved chunks via SIE."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import msgpack

from local_rag.config import get_settings
from local_rag.models import ExtractedEntity

# ── Default labels for extraction ─────────────────────────────────────────────
DEFAULT_LABELS = [
    "person",
    "organization",
    "technology",
    "product",
    "location",
    "date",
]


@dataclass
class ExtractionResult:
    """Extraction result for a single input text."""

    text: str
    entities: list[ExtractedEntity]


def extract_entities(
    texts: list[str],
    labels: list[str] | None = None,
    model: str | None = None,
    *,
    source: str = "",
    chunk_index: int = 0,
) -> list[ExtractionResult]:
    """Extract entities from a batch of texts via SIE.

    Args:
        texts: List of text strings to extract entities from.
        labels: Entity labels to extract (e.g. person, organization).
            Defaults to DEFAULT_LABELS.
        model: GLiNER model name on SIE. Defaults to settings.extract_model.
        source: Source file path (passed through for context).
        chunk_index: Chunk index (passed through for context).

    Returns:
        One ExtractionResult per input text, each holding its entities.
    """
    if not texts:
        return []

    settings = get_settings()
    extract_model = model or settings.extract_model
    extract_labels = labels or DEFAULT_LABELS

    import httpx

    url = f"{settings.sie_base_url}/v1/extract/{extract_model}"
    payload: dict[str, Any] = {
        "items": [{"text": t} for t in texts],
        "params": {"labels": extract_labels},
    }

    resp = httpx.post(url, json=payload, timeout=120.0)
    resp.raise_for_status()

    # SIE extract endpoint returns MessagePack, not JSON
    content_type = resp.headers.get("content-type", "")
    if "msgpack" in content_type:
        data = msgpack.unpackb(resp.content)
    else:
        data = resp.json()

    # Parse response — structure from SIE:
    # { "model": "...", "items": [ { "id": "...", "entities": [...], ... } ] }
    raw_items: list[dict] = data.get("items", data if isinstance(data, list) else [])

    results: list[ExtractionResult] = []
    for raw_item in raw_items:
        item_text = raw_item.get("text", "")
        entities: list[ExtractedEntity] = []

        entities_raw = raw_item.get("entities", [])
        for ent in entities_raw:
            if isinstance(ent, dict):
                label = ent.get("label", "")
                text_val = ent.get("text", "")
                score = ent.get("score", 0.0)
                if label and text_val:
                    entities.append(ExtractedEntity(
                        label=label,
                        text=text_val,
                        score=float(score),
                    ))

        # Deduplicate nearby-identical entities (same label + text, keep highest score)
        seen: set[tuple[str, str]] = set()
        deduped: list[ExtractedEntity] = []
        for e in sorted(entities, key=lambda x: x.score, reverse=True):
            key = (e.label, e.text.lower().strip())
            if key not in seen:
                seen.add(key)
                deduped.append(e)
        deduped.sort(key=lambda x: x.score, reverse=True)

        results.append(ExtractionResult(text=item_text, entities=deduped))

    return results


def classify_text(
    text: str,
    labels: list[str],
    model: str | None = None,
) -> dict[str, float]:
    """Zero-shot text classification via GLiNER entity extraction.

    Treats each label as an entity type to extract. Returns a dict mapping
    each label to the fraction of extracted entities that matched it (0.0–1.0).
    A label with score > 0 means the model recognized it in the text.
    """
    if not text.strip() or not labels:
        return {lbl: 0.0 for lbl in labels}

    settings = get_settings()
    extract_model = model or settings.extract_model

    import httpx

    url = f"{settings.sie_base_url}/v1/extract/{extract_model}"
    payload: dict[str, Any] = {
        "items": [{"text": text}],
        "params": {"labels": labels},
    }

    try:
        resp = httpx.post(url, json=payload, timeout=60.0)
        resp.raise_for_status()
    except Exception:
        return {lbl: 0.0 for lbl in labels}

    content_type = resp.headers.get("content-type", "")
    if "msgpack" in content_type:
        data = msgpack.unpackb(resp.content)
    else:
        data = resp.json()

    raw_items: list[dict] = data.get("items", data if isinstance(data, list) else [])
    if not raw_items:
        return {lbl: 0.0 for lbl in labels}

    entities_raw = raw_items[0].get("entities", [])
    total = len(entities_raw)
    counts: dict[str, float] = {lbl: 0.0 for lbl in labels}
    for ent in entities_raw:
        label = ent.get("label", "") if isinstance(ent, dict) else ""
        if label in counts:
            counts[label] += 1.0

    if total > 0:
        counts = {k: round(v / total, 4) for k, v in counts.items()}

    return counts
