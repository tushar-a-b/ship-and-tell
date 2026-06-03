# Ship & Tell

Turn your coding sessions into tweets, articles, and engineering insights — without sending your transcripts to an external API.

Ship & Tell is an **MCP server + Claude Code skill** that mines your local agent transcripts (Claude Code today; Codex / OpenCode / Cursor next) and lets your coding agent itself do the writing. No separate API key, no separate billing, no data leaving your machine — the host agent's existing login is the engine.

## Why

You spend hours building things with Claude Code, Codex, Cursor. Then you forget the bugs, the architecture decisions, the tweet-worthy insights. Ship & Tell extracts what you built, what you fixed, what you learned, and what's worth sharing — and stores it in a local vault you actually own.

## How it works

```
┌───────────────────────┐    ┌──────────────────────┐    ┌───────────────────┐
│  Agent transcripts    │    │  Ship & Tell MCP     │    │  Local vault      │
│  ~/.claude/projects/  │───▶│  (structured I/O)    │───▶│  ~/.ship-and-tell │
│  ~/.codex/sessions/   │    │                      │    │  /vault.jsonl     │
│  ~/.local/share/...   │    │                      │    │                   │
└───────────────────────┘    └──────────┬───────────┘    └───────────────────┘
                                        │
                                        ▼ MCP tools
                             ┌──────────────────────┐
                             │  Host agent's LLM    │
                             │  (Claude Code, etc.) │
                             │  drafts the content  │
                             └──────────────────────┘
```

The MCP server provides structured access to past sessions and a vault for saved insights. The **host agent's own LLM** does all the reading, extraction, and writing — Ship & Tell makes no external API calls.

## Install

Requires Python 3.10+ and a working `claude` CLI.

```bash
git clone <this repo> ship-and-tell
cd ship-and-tell

# 1. Install the package into a venv (add the [ui] extras if you want the Streamlit viewer)
python3 -m venv .venv
.venv/bin/pip install -e '.[ui]'

# 2. Register the MCP server with Claude Code
claude mcp add ship-and-tell -- "$PWD/.venv/bin/ship-and-tell-mcp"

# 3. Install the skill (symlink so edits hot-reload)
mkdir -p ~/.claude/skills
ln -s "$PWD/skills/ship-and-tell" ~/.claude/skills/ship-and-tell
```

Open a new Claude Code session to pick up both.

## Usage

In Claude Code, just ask:

> *"run the ship-and-tell weekly digest"*

> *"what did I learn this week worth tweeting?"*

> *"draft tweets from my coding sessions in the last 3 days"*

The skill activates, calls the MCP tools, drafts content, saves it to the vault, and prints a digest:

```
This week you:
✓ 3 bugs fixed
✓ 2 architecture decisions
✓ 1 production incident

Top Tweet Ideas:
1. ...
2. ...
3. ...

Article Ideas:
1. ...
2. ...
```

To browse what's been saved:

> *"show me my unposted tweets from the ship-and-tell vault"*

The vault lives at `~/.ship-and-tell/vault.jsonl` — one insight per line. Edit it by hand, grep it, version it, whatever you want.

### Streamlit UI

For a visual browser over the vault and recent sessions:

```bash
.venv/bin/ship-and-tell-ui
```

Opens at `http://localhost:8501`. Pick an agent (Claude Code today; Codex / OpenCode / Cursor / Gemini show as *coming soon*), filter recent sessions by project / minimum turn count, browse saved insights with tweet/thread/article tabs, and toggle the **Mark posted** / **Mark unposted** button per entry. Generation still happens inside Claude Code via the MCP server — the UI is for *managing* drafts, not creating them.

## MCP tools

| Tool | Purpose |
|---|---|
| `list_recent_sessions(days=7, min_user_turns=0, project_filter=None)` | Survey recent Claude Code sessions: id, project, first user message, turn count, **subagent_count**. Filter to skip drive-bys or focus on one repo. |
| `read_session(session_id, format="summary", max_turns=200, include_subagents="none", max_subagent_turns=40)` | Read one session. `include_subagents="summary"` appends each subagent's transcript in its own section and drops the parent's redundant tool_result, so each piece of investigative content appears exactly once. |
| `list_subagents(parent_session_id)` | Cheap index of subagents spawned from a session: agent_type, description, message_count. |
| `read_subagent(parent_session_id, agent_id, format="summary", max_turns=100)` | Read one subagent's transcript. First turn is `role="agent_task"` (the parent's brief), not `user`. |
| `read_git_activity(repo_path, since_days=7, since, until, max_commits=50, author)` | Commits + shortstat + top-touched files for a repo over a window. |
| `save_insight(title, lesson, tweet, thread, article, ...)` | Append one insight to the vault. |
| `list_vault(limit=20, since_days=None, posted=None)` | Read the vault back. `posted=False` returns unposted only; `True` returns posted only. |
| `update_insight(insight_id, ...)` | Edit any mutable field on an existing entry. |
| `mark_posted(insight_id, posted=True)` | Toggle the posted flag. |

## Use it from other agents

The MCP server is host-agnostic. To register it elsewhere:

- **Codex CLI:** add to `~/.codex/config.toml` MCP servers section.
- **OpenCode:** add to `opencode.json` MCP servers.
- **Cursor:** add to Cursor's MCP settings.
- **Gemini CLI:** add to `~/.gemini/settings.json`.

Point each to `/<path-to-repo>/.venv/bin/ship-and-tell-mcp`. The tools work the same way; only Claude Code currently gets the dedicated skill.

## Source adapter coverage

| Source | Reads | Notes |
|---|---|---|
| Claude Code | ✅ | `~/.claude/projects/<slug>/*.jsonl` |
| Codex CLI | ⏳ | Planned: `~/.codex/sessions/<year>/...` |
| OpenCode | ⏳ | Planned: `~/.local/share/opencode/storage/...` |
| Cursor | ⏳ | Planned: SQLite `state.vscdb` under `workspaceStorage/` |
| Gemini CLI | ⏳ | Planned (location TBD) |
| Git | ✅ | `git log --shortstat` + top-touched files per repo, scoped by time window |

## Vault entry shape

```json
{
  "id": "uuid",
  "created_at": "2026-06-03T...",
  "title": "Cloudflare CPU limit",
  "project": "/Users/.../CurrentAffairsAI",
  "problem": "Workers exceeded CPU budget during SSR",
  "root_cause": "Heavy LLM call inside the request path",
  "lesson": "Platform limits matter more than code quality.",
  "tweet": "...",
  "thread": "...",
  "article": "...",
  "source_session_id": "9946854a-...",
  "tags": ["cloudflare", "deploy"],
  "posted": false
}
```

## Roadmap

- **v0.1** — Codex + OpenCode source adapters.
- **v0.2** — `Stop` hook for Claude Code that flags tweet-worthy moments as a session ends (the "killer feature" from the spec).
- **v0.3** — Cursor SQLite adapter; richer scoring (tweet_score, recruiter_signal, uniqueness).
- **v1** — Optional standalone CLI (`shipandtell weekly`) for cron / non-agent use.

Shipped already: Claude Code source adapter, git activity adapter, Streamlit vault/sessions UI, atomic vault edits.

## Config

| Env var | Default | Purpose |
|---|---|---|
| `SHIP_AND_TELL_HOME` | `~/.ship-and-tell` | Vault directory. Override to keep multiple vaults (work vs personal). |

## License

TBD.
