"""MCP server for Ship & Tell.

Exposes structured access to the user's coding-agent transcripts and a local
JSONL vault for saved insights. The host agent (Claude Code, Cursor, OpenCode,
Codex CLI, Gemini CLI) does all the LLM work via its own model and login --
this server adds no external API calls.
"""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from . import claude_code, vault

mcp = FastMCP("ship-and-tell")


@mcp.tool()
def list_recent_sessions(
    days: int = 7,
    min_user_turns: int = 0,
    project_filter: str | None = None,
) -> list[dict[str, Any]]:
    """List Claude Code coding sessions from the last N days.

    Returns metadata per session: session_id, project (cwd), first user message,
    user_turn_count, model, git_branch. Use this to survey what was worked on
    and pick interesting sessions to read in full.

    min_user_turns: skip sessions with fewer human-typed turns than this.
    Useful default once the vault has many entries: 5 or 10 to skip drive-bys.
    project_filter: case-insensitive substring match against the project path
    (cwd). Use to focus the digest on one repo.
    """
    return [
        s.to_dict()
        for s in claude_code.list_recent(
            days=days,
            min_user_turns=min_user_turns,
            project_filter=project_filter,
        )
    ]


@mcp.tool()
def read_session(
    session_id: str,
    format: str = "summary",
    max_turns: int = 200,
) -> dict[str, Any]:
    """Read the transcript of one Claude Code session.

    format="summary" (default): human-typed user turns + assistant text replies.
    Tool calls, tool results, thinking blocks, and meta wrappers are stripped.
    Best for understanding what happened.
    format="full": raw JSONL records. Use only if summary is missing detail.

    max_turns caps the summary output (default 200). Long sessions are
    truncated by keeping the head and tail; check `truncated` in the response.
    session_id values come from list_recent_sessions.
    """
    return claude_code.read_session(
        session_id=session_id,
        format=format,
        max_turns=max_turns,
    )


@mcp.tool()
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
    """Save one learning from a coding session to the vault (~/.ship-and-tell/vault.jsonl).

    Required: title (5-10 words), lesson (1-2 sentences, generalized).
    Optional drafts: tweet (<=280 chars), thread, article. Provide whichever
    fit the insight -- not every lesson needs all three.
    Returns the saved entry including its generated id.
    """
    return vault.save_insight(
        title=title,
        lesson=lesson,
        project=project,
        problem=problem,
        root_cause=root_cause,
        tweet=tweet,
        thread=thread,
        article=article,
        source_session_id=source_session_id,
        tags=tags,
    )


@mcp.tool()
def list_vault(
    limit: int = 20,
    since_days: int | None = None,
    posted: bool | None = None,
) -> list[dict[str, Any]]:
    """List previously saved insights from the vault, most recent first.

    posted=None returns all; True returns only posted; False returns only unposted.
    Use this to build the weekly digest, find unposted tweets, or dedupe
    before saving a new insight that may already exist.
    """
    return vault.list_vault(limit=limit, since_days=since_days, posted=posted)


@mcp.tool()
def update_insight(
    insight_id: str,
    title: str | None = None,
    project: str | None = None,
    problem: str | None = None,
    root_cause: str | None = None,
    lesson: str | None = None,
    tweet: str | None = None,
    thread: str | None = None,
    article: str | None = None,
    source_session_id: str | None = None,
    tags: list[str] | None = None,
    posted: bool | None = None,
) -> dict[str, Any]:
    """Edit an existing vault entry. Only fields you pass are updated.

    Use this when the user asks to tweak a draft, fix a typo, retag, or set
    `posted=True/False`. id and created_at are immutable.
    """
    fields = {
        k: v
        for k, v in {
            "title": title,
            "project": project,
            "problem": problem,
            "root_cause": root_cause,
            "lesson": lesson,
            "tweet": tweet,
            "thread": thread,
            "article": article,
            "source_session_id": source_session_id,
            "tags": tags,
            "posted": posted,
        }.items()
        if v is not None
    }
    return vault.update_insight(insight_id, **fields)


@mcp.tool()
def mark_posted(insight_id: str, posted: bool = True) -> dict[str, Any]:
    """Mark a vault entry as posted (or set posted=False to unmark)."""
    return vault.mark_posted(insight_id, posted=posted)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
