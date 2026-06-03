"""Append-only JSONL vault for saved insights."""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

VAULT_DIR = Path(os.environ.get("SHIP_AND_TELL_HOME", str(Path.home() / ".ship-and-tell")))
VAULT_PATH = VAULT_DIR / "vault.jsonl"


def _ensure_vault() -> None:
    VAULT_DIR.mkdir(parents=True, exist_ok=True)
    if not VAULT_PATH.exists():
        VAULT_PATH.touch()


def save_insight(
    title: str,
    lesson: str,
    project: str = "",
    problem: str = "",
    root_cause: str = "",
    tweet: str = "",
    thread: str = "",
    article: str = "",
    source_session_id: str = "",
    tags: list[str] | None = None,
) -> dict[str, Any]:
    _ensure_vault()
    entry = {
        "id": str(uuid.uuid4()),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "title": title,
        "project": project,
        "problem": problem,
        "root_cause": root_cause,
        "lesson": lesson,
        "tweet": tweet,
        "thread": thread,
        "article": article,
        "source_session_id": source_session_id,
        "tags": tags or [],
        "posted": False,
    }
    with VAULT_PATH.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry) + "\n")
    return entry


def list_vault(limit: int = 20, since_days: int | None = None) -> list[dict[str, Any]]:
    _ensure_vault()
    cutoff: float | None = None
    if since_days is not None:
        cutoff = datetime.now(timezone.utc).timestamp() - since_days * 86400

    entries: list[dict[str, Any]] = []
    with VAULT_PATH.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if cutoff is not None:
                ts = entry.get("created_at", "")
                try:
                    entry_ts = datetime.fromisoformat(ts).timestamp()
                except ValueError:
                    continue
                if entry_ts < cutoff:
                    continue
            entries.append(entry)

    entries.sort(key=lambda e: e.get("created_at", ""), reverse=True)
    return entries[:limit]
