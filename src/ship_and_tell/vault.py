"""JSONL vault for saved insights.

Append-only for `save_insight`; mutating operations (`update_insight`,
`mark_posted`) rewrite the file atomically via tempfile + os.replace.
"""

from __future__ import annotations

import json
import os
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

VAULT_DIR = Path(os.environ.get("SHIP_AND_TELL_HOME", str(Path.home() / ".ship-and-tell")))
VAULT_PATH = VAULT_DIR / "vault.jsonl"

# Fields that can be updated via update_insight (id and created_at are immutable).
_MUTABLE_FIELDS = {
    "title",
    "project",
    "problem",
    "root_cause",
    "lesson",
    "tweet",
    "thread",
    "article",
    "source_session_id",
    "tags",
    "posted",
    "links",
}


def _ensure_vault() -> None:
    VAULT_DIR.mkdir(parents=True, exist_ok=True)
    if not VAULT_PATH.exists():
        VAULT_PATH.touch()


def _read_all() -> list[dict[str, Any]]:
    _ensure_vault()
    entries: list[dict[str, Any]] = []
    with VAULT_PATH.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return entries


def _write_all(entries: list[dict[str, Any]]) -> None:
    _ensure_vault()
    fd, tmp_path = tempfile.mkstemp(
        prefix="vault.", suffix=".jsonl.tmp", dir=str(VAULT_DIR)
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            for e in entries:
                fh.write(json.dumps(e) + "\n")
        os.replace(tmp_path, VAULT_PATH)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


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
    links: list[dict[str, Any]] | None = None,
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
        "links": links or [],
        "posted": False,
    }
    with VAULT_PATH.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry) + "\n")
    return entry


def list_vault(
    limit: int = 20,
    since_days: int | None = None,
    posted: bool | None = None,
) -> list[dict[str, Any]]:
    """List vault entries, most recent first.

    posted=None returns all; True returns only posted; False returns only unposted.
    """
    cutoff: float | None = None
    if since_days is not None:
        cutoff = datetime.now(timezone.utc).timestamp() - since_days * 86400

    entries: list[dict[str, Any]] = []
    for entry in _read_all():
        if cutoff is not None:
            ts = entry.get("created_at", "")
            try:
                entry_ts = datetime.fromisoformat(ts).timestamp()
            except ValueError:
                continue
            if entry_ts < cutoff:
                continue
        if posted is not None and bool(entry.get("posted")) != posted:
            continue
        entries.append(entry)

    entries.sort(key=lambda e: e.get("created_at", ""), reverse=True)
    return entries[:limit]


def get_insight(insight_id: str) -> dict[str, Any] | None:
    for entry in _read_all():
        if entry.get("id") == insight_id:
            return entry
    return None


def update_insight(insight_id: str, **fields: Any) -> dict[str, Any]:
    """Update mutable fields on an entry. Returns the updated entry."""
    unknown = set(fields) - _MUTABLE_FIELDS
    if unknown:
        raise ValueError(f"Cannot update fields: {sorted(unknown)}")
    entries = _read_all()
    target = None
    for entry in entries:
        if entry.get("id") == insight_id:
            for k, v in fields.items():
                entry[k] = v
            target = entry
            break
    if target is None:
        raise KeyError(f"Insight not found: {insight_id}")
    _write_all(entries)
    return target


def mark_posted(insight_id: str, posted: bool = True) -> dict[str, Any]:
    return update_insight(insight_id, posted=posted)


def delete_insight(insight_id: str) -> dict[str, Any]:
    """Remove an entry from the vault. Returns the deleted entry."""
    entries = _read_all()
    target = None
    remaining: list[dict[str, Any]] = []
    for entry in entries:
        if target is None and entry.get("id") == insight_id:
            target = entry
            continue
        remaining.append(entry)
    if target is None:
        raise KeyError(f"Insight not found: {insight_id}")
    _write_all(remaining)
    return target
