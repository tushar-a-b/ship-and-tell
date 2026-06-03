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
    subagent_count: int = 0

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
            "subagent_count": self.subagent_count,
        }


@dataclass
class SubagentInfo:
    parent_session_id: str
    agent_id: str
    agent_type: str
    description: str
    path: Path
    started_at: str | None
    last_active_at: str
    message_count: int
    model: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "parent_session_id": self.parent_session_id,
            "agent_id": self.agent_id,
            "agent_type": self.agent_type,
            "description": self.description,
            "started_at": self.started_at,
            "last_active_at": self.last_active_at,
            "message_count": self.message_count,
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


def _agent_tool_uses(content: Any) -> list[dict[str, Any]]:
    """Return [{tool_use_id, description, subagent_type}] for any Agent tool_use blocks."""
    out: list[dict[str, Any]] = []
    if not isinstance(content, list):
        return out
    for p in content:
        if not isinstance(p, dict):
            continue
        if p.get("type") == "tool_use" and p.get("name") == "Agent":
            inp = p.get("input") or {}
            out.append(
                {
                    "tool_use_id": p.get("id"),
                    "description": inp.get("description") or "",
                    "subagent_type": inp.get("subagent_type") or "",
                }
            )
    return out


def _subagents_dir(session_path: Path) -> Path:
    """Where Claude Code stores spawned-subagent transcripts for a session."""
    return session_path.parent / session_path.stem / "subagents"


def _count_subagents(session_path: Path) -> int:
    sd = _subagents_dir(session_path)
    if not sd.exists():
        return 0
    return sum(1 for _ in sd.glob("agent-*.jsonl"))


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


def list_recent(
    days: int = 7,
    min_user_turns: int = 0,
    project_filter: str | None = None,
) -> list[SessionInfo]:
    """List Claude Code sessions whose file was modified within the last `days`.

    `min_user_turns`: skip sessions with fewer human-typed turns than this.
    `project_filter`: case-insensitive substring match against the cwd.
    """
    now = datetime.now(timezone.utc).timestamp()
    cutoff = now - days * 86400
    pf = project_filter.lower() if project_filter else None
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

        if user_turn_count < min_user_turns:
            continue
        if pf and pf not in project.lower():
            continue

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
                subagent_count=_count_subagents(path),
            )
        )

    results.sort(key=lambda s: s.last_active_at, reverse=True)
    return results


def find_session(session_id: str) -> Path | None:
    for path in _iter_session_files():
        if path.stem == session_id:
            return path
    return None


def _summarize_records(
    records: list[dict[str, Any]],
    max_turns: int,
    is_subagent: bool = False,
    subagent_markers: dict[str, dict[str, Any]] | None = None,
) -> tuple[list[dict[str, Any]], int, bool]:
    """Convert raw JSONL records into clean user+assistant text turns.

    If `subagent_markers` is provided, any assistant record whose content
    invokes an Agent tool_use whose id is in the dict will emit a synthetic
    `subagent_marker` turn immediately after, referencing the matched
    subagent's type+description. The corresponding tool_result is dropped
    anyway by the standard summary path -- this just lets the consumer see
    the boundary in the conversation flow without double-counting.

    Returns (turns_list, total_kept, truncated).
    """
    turns: list[dict[str, Any]] = []
    seen_user_count = 0
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
        ts = rec.get("timestamp")

        if rtype == "user" and is_subagent and seen_user_count == 0 and text.strip():
            # A subagent's first "user" record is the parent's auto-generated
            # task brief, NOT a human prompt. Label it so the digest LLM does
            # not treat it as user intent.
            seen_user_count += 1
            turns.append({"role": "agent_task", "timestamp": ts, "text": text})
            continue

        if text.strip() and not _is_meta(text):
            if rtype == "user":
                seen_user_count += 1
            turns.append({"role": rtype, "timestamp": ts, "text": text})

        if rtype == "assistant" and subagent_markers:
            for au in _agent_tool_uses(content):
                meta = subagent_markers.get(au["tool_use_id"] or "")
                if meta is None:
                    continue
                turns.append(
                    {
                        "role": "subagent_marker",
                        "timestamp": ts,
                        "agent_id": meta["agent_id"],
                        "agent_type": meta["agent_type"],
                        "description": meta["description"],
                        "text": (
                            f"[Subagent: {meta['agent_type']} — "
                            f"\"{meta['description']}\" — "
                            f"full transcript included below]"
                        ),
                    }
                )

    total = len(turns)
    truncated = False
    if total > max_turns:
        head = max_turns // 2
        tail = max_turns - head
        elide = {"role": "system", "text": f"... [{total - max_turns} turns elided] ..."}
        turns = turns[:head] + [elide] + turns[-tail:]
        truncated = True
    return turns, total, truncated


