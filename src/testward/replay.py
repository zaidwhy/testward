"""Base-test replay.

For every test file a change modified, deleted or renamed, put the merge-base version back
and run it against the changed code. A test that passes was edited cosmetically. A test
that fails is then run against the merge-base code as a control: passing there means the
change needed that test altered to go green, failing there means the test was already
broken or flaky and nothing can be concluded.
"""

from __future__ import annotations

import hashlib
import logging
import os
import shlex
import shutil
import subprocess
import time
from dataclasses import dataclass, field, replace
from pathlib import Path

from . import git
from .config import CONFIG_PATH, ConfigError, ReplayConfig, parse

log = logging.getLogger("testward")

SCHEMA_VERSION = 1
LOG_TAIL_CHARS = 4000

HELD = "held"
NEEDS_SIGNOFF = "needs_signoff"
INCONCLUSIVE = "inconclusive"


class ReplayError(RuntimeError):
    pass


@dataclass
class Run:
    exit_code: int | None  # None when the run hit the timeout
    seconds: float
    log_tail: str


@dataclass
class FileResult:
    path: str
    status: str
    new_path: str | None
    base_blob: str
    head_blob: str | None
    verdict: str = INCONCLUSIVE
    replayed: bool = False
    head_exit: int | None = None  # None after a replay means it timed out
    control_ran: bool = False
    control_exit: int | None = None
    seconds: float = 0.0
    log_tail: str = ""
    note: str = ""
    waived: bool = False

    @property
    def fingerprint(self) -> str:
        """Identity of one test edit. Any further edit to the file changes it, so a
        sign-off never carries over to a version of the test nobody looked at."""
        parts = "\0".join([self.path, self.base_blob, self.head_blob or "deleted"])
        return hashlib.sha256(parts.encode()).hexdigest()[:32]


@dataclass
class Report:
    base: str
    head: str
    merge_base: str
    command: str | None
    config_source: str
    files: list[FileResult] = field(default_factory=list)
    support_changed: list[str] = field(default_factory=list)

    def unresolved(self, strict: bool = False) -> list[FileResult]:
        failing = {NEEDS_SIGNOFF, INCONCLUSIVE} if strict else {NEEDS_SIGNOFF}
        return [f for f in self.files if f.verdict in failing and not f.waived]


def load_config(repo: Path, merge_base: str, cli_command: str | None) -> ReplayConfig:
    text = git.file_at(repo, merge_base, CONFIG_PATH)
    if text is None:
        return ReplayConfig(command=cli_command, source="command line")
    config = parse(text.decode("utf-8", "replace"), source="merge base")
    if config.command is None and cli_command:
        return replace(config, command=cli_command)
    return config


def replay(repo: Path, base_rev: str, cli_command: str | None = None) -> Report:
    repo = repo.resolve()
    head = git.resolve(repo, "HEAD")
    merge_base = git.merge_base(repo, base_rev, head)
    config = load_config(repo, merge_base, cli_command)
    report = Report(
        base=base_rev,
        head=head,
        merge_base=merge_base,
        command=config.command,
        config_source=config.source,
    )

    changes = git.changed_since(repo, merge_base, head)
    tests = [c for c in changes if config.is_test(c.path)]
    support = [c for c in changes if config.is_support(c.path)]
    report.support_changed = [c.path for c in support]
    if not tests:
        return report

    if config.command is None:
        raise ConfigError(
            f"no test command: add `command` to {CONFIG_PATH} on the base branch or pass --command"
        )
    argv = _argv(config.command)

    dirty = git.tracked_changes(repo)
    if dirty:
        shown = ", ".join(dirty[:5])
        raise ReplayError(
            f"working tree has uncommitted changes to tracked files ({shown}); "
            "commit them first, the replay rewrites test files in place"
        )

    report.files = [
        FileResult(
            path=c.path,
            status=c.status,
            new_path=c.new_path,
            base_blob=git.blob_id(repo, merge_base, c.path) or "",
            head_blob=git.blob_id(repo, head, c.new_path or c.path),
        )
        for c in tests
    ]
    replayed = report.files[: config.max_files]
    for skipped in report.files[config.max_files :]:
        skipped.note = f"not replayed: more than {config.max_files} changed test files (max_files)"

    with _BaseTestsOverHead(repo, merge_base, head, tests + support):
        for result in replayed:
            run = _run(repo, argv, result.path, config.timeout_seconds)
            result.replayed = True
            result.head_exit = run.exit_code
            result.seconds = run.seconds
            result.log_tail = run.log_tail
            if run.exit_code == 0:
                result.verdict = HELD
            elif run.exit_code is None:
                result.note = f"timed out after {config.timeout_seconds}s against the changed code"

    failing = [r for r in replayed if r.head_exit not in (0, None)]
    if failing:
        _control_runs(repo, merge_base, config, argv, failing)
    return report


