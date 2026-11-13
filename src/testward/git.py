"""Git plumbing for the replay. Every call is an argument list; nothing goes through a shell."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path


class GitError(RuntimeError):
    pass


def git(repo: Path, *args: str) -> str:
    return git_bytes(repo, *args).decode("utf-8", "replace")


def git_bytes(repo: Path, *args: str) -> bytes:
    proc = subprocess.run(["git", "-C", str(repo), *args], capture_output=True)
    if proc.returncode != 0:
        detail = proc.stderr.decode("utf-8", "replace").strip()
        raise GitError(f"git {' '.join(args)} failed: {detail}")
    return proc.stdout


@dataclass(frozen=True)
class ChangedPath:
    status: str  # "modified", "deleted" or "renamed"
    path: str  # where the file lived at the merge base
    new_path: str | None  # set only for renames


def resolve(repo: Path, rev: str) -> str:
    return git(repo, "rev-parse", "--verify", f"{rev}^{{commit}}").strip()


def merge_base(repo: Path, base: str, head: str) -> str:
    return git(repo, "merge-base", base, head).strip()


def current_ref(repo: Path) -> str:
    """Branch name when on a branch, else the commit, so the checkout can be put back exactly."""
    proc = subprocess.run(
        ["git", "-C", str(repo), "symbolic-ref", "--quiet", "--short", "HEAD"],
        capture_output=True,
    )
    if proc.returncode == 0:
        return proc.stdout.decode().strip()
    return resolve(repo, "HEAD")


def tracked_changes(repo: Path) -> list[str]:
    out = git(repo, "status", "--porcelain", "--untracked-files=no")
    return [line[3:] for line in out.splitlines() if line.strip()]


def changed_since(repo: Path, base_commit: str, head_commit: str) -> list[ChangedPath]:
    """Paths that existed at the base and were modified, deleted or renamed by the head.

    Added files are left out on purpose: a new test cannot weaken an old one.
    """
    raw = git(repo, "diff", "--name-status", "-M", "-z", base_commit, head_commit)
    fields = [f for f in raw.split("\0") if f]
    changes: list[ChangedPath] = []
    i = 0
    while i < len(fields):
        code = fields[i]
        if code.startswith("R"):
            changes.append(ChangedPath("renamed", fields[i + 1], fields[i + 2]))
            i += 3
            continue
        if code.startswith("C"):
            i += 3
            continue
        if code == "M":
            changes.append(ChangedPath("modified", fields[i + 1], None))
        elif code == "D":
            changes.append(ChangedPath("deleted", fields[i + 1], None))
        i += 2
    return changes


def blob_id(repo: Path, commit: str, path: str) -> str | None:
    proc = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "--verify", "--quiet", f"{commit}:{path}"],
        capture_output=True,
    )
    return proc.stdout.decode().strip() if proc.returncode == 0 else None


def file_at(repo: Path, commit: str, path: str) -> bytes | None:
    if blob_id(repo, commit, path) is None:
        return None
    return git_bytes(repo, "show", f"{commit}:{path}")


def checkout_paths(repo: Path, commit: str, paths: list[str]) -> None:
    if paths:
        git(repo, "checkout", "--quiet", commit, "--", *paths)


def checkout_detached(repo: Path, commit: str) -> None:
    git(repo, "checkout", "--quiet", "--detach", commit)


def checkout_ref(repo: Path, ref: str) -> None:
    git(repo, "checkout", "--quiet", ref)