def _load_subagent_metas(parent_path: Path) -> list[SubagentInfo]:
    """Return SubagentInfo entries for one parent session, sorted by mtime asc."""
    sd = _subagents_dir(parent_path)
    if not sd.exists():
        return []
    parent_session_id = parent_path.stem
    out: list[SubagentInfo] = []
    for jsonl in sd.glob("agent-*.jsonl"):
        agent_id = jsonl.stem.removeprefix("agent-")
        meta_path = sd / f"agent-{agent_id}.meta.json"
        agent_type = ""
        description = ""
        if meta_path.exists():
            try:
                m = json.loads(meta_path.read_text())
                agent_type = m.get("agentType") or ""
                description = m.get("description") or ""
            except (json.JSONDecodeError, OSError):
                pass
        try:
            mtime = jsonl.stat().st_mtime
        except OSError:
            continue
        records = _read_jsonl(jsonl)
        started_at: str | None = None
        model: str | None = None
        for rec in records:
            if started_at is None and rec.get("timestamp"):
                started_at = rec["timestamp"]
            if model is None and rec.get("type") == "assistant":
                msg = rec.get("message", {})
                if isinstance(msg, dict) and msg.get("model"):
                    model = msg["model"]
            if started_at and model:
                break
        out.append(
            SubagentInfo(
                parent_session_id=parent_session_id,
                agent_id=agent_id,
                agent_type=agent_type,
                description=description,
                path=jsonl,
                started_at=started_at,
                last_active_at=datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat(),
                message_count=len(records),
                model=model,
            )
        )
    out.sort(key=lambda s: s.started_at or s.last_active_at)
    return out


def list_subagents(parent_session_id: str) -> list[SubagentInfo]:
    """List all subagents spawned from a given parent session."""
    path = find_session(parent_session_id)
    if path is None:
        raise FileNotFoundError(f"Session not found: {parent_session_id}")
    return _load_subagent_metas(path)


def read_subagent(
    parent_session_id: str,
    agent_id: str,
    format: str = "summary",
    max_turns: int = 100,
) -> dict[str, Any]:
    parent_path = find_session(parent_session_id)
    if parent_path is None:
        raise FileNotFoundError(f"Parent session not found: {parent_session_id}")
    sub_path = _subagents_dir(parent_path) / f"agent-{agent_id}.jsonl"
    if not sub_path.exists():
        raise FileNotFoundError(f"Subagent not found: {agent_id}")
    meta_path = _subagents_dir(parent_path) / f"agent-{agent_id}.meta.json"
    meta: dict[str, Any] = {}
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text())
        except (json.JSONDecodeError, OSError):
            meta = {}

    records = _read_jsonl(sub_path)
    if format == "full":
        return {
            "parent_session_id": parent_session_id,
            "agent_id": agent_id,
            "agent_type": meta.get("agentType", ""),
            "description": meta.get("description", ""),
            "messages": records,
        }

    turns, total, truncated = _summarize_records(records, max_turns, is_subagent=True)
    return {
        "parent_session_id": parent_session_id,
        "agent_id": agent_id,
        "agent_type": meta.get("agentType", ""),
        "description": meta.get("description", ""),
        "turn_count": total,
        "returned_turn_count": len(turns),
        "truncated": truncated,
        "turns": turns,
    }


