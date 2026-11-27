"""Suspend/resume human review for drafted answers (opt-in).

Idea from Sam Bhagwat, "Principles of Building AI Agents" (3rd ed.,
ch. 14, "Suspend and Resume"): when a step waits on a human, don't keep a
process running — persist the state durably and resume it later.

Here a drafted answer is *suspended* into a JSON queue on disk instead of
being released. A reviewer later lists pending items and approves,
edits-then-approves, or rejects each one. Nothing is held in memory
between commands, so the queue survives a restart by construction.

Off by default: plain `local-rag ask` behaves exactly as before. Use
`local-rag ask --review` to suspend, and `local-rag review ...` to resume.

Queue file: data/review_queue.json, or $LOCAL_RAG_REVIEW_QUEUE, or
`--queue PATH`. Writes are atomic (temp file + os.replace), so a crash
mid-write cannot leave a half-written queue.
"""

from __future__ import annotations

import json
import os
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

from local_rag.answer import Answer

PENDING, APPROVED, REJECTED = "pending", "approved", "rejected"


def default_queue_path() -> Path:
    env = os.environ.get("LOCAL_RAG_REVIEW_QUEUE")
    if env:
        return Path(env)
    try:
        from local_rag.config import PROJECT_ROOT
        return Path(PROJECT_ROOT) / "data" / "review_queue.json"
    except Exception:
        return Path.cwd() / "data" / "review_queue.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class ReviewError(Exception):
    pass


class ReviewQueue:
    """A durable queue of suspended answers. Every call re-reads the file."""

    def __init__(self, path: Path | str | None = None):
        self.path = Path(path) if path else default_queue_path()

    # -- storage -------------------------------------------------------------
    def _load(self) -> list[dict]:
        if not self.path.exists():
            return []
        data = json.loads(self.path.read_text(encoding="utf-8"))
        return data.get("items", [])

    def _save(self, items: list[dict]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self.path.parent, prefix=".review_queue.", suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump({"version": 1, "items": items}, fh, indent=2, ensure_ascii=False)
        os.replace(tmp, self.path)

    # -- suspend -------------------------------------------------------------
    def suspend(self, result: Answer) -> str:
        """Store a drafted answer as pending; return its id. Not released."""
        items = self._load()
        item_id = uuid.uuid4().hex[:8]
        items.append({
            "id": item_id,
            "state": PENDING,
            "created_at": _now(),
            "question": result.question,
            "draft": {
                "status": result.status,
                "answer": result.answer_text,
                "path": result.path,
                "path_detail": result.path_detail,
                "citations": [c.to_dict() for c in result.citations],
            },
            "final_answer": None,
            "edited": False,
            "reviewer_note": "",
            "decided_at": None,
        })
        self._save(items)
        return item_id

    # -- read ----------------------------------------------------------------
    def all(self) -> list[dict]:
        return self._load()

    def pending(self) -> list[dict]:
        return [i for i in self._load() if i["state"] == PENDING]

    def get(self, item_id: str) -> dict:
        for item in self._load():
            if item["id"] == item_id:
                return item
        raise ReviewError(f"No review item with id {item_id}")

    # -- resume --------------------------------------------------------------
    def _decide(self, item_id: str, state: str, final: str | None,
                edited: bool, note: str) -> dict:
        items = self._load()
        for item in items:
            if item["id"] != item_id:
                continue
            if item["state"] != PENDING:
                raise ReviewError(f"Item {item_id} is already {item['state']}")
            item.update(state=state, final_answer=final, edited=edited,
                        reviewer_note=note, decided_at=_now())
            self._save(items)
            return item
        raise ReviewError(f"No review item with id {item_id}")

    def approve(self, item_id: str, edited_text: str | None = None, note: str = "") -> dict:
        """Release the draft as-is, or release the reviewer's edited text.

        An edited answer is marked edited=True: its wording is the
        reviewer's, so it is no longer a verbatim quote of the cited
        chunks. The draft's citations are kept as the reviewer's sources.
        """
        draft = self.get(item_id)["draft"]["answer"]
        if edited_text is not None and edited_text.strip():
            return self._decide(item_id, APPROVED, edited_text.strip(), True, note)
        return self._decide(item_id, APPROVED, draft, False, note)

    def reject(self, item_id: str, note: str = "") -> dict:
        """Never release this answer. A note says why."""
        return self._decide(item_id, REJECTED, None, False, note)
