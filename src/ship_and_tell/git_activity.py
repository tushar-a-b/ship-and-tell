"""Read git activity (log + shortstat) for a repo over a time range.

Used alongside read_session: the conversation tells you what was *discussed*;
git tells you what was *actually shipped*. The tweet-worthy stuff is usually
in the intersection.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any

_STAT_FILES = re.compile(r"(\d+) files? changed")
_STAT_INS = re.compile(r"(\d+) insertions?")
_STAT_DEL = re.compile(r"(\d+) deletions?")


def _run_git(args: list[str], cwd: Path, timeout: float = 10.0) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(cwd), *args],
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _is_git_repo(repo: Path) -> bool:
    try:
        result = _run_git(["rev-parse", "--is-inside-work-tree"], repo, timeout=5)
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False
    return result.returncode == 0 and result.stdout.strip() == "true"


def _current_branch(repo: Path) -> str | None:
    try:
        result = _run_git(["rev-parse", "--abbrev-ref", "HEAD"], repo, timeout=5)
    except subprocess.TimeoutExpired:
        return None
    if result.returncode != 0:
        return None
    branch = result.stdout.strip()
    return branch or None


def read_activity(
    repo_path: str,
    since_days: int | None = 7,
    since: str | None = None,
    until: str | None = None,
    max_commits: int = 50,
    author: str | None = None,
) -> dict[str, Any]:
    """Return commit log + shortstat for `repo_path` over the given window.

    Either `since_days` (e.g. 7) or `since`/`until` (git's relative or ISO
    forms, e.g. "2026-06-01" or "3 days ago") can be used. If both are given,
    `since`/`until` win.
    """
    repo = Path(repo_path).expanduser()
    out: dict[str, Any] = {"repo": str(repo)}

    if not repo.exists():
        out["error"] = f"Path does not exist: {repo}"
        return out
    if not _is_git_repo(repo):
        out["error"] = f"Not a git repo: {repo}"
        return out

    effective_since = since
    if effective_since is None and since_days is not None:
        effective_since = f"{since_days} days ago"

    args = [
        "log",
        f"-{max_commits}",
        "--pretty=format:%H%x09%an%x09%aI%x09%s",
        "--shortstat",
        "--no-merges",
    ]
    if effective_since:
        args += ["--since", effective_since]
    if until:
        args += ["--until", until]
    if author:
        args += ["--author", author]

    try:
        result = _run_git(args, repo)
    except subprocess.TimeoutExpired:
        out["error"] = "git log timed out"
        return out

    if result.returncode != 0:
        out["error"] = result.stderr.strip() or "git log failed"
        return out

    commits: list[dict[str, Any]] = []
    pending: dict[str, Any] | None = None
    for raw in result.stdout.splitlines():
        line = raw.strip()
        if not line:
            continue
        if "\t" in line and line.count("\t") >= 3:
            if pending is not None:
                commits.append(pending)
            sha, author_name, date, subject = line.split("\t", 3)
            pending = {
                "sha": sha[:12],
                "author": author_name,
                "date": date,
                "subject": subject,
                "files_changed": 0,
                "insertions": 0,
                "deletions": 0,
            }
        elif pending is not None:
            mf = _STAT_FILES.search(line)
            mi = _STAT_INS.search(line)
            md = _STAT_DEL.search(line)
            if mf:
                pending["files_changed"] = int(mf.group(1))
            if mi:
                pending["insertions"] = int(mi.group(1))
            if md:
                pending["deletions"] = int(md.group(1))
    if pending is not None:
        commits.append(pending)

    files_by_count: dict[str, int] = {}
    if commits:
        try:
            name_only = _run_git(
                [
                    "log",
                    f"-{max_commits}",
                    "--pretty=format:",
                    "--name-only",
                    "--no-merges",
                ]
                + (["--since", effective_since] if effective_since else [])
                + (["--until", until] if until else [])
                + (["--author", author] if author else []),
                repo,
            )
            for fname in name_only.stdout.splitlines():
                fname = fname.strip()
                if not fname:
                    continue
                files_by_count[fname] = files_by_count.get(fname, 0) + 1
        except subprocess.TimeoutExpired:
            pass

    top_files = sorted(files_by_count.items(), key=lambda kv: -kv[1])[:15]

    out.update(
        {
            "branch": _current_branch(repo),
            "since": effective_since,
            "until": until,
            "commit_count": len(commits),
            "commits": commits,
            "top_files": [{"path": p, "touched_in_commits": n} for p, n in top_files],
        }
    )
    return out
