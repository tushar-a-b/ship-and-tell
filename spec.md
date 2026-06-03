This is actually a very good project because it solves a problem you've personally experienced:

> "I spend hours building things with Claude Code, Codex, Cursor, OpenCode, etc. Then I forget the lessons, bugs, architecture decisions, and tweet-worthy insights."

The spec should focus on that problem first.

---

# Ship & Tell

### Tagline

Turn coding sessions into tweets, articles, changelogs, and engineering insights automatically.

---

# Problem Statement

Engineers solve dozens of interesting problems every week:

* bugs
* production incidents
* architecture decisions
* deployment issues
* performance improvements
* AI agent failures

Most of these lessons are lost.

Ship & Tell automatically extracts:

* what was built
* what was fixed
* what was learned
* what is worth sharing

from coding sessions and git activity.

---

# Target Users

### Primary

* Claude Code users
* Cursor users
* OpenCode users
* Codex users
* AI-assisted developers

### Secondary

* Indie hackers
* Open source maintainers
* Engineering managers
* Developer advocates

---

# V1 Goal

At the end of the week the developer should receive:

```text
This week you:

✓ Fixed 3 bugs
✓ Made 2 architecture decisions
✓ Solved 1 production incident

Top Tweet Ideas:
...
...
...

Article Ideas:
...
...
...
```

---

# Inputs

## Source 1: Coding Agent Conversations

Support:

* Claude Code
* Cursor
* OpenCode
* Codex CLI
* Gemini CLI

Input:

```text
chat transcripts
```

---

## Source 2: Git

Read:

```bash
git log
git diff
git show
```

Extract:

* features
* bug fixes
* refactors

---

## Source 3: PRs

Optional V2

GitHub integration.

---

# Core Pipeline

```text
Agent Chats
        +
Git History
        +
PRs

      ↓

Activity Extractor

      ↓

Learning Detector

      ↓

Content Generator

      ↓

Content Vault
```

---

# Module 1: Activity Extractor

Purpose:

Turn raw chats into structured activities.

Example:

Input:

```text
Spent 2 hours debugging Cloudflare Workers.
Found CPU limit causing Error 1102.
Moved deployment to Vercel.
```

Output:

```json
{
  "type": "production_incident",
  "title": "Cloudflare CPU limit",
  "project": "CurrentAffairsAI",
  "summary": "Workers exceeded CPU budget."
}
```

---

# Module 2: Learning Detector

This is the secret sauce.

Prompt:

```text
Analyze this activity.

Identify:

- Root cause
- Lesson learned
- Engineering insight
- Tradeoff discovered
- Tweet potential
```

Output:

```json
{
  "lesson": "Platform limits matter more than code quality.",
  "tweet_worthy": true
}
```

---

# Module 3: Content Scorer

Every lesson gets scores:

```json
{
  "technical_depth": 9,
  "recruiter_signal": 10,
  "uniqueness": 8,
  "tweet_score": 9
}
```

---

# Module 4: Content Generator

Generate:

## Tweet

```text
My Next.js app worked perfectly...

Until Cloudflare Workers hit CPU limits.
```

---

## Thread

```text
Thread:
How Error 1102 taught me...
```

---

## Article

```text
Title:
Why I Moved from Cloudflare Workers to Vercel
```

---

# Module 5: Content Vault

Store:

```json
{
  "id": "...",
  "created_at": "...",
  "project": "CurrentAffairsAI",
  "problem": "...",
  "root_cause": "...",
  "lesson": "...",
  "tweet": "...",
  "thread": "...",
  "article": "...",
  "posted": false
}
```

---

# Weekly Digest

Command:

```bash
shipandtell weekly
```

Output:

```text
Top Learnings This Week

1. Cloudflare CPU Limit
2. Metadata Drift
3. Hybrid Retrieval

Top Tweets

...
...
...

Top Article Ideas

...
...
...
```

---

# CLI Commands

```bash
shipandtell scan

shipandtell weekly

shipandtell tweets

shipandtell articles

shipandtell digest
```

---

# V1 Tech Stack

Since you're strongest here:

Backend:

* FastAPI

Storage:

* PostgreSQL

LLM:

* OpenAI
* Claude
* Local models

Frontend:

* Next.js

CLI:

* Typer (Python)

---

# Killer Feature (V2)

The feature I'd build after launch:

```bash
shipandtell watch
```

Runs in background.

When Claude Code session ends:

```text
⚡ Detected tweet-worthy insight:

"Cloudflare Workers CPU limit caused SSR failure"

Generate content? [Y/n]
```

This is the feature that turns Ship & Tell from a tool into a daily companion.

---

If you build only V1 correctly, you'll solve your own problem first: **never losing tweet/article ideas from your engineering work again.** That's usually the sign of a good product.
