---
name: ship-and-tell
description: Mine the user's recent Claude Code sessions, subagent transcripts, git activity, and GitHub PRs/commits/releases for shareable insights -- tweet drafts written in plain English with a pro voice, anchored to actual shipped artifacts. Use when the user asks for "tweet ideas", "weekly digest", "what did I learn this week", "ship and tell", "/weekly", "/ship-it", or similar. Requires the `ship-and-tell` MCP server (tools: list_recent_sessions, read_session, list_subagents, read_subagent, list_my_pull_requests, list_my_commits, list_my_releases, read_git_activity, save_insight, list_vault, update_insight, mark_posted, delete_insight).
---

# Ship & Tell

Turn recent coding sessions into shareable insights. The MCP tools provide structured access to transcripts, git activity, and a local vault; you (the host LLM) do the writing.

## Required MCP tools

- `list_recent_sessions(days, min_user_turns, project_filter)` -- survey recent sessions. Each entry includes `subagent_count`; flag sessions with `subagent_count >= 3` for deep reads.
- `read_session(session_id, format, max_turns, include_subagents, max_subagent_turns)` -- read one session. Default reads parent only. Pass `include_subagents="summary"` for sessions with many subagents: this strips the parent's redundant tool_result for each Agent call and appends each subagent's transcript in its own section, so investigative content appears EXACTLY ONCE.
- `list_subagents(parent_session_id)` -- cheap index of subagents for a session (agent_type, description, message_count). Useful when you only want titles, not transcripts.
- `read_subagent(parent_session_id, agent_id, format, max_turns)` -- read one subagent's transcript. The first turn has role="agent_task" (auto-generated task brief from the parent), not role="user".
- `read_git_activity(repo_path, since_days)` -- list commits + shortstat for a local repo. Pair with read_session to separate "discussed" from "shipped" when the repo is on disk.
- `list_my_pull_requests(usernames, since_days, state)` -- GitHub PRs authored by the user(s), via the `gh` CLI. PR title + body is usually the single strongest tweet-anchor signal. Returns `url` for each PR.
- `list_my_commits(usernames, repos, since_days)` -- GitHub commits by author across repos the active gh account can see.
- `list_my_releases(repos, since_days)` -- GitHub releases (often the best source for launch posts; release-notes body is curated copy).
- `save_insight(...)` -- persist a draft to the vault.
- `list_vault(limit, since_days, posted)` -- pull saved entries; pass `posted=False` for unposted.
- `update_insight(insight_id, ...)` -- edit a draft.
- `mark_posted(insight_id, posted)` -- flag a draft as posted/unposted.
- `delete_insight(insight_id)` -- permanently remove a bad draft from the vault.

Each `save_insight` and `update_insight` accepts a `links` list of dicts like `[{"type": "pr", "url": "...", "label": "PR #72: ..."}]`. Always attach at least one link when there's a real shipped artifact (PR > release > commit > local-commit > issue > session). For pure design/ops insights with no shipped artifact, link the session id as `type: "session"`.

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
   - `tweet`: a single-post draft. Default to fitting 280 chars (single tweet, free-tier safe). If the user has X Premium (check user memory), longer is fine when length is *earned* -- a story arc, a code block, a multi-step reveal -- not when it's padding. **Open cold** (see "Cold reader rule" below). Conciseness still wins engagement; never pad just because you can.
   - `thread`: bullet-form skeleton when the lesson needs multiple posts or a numbered breakdown. Same cold-reader rule applies to the first bullet.
   - `article`: working title + one-paragraph outline when it warrants a blog post.
   - `source_session_id`: the session_id you read.
   - `project`: the project field from the session metadata.

## Cold reader rule (non-negotiable for tweet/thread/article)

**Every draft must open with what the user is building, then the immediate problem or attempt. The punchline comes last, not first.**

Before saving any insight, read its tweet aloud as if you have never heard of the user's projects. If, after 5 seconds, a stranger cannot identify (a) what the system does and (b) what the problem was, **the tweet is broken** -- rewrite the opening before saving.

✅ **Good opener patterns:**
- "Building a {one-line system description}. {Symptom or attempted fix}."
- "I shipped {thing}. {Unexpected outcome}."
- "{Specific technology / tool} returned {surprising behavior} when {context}."

❌ **Broken opener patterns (these all kill cold readers):**
- Opening with an undefined domain term: "The signed_fields array...", "Dispute enters commit_phase...", "Sub-agents and parent sessions...".
- Opening with the punchline: "State machines pin participants" -- great line, but only after the setup.
- Assuming the reader is already in the project.

**Exception:** universal, technology-only lessons (e.g., HTTP-vs-websocket error reporting, Python relative-imports semantics) can skip project context because the technology itself IS the context. Judgement call -- if the lesson would be just as true in any project, project setup is optional. If the lesson depends on the user's specific stack, project setup is mandatory.

**Voice is style, not information.** "Match the user's terse voice" means short sentences and direct words. It does NOT mean drop the setup. A terse tweet still says what it is about.

## Plain-English rule (paired with cold reader)

After the cold-reader check, run a second gut-check: **would a non-engineer friend understand what's happening in sentence 1?** If you used a term that's only meaningful to someone deep in the stack ("subagent-aware summaries", "tool_result block", "canonical bytes", "MV3 service worker") in the opener, rewrite it. Move precise terms later in the draft once context is established, or swap them for plain analogues ("a helper agent", "the field stored when the tool replied", "the bytes the signature actually covers", "the background script that lives across browser pages").

The user has explicitly asked for "the same level of explanation" as the [ship-and-tell ca24007](https://github.com/tushar-a-b/ship-and-tell/commit/ca24007) tweet rewrite: ordinary words in the first paragraph, precise vocabulary later, end with a transferable principle.

## Pro voice / recruiter-signal rule

Tweets should make the author's handle look like a senior engineer's: calm, anchored to real shipped work, judgment visible. Concrete checklist before saving any tweet:

1. **Anchored to shipped artifact.** Attach a PR / commit / release URL via the `links` field whenever one exists. If the lesson was a runtime/ops discovery with no code change, link the source session id with `type: "session"`. Insights with no anchor at all should be the exception, not the rule.
2. **Names the tradeoff.** "I picked X over Y because Z" reads as judgment. "I learned about X" reads as a student.
3. **Specific numbers and proper nouns.** "21 jsonls → 125 transcripts" > "a lot more than expected". "ML-DSA-65 signature" > "crypto signature". Specificity signals depth, but introduce precise nouns AFTER plain-English setup.
4. **Calm declarative voice.** "Here's what happened. Here's why." Not "OMG", not "🤯", not "you won't believe".
5. **Investigation visible.** Show the steps of the trace, not just the conclusion. "Then I traced through verification" > "Then I realized".
6. **Failure-accepting.** "Was about to add Y. Was wrong" is a stronger pro signal than silence about the wrong direction.
7. **Transferable principle at the end.** A single quotable line at the end that another engineer can apply elsewhere ("Dedupe with code, not prompts" / "Seed before you file") makes the post quotable beyond your project.

**Never use Co-Authored-By Claude, "Generated with Claude Code", or any AI-attribution trailer in commit messages, PR bodies, gh comments, or release notes when committing on this user's behalf.** This is a permanent user preference -- see the user memory entry.
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
