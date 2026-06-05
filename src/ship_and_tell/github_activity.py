"""Source adapter for the user's GitHub activity (PRs, commits, releases).

Uses the `gh` CLI so we ride on the user's existing auth -- no separate
PAT to store, no third-party service. The active gh account is whatever
`gh auth status` reports; secondary accounts can be queried by passing
their usernames in `usernames`, which gives access to any repos the
active account can see.

For private repos that the active gh account cannot see (e.g., a personal
repo owned by a second identity not currently authed), prefer the local
`git_activity` adapter -- it reads from the working tree, no GitHub round
trip required.
"""

from __future__ import annotations

import json
import subprocess
from datetime import datetime, timedelta, timezone
from typing import Any


def _run(args: list[str], timeout: float = 20.0) -> tuple[int, str, str]:
    try:
        p = subprocess.run(
            ["gh", *args], capture_output=True, text=True, timeout=timeout
        )
        return p.returncode, p.stdout, p.stderr
    except FileNotFoundError:
        return 127, "", "gh CLI not installed"
    except subprocess.TimeoutExpired:
        return 124, "", "gh command timed out"


def _run_json(args: list[str], timeout: float = 20.0) -> tuple[bool, Any]:
    rc, out, err = _run(args, timeout=timeout)
    if rc != 0:
        return False, err.strip() or f"gh exited {rc}"
    if not out.strip():
        return True, []
    try:
        return True, json.loads(out)
    except json.JSONDecodeError as e:
        return False, f"JSON parse error: {e}"


def list_authed_accounts() -> list[str]:
    """Return the GitHub usernames currently logged in via `gh auth status`."""
    rc, out, err = _run(["auth", "status"], timeout=5.0)
    if rc != 0:
        return []
    accounts: list[str] = []
    for line in (out + "\n" + err).splitlines():
        line = line.strip()
        if "Logged in to" in line and "account" in line:
            tail = line.split("account", 1)[1].strip()
            user = tail.split()[0] if tail else ""
            if user and user not in accounts:
                accounts.append(user)
    return accounts


def _since_iso(since_days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=since_days)).date().isoformat()


def list_pull_requests(
    usernames: list[str] | None = None,
    since_days: int = 14,
    state: str = "merged",
    limit: int = 50,
) -> dict[str, Any]:
    """List PRs authored by each user, filtered by state and time window.

    state: "merged" | "open" | "closed" | "all"
    """
    if usernames is None:
        usernames = list_authed_accounts() or ["@me"]
    since = _since_iso(since_days)
    since_full = f"{since}T00:00:00Z"

    out_prs: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []

    for user in usernames:
        author = "@me" if user == "@me" else user
        args = [
            "search", "prs",
            "--author", author,
            "--limit", str(limit),
            "--json", "title,url,number,repository,state,closedAt,createdAt,body",
        ]
        if state == "merged":
            args.append("--merged")
        elif state == "open":
            args += ["--state", "open"]
        elif state == "closed":
            args += ["--state", "closed"]

        ok, data = _run_json(args)
        if not ok:
            errors.append({"username": user, "error": str(data)})
            continue
        for it in data:
            ts = it.get("closedAt") or it.get("createdAt") or ""
            if ts and ts < since_full:
                continue
            repo = it.get("repository") or {}
            out_prs.append(
                {
                    "username": user,
                    "repo": repo.get("nameWithOwner", "") if isinstance(repo, dict) else "",
                    "number": it.get("number"),
                    "title": it.get("title", ""),
                    "url": it.get("url", ""),
                    "state": it.get("state", ""),
                    "closed_at": it.get("closedAt"),
                    "created_at": it.get("createdAt"),
                    "body_preview": (it.get("body") or "")[:500],
                }
            )

    out_prs.sort(key=lambda p: p.get("closed_at") or p.get("created_at") or "", reverse=True)
    return {
        "usernames": usernames,
        "since_days": since_days,
        "state": state,
        "pull_requests": out_prs,
        "errors": errors,
    }


def _resolve_me(user: str) -> str:
    if user != "@me":
        return user
    ok, data = _run_json(["api", "user", "--jq", ".login"])
    if not ok:
        return user
    if isinstance(data, list):
        return data[0] if data else user
    if isinstance(data, str):
        return data
    return user


def _user_repos(since_iso: str, max_repos: int = 30) -> list[str]:
    ok, data = _run_json(
        [
            "api",
            "/user/repos?per_page=100&sort=pushed&direction=desc",
            "--jq",
            "[.[] | {full_name: .full_name, pushed_at: .pushed_at}]",
        ]
    )
    if not ok or not isinstance(data, list):
        return []
    return [
        r["full_name"]
        for r in data
        if isinstance(r, dict) and r.get("pushed_at", "") >= since_iso
    ][:max_repos]


def list_commits(
    usernames: list[str] | None = None,
    repos: list[str] | None = None,
    since_days: int = 7,
    limit_per_repo: int = 30,
) -> dict[str, Any]:
    """List commits by each user across the given (or auto-discovered) repos."""
    if usernames is None:
        usernames = list_authed_accounts() or ["@me"]
    since = _since_iso(since_days)
    since_iso = f"{since}T00:00:00Z"
    if repos is None:
        repos = _user_repos(since_iso)

    out_commits: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []

    for user in usernames:
        resolved = _resolve_me(user)
        for repo in repos:
            ok, data = _run_json(
                [
                    "api",
                    f"/repos/{repo}/commits?author={resolved}&since={since_iso}&per_page={limit_per_repo}",
                ]
            )
            if not ok:
                # Repo not accessible to this gh session, or user didn't contribute.
                # Either case: not an error from the digest's perspective.
                continue
            if not isinstance(data, list):
                continue
            for c in data:
                commit = c.get("commit") or {}
                author = commit.get("author") or {}
                out_commits.append(
                    {
                        "username": user,
                        "repo": repo,
                        "sha": (c.get("sha") or "")[:12],
                        "url": c.get("html_url", ""),
                        "message": (commit.get("message") or "").split("\n")[0],
                        "author_name": author.get("name") if isinstance(author, dict) else "",
                        "date": author.get("date") if isinstance(author, dict) else "",
                    }
                )

    out_commits.sort(key=lambda c: c.get("date") or "", reverse=True)
    return {
        "usernames": usernames,
        "since_days": since_days,
        "repos_queried": repos,
        "commits": out_commits,
        "errors": errors,
    }


def list_releases(
    repos: list[str] | None = None,
    since_days: int = 60,
    limit_per_repo: int = 5,
) -> dict[str, Any]:
    """List releases per repo within the time window."""
    since = _since_iso(since_days)
    since_iso = f"{since}T00:00:00Z"
    if repos is None:
        repos = _user_repos(since_iso, max_repos=20)

    out_rels: list[dict[str, Any]] = []
    for repo in repos:
        ok, data = _run_json(
            ["api", f"/repos/{repo}/releases?per_page={limit_per_repo}"]
        )
        if not ok or not isinstance(data, list):
            continue
        for r in data:
            published = r.get("published_at", "") or ""
            if published and published < since_iso:
                continue
            out_rels.append(
                {
                    "repo": repo,
                    "tag": r.get("tag_name", ""),
                    "name": r.get("name", ""),
                    "url": r.get("html_url", ""),
                    "published_at": published,
                    "body_preview": (r.get("body") or "")[:400],
                }
            )

    out_rels.sort(key=lambda r: r.get("published_at") or "", reverse=True)
    return {"since_days": since_days, "repos_queried": repos, "releases": out_rels}
