"""Replay one sampled pull request. Meant for a disposable CI runner with no secrets: it
installs and runs the sampled repository's code.

Reads one JSON row (from sample.py) on stdin, appends one JSON row to the output file.
Usage: python replay_one.py <work_dir> <out.jsonl> < row.json
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
import tomllib
from pathlib import Path

PULL_REQUEST_BUDGET_SECONDS = 20 * 60
PYTEST = "python -m pytest {file} -x -q -p no:cacheprovider"
HARNESS_PYTHON = sys.executable
# Plugins that repositories name in addopts; without them pytest exits 4 before running.
PYTEST_PLUGINS = ("pytest", "pytest-asyncio", "pytest-cov", "pytest-mock", "pytest-xdist", "pytest-timeout")
REQUIREMENT_FILES = (
    "requirements.txt",
    "requirements-dev.txt",
    "requirements_dev.txt",
    "requirements-test.txt",
    "test-requirements.txt",
    "dev-requirements.txt",
)


class Budget:
    def __init__(self, seconds: float):
        self.deadline = time.monotonic() + seconds

    def left(self) -> float:
        return max(self.deadline - time.monotonic(), 1.0)


def run(argv: list[str], cwd: Path, budget: Budget, env: dict | None = None):
    try:
        done = subprocess.run(
            argv, cwd=cwd, env=env, timeout=budget.left(),
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        )
    except subprocess.TimeoutExpired:
        return None, "timed out"
    return done.returncode, done.stdout.decode("utf-8", "replace")[-3000:]


def git(repo: Path, budget: Budget, *args: str):
    return run(["git", "-C", str(repo), *args], repo.parent, budget)


def venv_environment(venv: Path) -> dict:
    """PATH is set for the test command testward launches. The harness itself calls the
    venv interpreter by full path: on Windows a bare "python" resolves against the parent's
    PATH and would install into the wrong interpreter."""
    bin_dir = venv / ("Scripts" if os.name == "nt" else "bin")
    env = dict(os.environ)
    env["VENV_PYTHON"] = str(bin_dir / ("python.exe" if os.name == "nt" else "python"))
    env["PATH"] = f"{bin_dir}{os.pathsep}{env['PATH']}"
    env["VIRTUAL_ENV"] = str(venv)
    env["UV_PROJECT_ENVIRONMENT"] = str(venv)
    env.pop("PYTHONHOME", None)
    return env


def declared_groups(repo: Path) -> tuple[list[str], list[str]]:
    """Extras and PEP 735 dependency groups the repository itself declares."""
    try:
        project = tomllib.loads((repo / "pyproject.toml").read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError, UnicodeDecodeError):
        return [], []
    extras = list(project.get("project", {}).get("optional-dependencies", {}))
    return extras[:20], list(project.get("dependency-groups", {}))[:20]


def install(repo: Path, env: dict, budget: Budget) -> str:
    """Best effort and identical for every repository; returns what worked.

    Order: the lock file's own tool, then everything pyproject declares, then requirement
    files. Nothing here is chosen per repository.
    """
    python = env["VENV_PYTHON"]
    pip = [python, "-m", "pip", "install", "-q"]
    steps = []

    def attempt(label: str, argv: list[str]) -> bool:
        code, _ = run(argv, repo, budget, env)
        steps.append(label if code == 0 else f"{label}-failed")
        return code == 0

    run([*pip, *PYTEST_PLUGINS], repo, budget, env)
    if (repo / "uv.lock").exists():
        attempt("uv-sync", [HARNESS_PYTHON, "-m", "uv", "sync", "--all-extras", "--all-groups",
                            "--inexact", "--python", python])
    elif (repo / "poetry.lock").exists() and shutil.which("poetry"):
        attempt("poetry", ["poetry", "install", "--no-interaction", "--all-extras", "--all-groups"])
    if (repo / "pyproject.toml").exists() or (repo / "setup.py").exists():
        extras, groups = declared_groups(repo)
        with_extras = f".[{','.join(extras)}]" if extras else "."
        if not attempt("editable+extras", [*pip, "-e", with_extras]):
            attempt("editable", [*pip, "-e", "."])
        for group in groups:
            attempt(f"group:{group}", [*pip, "--group", group])
    requirement_files = [name for name in REQUIREMENT_FILES if (repo / name).exists()]
    requirement_files += sorted(
        str(path.relative_to(repo)) for path in (repo / "requirements").glob("*.txt")
    )[:8]
    for name in requirement_files:
        attempt(name, [*pip, "-r", name])
    # The plugins again: a project pin may have replaced pytest and dropped them.
    run([*pip, *PYTEST_PLUGINS], repo, budget, env)
    return ",".join(steps) or "nothing-to-install"


def testward(repo: Path, base: str, env: dict, budget: Budget, json_path: Path):
    json_path.unlink(missing_ok=True)
    code, tail = run(
        [env["VENV_PYTHON"], "-m", "testward.cli", "replay", "--base", base, "--command", PYTEST,
         "--json", str(json_path)],
        repo, budget, env,
    )
    report = json.loads(json_path.read_text(encoding="utf-8")) if json_path.exists() else None
    return code, tail, report


def verdicts(report: dict | None) -> dict[str, str]:
    return {f["path"]: f["verdict"] for f in (report or {}).get("files", [])}


def floor_control(repo: Path, row: dict, env: dict, budget: Budget, work: Path) -> dict | None:
    """Append a comment to each modified test file on top of the base and replay that.
    A harness that blames a comment is broken."""
    git(repo, budget, "checkout", "-q", "--detach", row["first_parent"])
    touched = []
    for path in row["replayed_modified"]:
        target = repo / path
        if target.exists():
            with target.open("a", encoding="utf-8") as handle:
                handle.write("\n# testward floor control\n")
            touched.append(path)
    if not touched:
        return None
    git(repo, budget, "add", *touched)
    code, _ = git(
        repo, budget, "-c", "user.name=floor", "-c", "user.email=floor@example.invalid",
        "commit", "-q", "-m", "floor control",
    )
    if code != 0:
        return None
    _, _, report = testward(repo, row["first_parent"], env, budget, work / "floor.json")
    return verdicts(report)


def main(work: Path, out_path: Path) -> None:
    row = json.loads(sys.stdin.read())
    budget = Budget(PULL_REQUEST_BUDGET_SECONDS)
    started = time.monotonic()
    work.mkdir(parents=True, exist_ok=True)
    repo = work / "repo"
    shutil.rmtree(repo, ignore_errors=True)
    result = {key: row[key] for key in ("pr_id", "repository", "number", "agent", "url", "stars")}
    result.update(stage="clone", merge_sha=row["merge_sha"], first_parent=row["first_parent"])

    try:
        source = row.get("clone_url") or f"https://github.com/{row['repository']}.git"
        code, tail = run(
            ["git", "clone", "-q", "--filter=blob:none", "--no-checkout", source, str(repo)],
            work, budget,
        )
        if code == 0:
            # A merge commit may be unreachable from any branch after a force push.
            git(repo, budget, "fetch", "-q", "origin", row["merge_sha"])
            code, tail = git(repo, budget, "checkout", "-q", "--detach", row["merge_sha"])
        if code != 0:
            result["error"] = tail
            return

        # If this differs from the pull request's own file count, the merge commit's first
        # parent is not the pull request's base (a rebase merge) and the row is excluded.
        _, names = git(repo, budget, "diff", "--name-only", row["first_parent"], row["merge_sha"])
        result["diff_files"] = len((names or "").split())
        result["changed_files"] = row.get("changed_files")

        result["stage"] = "install"
        venv = work / "venv"
        shutil.rmtree(venv, ignore_errors=True)
        subprocess.run([sys.executable, "-m", "venv", str(venv)], check=True)
        env = venv_environment(venv)
        run([env["VENV_PYTHON"], "-m", "pip", "install", "-q", os.environ["TESTWARD_SOURCE"]], work, budget, env)
        result["installed"] = install(repo, env, budget)
        git(repo, budget, "checkout", "-q", "--", ".")  # installs may rewrite tracked files

        result["stage"] = "replay"
        code, tail, report = testward(repo, row["first_parent"], env, budget, work / "replay.json")
        result.update(exit_code=code, report=report)
        if report is None:
            result["error"] = tail
            return
        first = verdicts(report)
        result["verdicts"] = first
        row["replayed_modified"] = [
            f["path"] for f in report["files"] if f["status"] == "modified"
        ]

        if "needs_signoff" in first.values():
            result["stage"] = "rerun"
            result["reruns"] = [
                verdicts(testward(repo, row["first_parent"], env, budget, work / "rerun.json")[2])
                for _ in range(2)
            ]

        if first:
            result["stage"] = "floor"
            result["floor"] = floor_control(repo, row, env, budget, work)
        result["stage"] = "done"
    finally:
        result["seconds"] = round(time.monotonic() - started, 1)
        with out_path.open("a", encoding="utf-8") as out:
            out.write(json.dumps(result) + "\n")
        shutil.rmtree(repo, ignore_errors=True)
        shutil.rmtree(work / "venv", ignore_errors=True)


if __name__ == "__main__":
    main(Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve())
