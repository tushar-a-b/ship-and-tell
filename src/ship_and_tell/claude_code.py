"""Source adapter for Claude Code transcripts (~/.claude/projects/)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

CLAUDE_PROJECTS_DIR = Path.home() / ".claude" / "projects"


@dataclass
class SessionInfo:
    session_id: str
    project: str
    path: Path
    started_at: str | None
    last_active_at: str
    message_count: int
    user_turn_count: int
    first_user_message: str
    git_branch: str | None
    model: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "project": self.project,
            "started_at": self.started_at,
            "last_active_at": self.last_active_at,
            "message_count": self.message_count,
            "user_turn_count": self.user_turn_count,
            "first_user_message": self.first_user_message,
            "git_branch": self.git_branch,
            "model": self.model,
        }


def _slug_to_project(slug: str) -> str:
    if slug.startswith("-"):
        return "/" + slug[1:].replace("-", "/")
    return slug.replace("-", "/")


def _iter_session_files() -> Iterator[Path]:
    if not CLAUDE_PROJECTS_DIR.exists():
        return
    for project_dir in CLAUDE_PROJECTS_DIR.iterdir():
        if not project_dir.is_dir():
            continue
        for f in project_dir.glob("*.jsonl"):
            yield f


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def _extract_text(content: Any) -> str:
    """Pull plain visible text out of message content. Skips tool/thinking blocks."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for p in content:
            if not isinstance(p, dict):
                continue
            if p.get("type") == "text" and isinstance(p.get("text"), str):
                parts.append(p["text"])
        return "\n".join(parts)
    return ""


def _is_tool_result(content: Any) -> bool:
    if not isinstance(content, list):
        return False
    return any(isinstance(p, dict) and p.get("type") == "tool_result" for p in content)


_META_PREFIXES = (
    "<command-name>",
    "<command-message>",
    "<command-args>",
    "<local-command-stdout>",
    "<system-reminder>",
    "<user-prompt-submit-hook>",
)


def _is_meta(text: str) -> bool:
    s = text.lstrip()
    return any(s.startswith(p) for p in _META_PREFIXES)


def list_recent(days: int = 7) -> list[SessionInfo]:
    """List Claude Code sessions whose file was modified within the last `days`."""
    now = datetime.now(timezone.utc).timestamp()
    cutoff = now - days * 86400
    results: list[SessionInfo] = []

    for path in _iter_session_files():
        try:
            mtime = path.stat().st_mtime
        except OSError:
            continue
        if mtime < cutoff:
            continue

        records = _read_jsonl(path)
        if not records:
            continue

        session_id = path.stem
        project: str | None = None
        first_user = ""
        started_at: str | None = None
        git_branch: str | None = None
        model: str | None = None
        user_turn_count = 0

        for rec in records:
            ts = rec.get("timestamp")
            if started_at is None and ts:
                started_at = ts
            if project is None and rec.get("cwd"):
                project = rec["cwd"]
            if git_branch is None and rec.get("gitBranch"):
                git_branch = rec["gitBranch"]
            if model is None and rec.get("type") == "assistant":
                msg = rec.get("message", {})
                if isinstance(msg, dict) and msg.get("model"):
                    model = msg["model"]
            if rec.get("type") == "user":
                msg = rec.get("message", {})
                if not isinstance(msg, dict):
                    continue
                content = msg.get("content")
                if _is_tool_result(content):
                    continue
                text = _extract_text(content)
                if text and not _is_meta(text):
                    user_turn_count += 1
                    if not first_user:
                        first_user = text[:240]

        if project is None:
            project = _slug_to_project(path.parent.name)

        results.append(
            SessionInfo(
                session_id=session_id,
                project=project,
                path=path,
                started_at=started_at,
                last_active_at=datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat(),
                message_count=len(records),
                user_turn_count=user_turn_count,
                first_user_message=first_user,
                git_branch=git_branch,
                model=model,
            )
        )

    results.sort(key=lambda s: s.last_active_at, reverse=True)
    return results


def find_session(session_id: str) -> Path | None:
    for path in _iter_session_files():
        if path.stem == session_id:
            return path
    return None


def read_session(
    session_id: str,
    format: str = "summary",
    max_turns: int = 200,
) -> dict[str, Any]:
    path = find_session(session_id)
    if path is None:
        raise FileNotFoundError(f"Session not found: {session_id}")

    records = _read_jsonl(path)
    project: str | None = None
    for rec in records:
        if rec.get("cwd"):
            project = rec["cwd"]
            break
    if project is None:
        project = _slug_to_project(path.parent.name)

    if format == "full":
        return {
            "session_id": session_id,
            "project": project,
            "messages": records,
        }

    # Summary: keep only human-typed user turns + assistant text replies.
    # Drop tool_result user records, tool_use-only assistant turns, meta wrappers,
    # and thinking blocks.
    turns: list[dict[str, Any]] = []
    for rec in records:
        rtype = rec.get("type")
        if rtype not in ("user", "assistant"):
            continue
        msg = rec.get("message")
        if not isinstance(msg, dict):
            continue
        content = msg.get("content")
        if rtype == "user" and _is_tool_result(content):
            continue
        text = _extract_text(content)
        if not text.strip() or _is_meta(text):
            continue
        turns.append(
            {
                "role": rtype,
                "timestamp": rec.get("timestamp"),
                "text": text,
            }
        )

    total = len(turns)
    truncated = False
    if total > max_turns:
        # Keep the opening (intent) and the tail (resolution) -- the middle
        # of a long debugging session is usually less load-bearing than either end.
        head = max_turns // 2
        tail = max_turns - head
        turns = turns[:head] + [{"role": "system", "text": f"... [{total - max_turns} turns elided] ..."}] + turns[-tail:]
        truncated = True

    return {
        "session_id": session_id,
        "project": project,
        "turn_count": total,
        "returned_turn_count": len(turns),
        "truncated": truncated,
        "turns": turns,
    }
