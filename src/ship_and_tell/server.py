"""MCP server for Ship & Tell.

Exposes structured access to the user's coding-agent transcripts and a local
JSONL vault for saved insights. The host agent (Claude Code, Cursor, OpenCode,
Codex CLI, Gemini CLI) does all the LLM work via its own model and login --
this server adds no external API calls.
"""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from . import claude_code, git_activity, vault

mcp = FastMCP("ship-and-tell")


@mcp.tool()
def list_recent_sessions(
    days: int = 7,
    min_user_turns: int = 0,
    project_filter: str | None = None,
) -> list[dict[str, Any]]:
    """List Claude Code coding sessions from the last N days.

    Returns metadata per session: session_id, project (cwd), first user message,
    user_turn_count, model, git_branch, subagent_count. Use this to survey
    what was worked on and pick interesting sessions to read in full.

    subagent_count tells you how many Agent tool invocations spawned a
    sub-transcript. Sessions with subagent_count >= 3 are usually the ones
    with the richest investigative content -- call read_session with
    include_subagents="summary" on those.

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
    include_subagents: str = "none",
    max_subagent_turns: int = 40,
) -> dict[str, Any]:
    """Read the transcript of one Claude Code session.

    format="summary" (default): human-typed user turns + assistant text replies.
    Tool calls, tool results, thinking blocks, and meta wrappers are stripped.
    format="full": raw JSONL records. Use only if summary is missing detail.

    include_subagents:
      "none" (default) -- parent transcript only.
      "summary" -- inserts a subagent_marker turn at each Agent invocation
        point in the parent, then appends each subagent's own summary in
        `subagent_sections`. The parent's redundant tool_result for each
        Agent call was already excluded by the summary path, so each piece
        of subagent content appears EXACTLY ONCE in its dedicated section.
        Use on sessions where subagent_count >= 3 -- the investigative
        thinking lives there.
      "full" -- raw JSONL per subagent. Heavy; rarely needed.

    max_turns caps the parent summary (default 200). Long sessions are
    truncated head+tail (check `truncated`). max_subagent_turns caps each
    individual subagent summary (default 40).

    session_id values come from list_recent_sessions. subagent_marker turns
    in the output use role="subagent_marker"; the synthetic first "user" turn
    of each subagent uses role="agent_task" so you don't mistake the
    auto-generated task brief for human input.
    """
    return claude_code.read_session(
        session_id=session_id,
        format=format,
        max_turns=max_turns,
        include_subagents=include_subagents,
        max_subagent_turns=max_subagent_turns,
    )


@mcp.tool()
def list_subagents(parent_session_id: str) -> list[dict[str, Any]]:
    """List subagents (Agent tool invocations) spawned from a parent session.

    Each entry: parent_session_id, agent_id, agent_type (Explore/Plan/
    general-purpose/etc), description (the parent's task brief), started_at,
    message_count, model. Use as a cheaper alternative to read_session with
    include_subagents="summary" when you only need the index.
    """
    return [s.to_dict() for s in claude_code.list_subagents(parent_session_id)]


@mcp.tool()
def read_subagent(
    parent_session_id: str,
    agent_id: str,
    format: str = "summary",
    max_turns: int = 100,
) -> dict[str, Any]:
    """Read one subagent's transcript.

    Returns parent_session_id, agent_id, agent_type, description, and the
    same turns shape as read_session. The first turn has role="agent_task"
    (the auto-generated task brief from the parent), not role="user", to
    keep the digest LLM from treating it as human input.
    """
    return claude_code.read_subagent(
        parent_session_id=parent_session_id,
        agent_id=agent_id,
        format=format,
        max_turns=max_turns,
    )


@mcp.tool()
def read_git_activity(
    repo_path: str,
    since_days: int | None = 7,
    since: str | None = None,
    until: str | None = None,
    max_commits: int = 50,
    author: str | None = None,
) -> dict[str, Any]:
    """Read git commits + shortstat for a repo over a time window.

    Use alongside read_session: the transcript tells you what was *discussed*;
    this tells you what was *actually committed*. The intersection is usually
    where the tweet-worthy lessons live -- a thing you argued about and shipped.

    `repo_path` is typically the `project` field from list_recent_sessions.
    Either pass `since_days` (default 7) or `since`/`until` (git relative or
    ISO forms, e.g. "2026-06-01"). Errors come back in the `error` field
    instead of as exceptions, so you can call this without try/except.
    """
    return git_activity.read_activity(
        repo_path=repo_path,
        since_days=since_days,
        since=since,
        until=until,
        max_commits=max_commits,
        author=author,
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
