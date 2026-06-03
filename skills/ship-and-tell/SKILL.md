---
name: ship-and-tell
description: Mine the user's recent Claude Code sessions, subagent transcripts, and git activity for shareable insights -- tweet drafts, thread skeletons, article ideas -- and produce a weekly digest. Use when the user asks for "tweet ideas", "weekly digest", "what did I learn this week", "ship and tell", "/weekly", "/ship-it", or similar. Requires the `ship-and-tell` MCP server (tools: list_recent_sessions, read_session, list_subagents, read_subagent, read_git_activity, save_insight, list_vault, update_insight, mark_posted).
---

# Ship & Tell

Turn recent coding sessions into shareable insights. The MCP tools provide structured access to transcripts, git activity, and a local vault; you (the host LLM) do the writing.

## Required MCP tools

- `list_recent_sessions(days, min_user_turns, project_filter)` -- survey recent sessions. Each entry includes `subagent_count`; flag sessions with `subagent_count >= 3` for deep reads.
- `read_session(session_id, format, max_turns, include_subagents, max_subagent_turns)` -- read one session. Default reads parent only. Pass `include_subagents="summary"` for sessions with many subagents: this strips the parent's redundant tool_result for each Agent call and appends each subagent's transcript in its own section, so investigative content appears EXACTLY ONCE.
- `list_subagents(parent_session_id)` -- cheap index of subagents for a session (agent_type, description, message_count). Useful when you only want titles, not transcripts.
- `read_subagent(parent_session_id, agent_id, format, max_turns)` -- read one subagent's transcript. The first turn has role="agent_task" (auto-generated task brief from the parent), not role="user".
- `read_git_activity(repo_path, since_days)` -- list commits + shortstat for a repo. Pair with read_session to separate "discussed" from "shipped".
- `save_insight(...)` -- persist a draft to the vault.
- `list_vault(limit, since_days, posted)` -- pull saved entries; pass `posted=False` for unposted.
- `update_insight(insight_id, ...)` -- edit a draft.
- `mark_posted(insight_id, posted)` -- flag a draft as posted/unposted.

If these tools are not available, tell the user the `ship-and-tell` MCP server is not installed and stop. Do not fall back to guessing.

## Workflow

1. Call `list_vault(since_days=14)` first so you can dedupe.
2. Call `list_recent_sessions(days=7, min_user_turns=5)` (or whatever range the user asks for).
3. Pick the 5-10 most interesting sessions. Prefer ones with: a real bug fix, an architecture/library decision, a debugging arc that revealed a root cause, a performance change, or a surprising failure mode (AI agent, deploy platform, library). Skip trivial sessions (one-off questions, quick edits).
4. For each pick:
   - Decide depth based on `subagent_count` from step 2:
     - 0-2 subagents: `read_session(session_id, format="summary")`.
     - 3+ subagents: `read_session(session_id, format="summary", include_subagents="summary")`. The investigative thinking lives in subagents, not the parent -- and the data layer guarantees no double-counting (parent tool_results are dropped; subagent content appears once per `subagent_section`).
   - Treat `agent_task` turns as the task brief the parent gave the subagent, NOT the user's intent. Treat `subagent_marker` turns as breadcrumbs showing where in the parent conversation each subagent was invoked.
   - Call `read_git_activity(repo_path=<session's project>, since_days=...)` to see what actually shipped during the session's window. Prefer lessons that map to real commits -- if you can name the sha, the lesson is real.
5. For every distinct lesson worth keeping, call `save_insight` with:
   - `title`: 5-10 word handle.
   - `lesson`: 1-2 sentences, generalized. The reusable learning, not the narrative.
   - `problem` + `root_cause`: when the session was a debugging arc.
   - `tweet`: a single tweet draft (<= 280 chars). Conversational, specific, no hashtag spam. A good tweet has a surprise or a concrete number.
   - `thread`: bullet-form skeleton when the lesson has more depth than fits one tweet.
   - `article`: working title + one-paragraph outline when it warrants a blog post.
   - `source_session_id`: the session_id you read.
   - `project`: the project field from the session metadata.
6. Output a digest to the user in this shape:

   ```
   This week you:
   ✓ N bugs fixed
   ✓ N architecture decisions
   ✓ N production incidents (if any)

   Top Tweet Ideas:
   1. <tweet>
   2. <tweet>
   3. <tweet>

   Article Ideas:
   1. <title> -- <one-line hook>
   2. <title> -- <one-line hook>
   ```

## Quality bar

- **Don't fabricate.** If the transcript doesn't reveal the root cause, leave `root_cause` empty. Don't invent narrative.
- **Dedupe.** Skip lessons already in the vault (check the `list_vault` output from step 1).
- **Don't double-count subagents.** When `include_subagents="summary"` is on, the data layer drops the parent's tool_result for each matched Agent call -- so subagent content appears once. But the parent's own assistant text often *restates* a subagent's conclusion: count that as one insight, not two.
- **Be selective.** Five saved insights with sharp tweets beats fifteen mediocre ones. If a "lesson" is generic ("test your code", "read docs") -- skip it.
- **Voice.** Match the user's voice from the transcripts. If they're terse, tweets are terse. If they're playful, tweets are playful. Don't default to LinkedIn-speak.
