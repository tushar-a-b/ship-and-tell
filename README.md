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

# 1. Install the package into a venv
python3 -m venv .venv
.venv/bin/pip install -e .

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

The vault lives at `~/.ship-and-tell/vault.jsonl` — append-only, one insight per line. Edit it by hand, grep it, version it, whatever you want.

## MCP tools

| Tool | Purpose |
|---|---|
| `list_recent_sessions(days=7)` | Survey recent Claude Code sessions: id, project, first user message, turn count. |
| `read_session(session_id, format, max_turns)` | Read one session. `format="summary"` strips tool noise; `format="full"` returns raw JSONL. Long sessions auto-truncate head+tail. |
| `save_insight(title, lesson, tweet, thread, article, ...)` | Append one insight to the vault. |
| `list_vault(limit, since_days)` | Read the vault back. |

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
| Git | ⏳ | Planned: `git log` / `git diff` per repo touched |

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
- **v0.2** — Git activity adapter; `Stop` hook for Claude Code that flags tweet-worthy moments as a session ends (the "killer feature" from the spec).
- **v0.3** — Cursor SQLite adapter; richer scoring (tweet_score, recruiter_signal, uniqueness).
- **v1** — Optional standalone CLI (`shipandtell weekly`) for cron / non-agent use.

## Config

| Env var | Default | Purpose |
|---|---|---|
| `SHIP_AND_TELL_HOME` | `~/.ship-and-tell` | Vault directory. Override to keep multiple vaults (work vs personal). |

## License

TBD.