def _match_subagents_to_parent(
    parent_records: list[dict[str, Any]],
    subagents: list[SubagentInfo],
) -> tuple[dict[str, dict[str, Any]], list[SubagentInfo]]:
    """Match each subagent to a parent Agent tool_use by description (chronological tiebreak).

    Returns (tool_use_id -> {agent_id, agent_type, description}, unmatched_subagents).
    """
    # Walk parent in order, collecting Agent tool_uses with their descriptions.
    parent_agent_calls: list[dict[str, Any]] = []
    for rec in parent_records:
        if rec.get("type") != "assistant":
            continue
        msg = rec.get("message")
        if not isinstance(msg, dict):
            continue
        for au in _agent_tool_uses(msg.get("content")):
            parent_agent_calls.append(au)

    # Bucket subagents by description, preserving chronological order.
    by_desc: dict[str, list[SubagentInfo]] = {}
    for sub in subagents:
        by_desc.setdefault(sub.description, []).append(sub)

    matched: dict[str, dict[str, Any]] = {}
    used_subagent_ids: set[str] = set()
    for call in parent_agent_calls:
        bucket = by_desc.get(call["description"]) or []
        # pop the first unused subagent in this bucket
        while bucket:
            cand = bucket.pop(0)
            if cand.agent_id in used_subagent_ids:
                continue
            tool_use_id = call["tool_use_id"]
            if not tool_use_id:
                break
            matched[tool_use_id] = {
                "agent_id": cand.agent_id,
                "agent_type": cand.agent_type or call["subagent_type"],
                "description": cand.description,
            }
            used_subagent_ids.add(cand.agent_id)
            break

    unmatched = [s for s in subagents if s.agent_id not in used_subagent_ids]
    return matched, unmatched


def read_session(
    session_id: str,
    format: str = "summary",
    max_turns: int = 200,
    include_subagents: str = "none",
    max_subagent_turns: int = 40,
) -> dict[str, Any]:
    """Read a session in summary or full form.

    include_subagents:
      - "none"    (default): parent transcript only; tool_use/tool_result for
                  any Agent calls are stripped as usual. No duplication risk.
      - "summary": parent transcript with `subagent_marker` turns inserted at
                  each Agent invocation point, followed by each matched
                  subagent's own summary in its own section. The parent's
                  redundant tool_result was already excluded by the summary
                  path, so each piece of subagent content appears EXACTLY
                  ONCE -- in its dedicated section.
      - "full":   returns raw JSONL for the parent plus raw JSONL per
                  subagent. Use sparingly.
    """
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
        result: dict[str, Any] = {
            "session_id": session_id,
            "project": project,
            "messages": records,
        }
        if include_subagents != "none":
            subs = _load_subagent_metas(path)
            result["subagents"] = [
                {
                    **s.to_dict(),
                    "messages": _read_jsonl(s.path),
                }
                for s in subs
            ]
        return result

    subagents = _load_subagent_metas(path) if include_subagents != "none" else []
    matched, unmatched = (
        _match_subagents_to_parent(records, subagents) if subagents else ({}, [])
    )

    parent_turns, parent_total, parent_truncated = _summarize_records(
        records,
        max_turns=max_turns,
        subagent_markers=matched if include_subagents == "summary" else None,
    )

    subagent_sections: list[dict[str, Any]] = []
    if include_subagents == "summary" and subagents:
        for sub in subagents:
            # Read subagent records once and summarize.
            sub_records = _read_jsonl(sub.path)
            sub_turns, sub_total, sub_truncated = _summarize_records(
                sub_records,
                max_turns=max_subagent_turns,
                is_subagent=True,
            )
            is_matched = any(
                m["agent_id"] == sub.agent_id for m in matched.values()
            )
            subagent_sections.append(
                {
                    "agent_id": sub.agent_id,
                    "agent_type": sub.agent_type,
                    "description": sub.description,
                    "matched_to_parent": is_matched,
                    "turn_count": sub_total,
                    "returned_turn_count": len(sub_turns),
                    "truncated": sub_truncated,
                    "turns": sub_turns,
                }
            )

    return {
        "session_id": session_id,
        "project": project,
        "turn_count": parent_total,
        "returned_turn_count": len(parent_turns),
        "truncated": parent_truncated,
        "turns": parent_turns,
        "subagent_count": len(subagents),
        "subagent_sections": subagent_sections,
        "unmatched_subagent_count": len(unmatched),
    }
