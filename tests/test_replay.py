"""Each test builds a small real git repository and replays it. The test command is
`python {file}`, so a "test" is a script that exits non-zero when its assertion fails."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from testward import cli
from testward.config import ConfigError
from testward.replay import HELD, INCONCLUSIVE, NEEDS_SIGNOFF, ReplayError, replay
from testward.report import to_markdown

COMMAND = f'"{Path(sys.executable).as_posix()}" {{file}}'

APP_OK = "def total(prices):\n    return sum(prices)\n"
APP_BROKEN = "def total(prices):\n    return sum(prices[1:])\n"
TEST_STRICT = (
    "import sys; sys.path.insert(0, '.')\n"
    "from app import total\n"
    "assert total([1, 2, 3]) == 6\n"
)
TEST_WEAKENED = (
    "import sys; sys.path.insert(0, '.')\n"
    "from app import total\n"
    "assert total([1, 2, 3])\n"
)
TEST_REWORDED = TEST_STRICT + "# checks the sum of all prices\n"


def sh(repo: Path, *args: str) -> str:
    done = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=True)
    return done.stdout.strip()


def commit(repo: Path, message: str, files: dict[str, str | None]) -> None:
    for name, content in files.items():
        target = repo / name
        if content is None:
            sh(repo, "rm", "-q", name)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8", newline="\n")
        sh(repo, "add", name)
    sh(repo, "commit", "-q", "-m", message)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    sh(tmp_path, "init", "-q", "-b", "main")
    sh(tmp_path, "config", "user.email", "dev@example.test")
    sh(tmp_path, "config", "user.name", "dev")
    sh(tmp_path, "config", "core.autocrlf", "false")
    commit(tmp_path, "base", {"app.py": APP_OK, "tests/test_total.py": TEST_STRICT})
    sh(tmp_path, "checkout", "-q", "-b", "change")
    return tmp_path


def only(report):
    assert len(report.files) == 1
    return report.files[0]


def test_weakened_assertion_that_hides_a_bug_needs_signoff(repo):
    commit(repo, "fix", {"app.py": APP_BROKEN, "tests/test_total.py": TEST_WEAKENED})
    result = only(replay(repo, "main", COMMAND))
    assert result.verdict == NEEDS_SIGNOFF
    assert result.head_exit != 0 and result.control_exit == 0
    assert "AssertionError" in result.log_tail


def test_cosmetic_test_edit_is_held(repo):
    commit(repo, "tidy", {"tests/test_total.py": TEST_REWORDED})
    result = only(replay(repo, "main", COMMAND))
    assert result.verdict == HELD
    assert result.control_ran is False


def test_deleted_test_is_restored_and_replayed(repo):
    commit(repo, "drop", {"app.py": APP_BROKEN, "tests/test_total.py": None})
    result = only(replay(repo, "main", COMMAND))
    assert (result.status, result.verdict) == ("deleted", NEEDS_SIGNOFF)
    assert not (repo / "tests").exists(), "the restored test and its directory are removed again"


def test_renamed_and_weakened_test_is_replayed_at_its_old_path(repo):
    sh(repo, "mv", "tests/test_total.py", "tests/test_sum.py")
    (repo / "tests/test_sum.py").write_text(TEST_STRICT.replace("== 6", "> 0"), newline="\n")
    (repo / "app.py").write_text(APP_BROKEN, newline="\n")
    sh(repo, "commit", "-q", "-am", "rename")
    result = only(replay(repo, "main", COMMAND))
    assert (result.status, result.new_path) == ("renamed", "tests/test_sum.py")
    assert result.verdict == NEEDS_SIGNOFF
    assert (repo / "tests/test_sum.py").exists() and not (repo / "tests/test_total.py").exists()


def test_test_already_failing_at_the_base_is_inconclusive(tmp_path):
    sh(tmp_path, "init", "-q", "-b", "main")
    sh(tmp_path, "config", "user.email", "dev@example.test")
    sh(tmp_path, "config", "user.name", "dev")
    commit(tmp_path, "base", {"app.py": APP_BROKEN, "tests/test_total.py": TEST_STRICT})
    sh(tmp_path, "checkout", "-q", "-b", "change")
    commit(tmp_path, "loosen", {"tests/test_total.py": TEST_WEAKENED})
    report = replay(tmp_path, "main", COMMAND)
    result = only(report)
    assert result.verdict == INCONCLUSIVE and "merge-base code" in result.note
    assert report.unresolved() == [] and report.unresolved(strict=True) == [result]


def test_new_tests_and_code_only_changes_are_not_replayed(repo):
    commit(repo, "more", {"app.py": APP_OK + "\n", "tests/test_extra.py": TEST_STRICT})
    report = replay(repo, "main", COMMAND)
    assert report.files == []
    assert "no existing test" in to_markdown(report)


def test_checkout_is_back_on_the_branch_and_clean_after_a_replay(repo):
    commit(repo, "fix", {"app.py": APP_BROKEN, "tests/test_total.py": TEST_WEAKENED})
    head = sh(repo, "rev-parse", "HEAD")
    replay(repo, "main", COMMAND)
    assert sh(repo, "rev-parse", "--abbrev-ref", "HEAD") == "change"
    assert sh(repo, "rev-parse", "HEAD") == head
    assert sh(repo, "status", "--porcelain", "--untracked-files=no") == ""
    assert (repo / "tests/test_total.py").read_text() == TEST_WEAKENED


def test_uncommitted_tracked_changes_are_refused(repo):
    commit(repo, "fix", {"tests/test_total.py": TEST_WEAKENED})
    (repo / "app.py").write_text(APP_BROKEN)
    with pytest.raises(ReplayError, match="uncommitted changes.*app.py"):
        replay(repo, "main", COMMAND)
    assert (repo / "app.py").read_text() == APP_BROKEN


def test_command_comes_from_the_base_branch_not_from_the_change(tmp_path):
    sh(tmp_path, "init", "-q", "-b", "main")
    sh(tmp_path, "config", "user.email", "dev@example.test")
    sh(tmp_path, "config", "user.name", "dev")
    base_config = f"command = '{COMMAND}'\n"
    commit(
        tmp_path,
        "base",
        {"app.py": APP_OK, "tests/test_total.py": TEST_STRICT, ".testward.toml": base_config},
    )
    sh(tmp_path, "checkout", "-q", "-b", "change")
    always_green = f"command = '\"{Path(sys.executable).as_posix()}\" -c pass'\n"
    commit(
        tmp_path,
        "fix",
        {"app.py": APP_BROKEN, "tests/test_total.py": TEST_WEAKENED, ".testward.toml": always_green},
    )
    report = replay(tmp_path, "main", cli_command="ignored-because-base-has-a-config")
    assert report.config_source == "merge base"
    assert only(report).verdict == NEEDS_SIGNOFF


def test_timeout_is_inconclusive_and_named(repo):
    slow = "import time\ntime.sleep(30)\n"
    config = f"command = '{COMMAND}'\ntimeout_seconds = 1\n"
    commit(repo, "slow base", {"tests/test_slow.py": slow, ".testward.toml": config})
    sh(repo, "branch", "-f", "main", "change")
    commit(repo, "edit", {"tests/test_slow.py": slow + "# edited\n"})
    result = only(replay(repo, "main"))
    assert result.verdict == INCONCLUSIVE and "timed out after 1s" in result.note


def test_missing_command_names_both_ways_to_set_it(repo):
    commit(repo, "fix", {"tests/test_total.py": TEST_WEAKENED})
    with pytest.raises(ConfigError, match=r"\.testward\.toml.*--command"):
        replay(repo, "main")


def test_changed_snapshot_is_restored_with_the_tests_and_reported(repo):
    commit(repo, "snap base", {"tests/__snapshots__/total.snap": "6\n"})
    sh(repo, "branch", "-f", "main", "change")
    commit(repo, "regen", {"tests/__snapshots__/total.snap": "5\n"})
    report = replay(repo, "main", COMMAND)
    assert report.files == [] and report.support_changed == ["tests/__snapshots__/total.snap"]


def test_cli_exit_codes_and_markdown(repo, tmp_path_factory, capsys):
    out = tmp_path_factory.mktemp("out")
    commit(repo, "fix", {"app.py": APP_BROKEN, "tests/test_total.py": TEST_WEAKENED})
    code = cli.main(
        ["replay", "--base", "main", "--repo", str(repo), "--command", COMMAND,
         "--json", str(out / "r.json"), "--markdown", str(out / "r.md")]
    )
    assert code == cli.EXIT_NEEDS_SIGNOFF
    printed = capsys.readouterr().out
    assert "1 need sign-off" in printed and "`tests/test_total.py`" in printed
    assert '"verdict": "needs_signoff"' in (out / "r.json").read_text()

    assert cli.main(["replay", "--base", "no-such-branch", "--repo", str(repo)]) == cli.EXIT_ERROR