def _control_runs(
    repo: Path, merge_base: str, config: ReplayConfig, argv: list[str], failing: list[FileResult]
) -> None:
    original = git.current_ref(repo)
    git.checkout_detached(repo, merge_base)
    try:
        if config.setup and not _setup(repo, config):
            for result in failing:
                result.note = "setup command failed at the merge base, so there is no control run"
            return
        for result in failing:
            control = _run(repo, argv, result.path, config.timeout_seconds)
            result.control_ran = True
            result.control_exit = control.exit_code
            result.seconds += control.seconds
            if control.exit_code == 0:
                result.verdict = NEEDS_SIGNOFF
            else:
                result.note = "also fails against the merge-base code: broken or flaky before this change"
    finally:
        git.checkout_ref(repo, original)
        if config.setup:
            _setup(repo, config)


def _setup(repo: Path, config: ReplayConfig) -> bool:
    run = _run(repo, _argv(config.setup or ""), None, config.timeout_seconds)
    if run.exit_code != 0:
        log.warning("setup command exited %s: %s", run.exit_code, run.log_tail[-400:])
    return run.exit_code == 0


class _BaseTestsOverHead:
    """Rewrite the changed test files to their merge-base content, then put the head back."""

    def __init__(self, repo: Path, merge_base: str, head: str, changes: list[git.ChangedPath]):
        self.repo, self.merge_base, self.head, self.changes = repo, merge_base, head, changes
        self.created_dirs: list[Path] = []

    def __enter__(self) -> None:
        for change in self.changes:
            if change.status != "modified" and (self.repo / change.path).exists():
                raise ReplayError(
                    f"{change.path} was {change.status} by the change but a file is in the way on disk"
                )
        try:
            for change in self.changes:
                content = git.file_at(self.repo, self.merge_base, change.path)
                if content is None:
                    continue
                target = self.repo / change.path
                self._make_parents(target.parent)
                target.write_bytes(content)
                if change.new_path:
                    (self.repo / change.new_path).unlink(missing_ok=True)
        except BaseException:
            self.__exit__(None, None, None)
            raise

    def __exit__(self, *exc_info: object) -> None:
        restore: list[str] = []
        for change in self.changes:
            if change.status == "modified":
                restore.append(change.path)
                continue
            (self.repo / change.path).unlink(missing_ok=True)
            if change.new_path:
                restore.append(change.new_path)
        git.checkout_paths(self.repo, self.head, restore)
        for directory in reversed(self.created_dirs):
            if any(directory.iterdir()):
                log.warning("left %s in place: the test run wrote files into it", directory)
            else:
                directory.rmdir()

    def _make_parents(self, directory: Path) -> None:
        missing = []
        while not directory.exists():
            missing.append(directory)
            directory = directory.parent
        for d in reversed(missing):
            d.mkdir()
            self.created_dirs.append(d)


def _argv(command: str) -> list[str]:
    argv = shlex.split(command)
    if not argv:
        raise ConfigError("test command is empty")
    program = shutil.which(argv[0])
    if program is None:
        raise ReplayError(f"test command not found on PATH: {argv[0]}")
    return [program, *argv[1:]]


def _run(repo: Path, argv: list[str], test_file: str | None, timeout: int) -> Run:
    if test_file is None:
        command = argv
    elif any("{file}" in part for part in argv):
        command = [part.replace("{file}", test_file) for part in argv]
    else:
        command = [*argv, test_file]
    started = time.monotonic()
    try:
        proc = subprocess.run(
            command,
            cwd=repo,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
            env={**os.environ, "TESTWARD_REPLAY": "1"},
        )
    except subprocess.TimeoutExpired as expired:
        output = (expired.stdout or b"").decode("utf-8", "replace")
        return Run(None, time.monotonic() - started, output[-LOG_TAIL_CHARS:])
    output = proc.stdout.decode("utf-8", "replace")
    return Run(proc.returncode, time.monotonic() - started, output[-LOG_TAIL_CHARS:])
