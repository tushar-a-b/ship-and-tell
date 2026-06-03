"""Registry of agent/editor source adapters.

Only Claude Code is wired up today. The other entries advertise planned
support to the UI so the user knows what's coming without us pretending it
already works.
"""

from __future__ import annotations

from typing import Protocol

from . import claude_code


class SourceAdapter(Protocol):
    def list_recent(
        self,
        days: int = 7,
        min_user_turns: int = 0,
        project_filter: str | None = None,
    ): ...

    def read_session(
        self,
        session_id: str,
        format: str = "summary",
        max_turns: int = 200,
    ): ...


AVAILABLE: dict[str, dict] = {
    "claude_code": {
        "name": "Claude Code",
        "status": "ready",
        "transcripts_at": "~/.claude/projects/",
        "adapter": claude_code,
    },
    "codex": {
        "name": "Codex CLI",
        "status": "planned",
        "transcripts_at": "~/.codex/sessions/",
        "adapter": None,
    },
    "opencode": {
        "name": "OpenCode",
        "status": "planned",
        "transcripts_at": "~/.local/share/opencode/storage/",
        "adapter": None,
    },
    "cursor": {
        "name": "Cursor",
        "status": "planned",
        "transcripts_at": "~/Library/Application Support/Cursor/User/workspaceStorage/",
        "adapter": None,
    },
    "gemini": {
        "name": "Gemini CLI",
        "status": "planned",
        "transcripts_at": "~/.gemini/",
        "adapter": None,
    },
}


def get_adapter(key: str):
    info = AVAILABLE.get(key)
    if info is None:
        raise KeyError(f"Unknown source: {key}")
    if info["status"] != "ready" or info["adapter"] is None:
        raise NotImplementedError(f"{info['name']} adapter is not yet implemented")
    return info["adapter"]
