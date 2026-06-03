---
name: ship-and-tell
description: Mine the user's recent Claude Code sessions for shareable insights -- tweet drafts, thread skeletons, article ideas -- and produce a weekly digest. Use when the user asks for "tweet ideas", "weekly digest", "what did I learn this week", "ship and tell", "/weekly", "/ship-it", or similar. Requires the `ship-and-tell` MCP server to be installed (tools: list_recent_sessions, read_session, save_insight, list_vault).
---

# Ship & Tell

Turn recent coding sessions into shareable insights. The MCP tools provide structured access to transcripts and a local vault; you (the host LLM) do the writing.

## Required MCP tools

- `list_recent_sessions(days)` -- survey recent sessions.
- `read_session(session_id, format)` -- read one session (use `format="summary"`).
- `save_insight(...)` -- persist a draft to the vault.
- `list_vault(limit, since_days)` -- pull saved entries.

If these tools are not available, tell the user the `ship-and-tell` MCP server is not installed and stop. Do not fall back to guessing.

## Workflow

1. Call `list_vault(since_days=14)` first so you can dedupe.
2. Call `list_recent_sessions(days=7)` (or whatever range the user asks for).
3. Pick the 5-10 most interesting sessions. Prefer ones with: a real bug fix, an architecture/library decision, a debugging arc that revealed a root cause, a performance change, or a surprising failure mode (AI agent, deploy platform, library). Skip trivial sessions (one-off questions, quick edits).
4. For each pick, call `read_session(session_id, format="summary")`. Read for the *generalizable* lesson, not just "I did X".
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
- **Be selective.** Five saved insights with sharp tweets beats fifteen mediocre ones. If a "lesson" is generic ("test your code", "read docs") -- skip it.
- **Voice.** Match the user's voice from the transcripts. If they're terse, tweets are terse. If they're playful, tweets are playful. Don't default to LinkedIn-speak.
