# testward

A green build proves little when the same change edited the tests. testward puts the base
branch's tests back and runs them against the changed code, so a test that had to be loosened
or deleted to get green is found by running it, not by reading the diff.

```
| Test file             | Change   | Old test, new code | Old test, old code | Verdict                                             |
| tests/test_empty.py   | modified | exit 0             | not run            | held: the old test still passes                     |
| tests/test_total.py   | modified | exit 1             | exit 0             | needs sign-off: the old test fails on the new code  |
```

That table is real output from the flow in [How it was checked](#how-it-was-checked).

## The rule it enforces

For each test file a change modified, deleted or renamed:

1. Restore the file as it was at the merge base and run it against the new code.
2. If it passes, the edit was cosmetic: **held**.
3. If it fails, run it against the merge-base code as a control. Passing there means the change
   could not go green without altering this test: **needs sign-off**. Failing there means the
   test was already broken or flaky: **inconclusive**, and the change is not blamed.

A verdict is two exit codes. Nothing pattern-matches the diff and no model scores it. Tools
that flag `assert x == 6` becoming `assert x` by pattern also flag honest refactors; one of
them reports about 3.4 findings on a clean pull request ([its author's write-up][swarm]).

Changing a test is often correct. So "needs sign-off" is a question, not an accusation: a
person records why the behaviour was meant to change, and the check passes. In a 229-run study
of Claude Code ([flake-laundering][study]), a blanket "do not change tests" rule stopped 10 of
10 legitimate test repairs. Blocking test edits is the wrong gate; asking for a reason is the
right one.

## Two things that live outside the change

Anything in the repository can be rewritten by the change being checked, so:

- **The test command is read from the base branch.** `.testward.toml` at the merge base wins
  over the copy in the change and over `--command`.
- **Sign-offs are recorded on a server**, keyed to the exact old and new content of the test
  file. Edit the test again and the sign-off stops applying.

## Use it

Not published to PyPI or the Actions marketplace yet (see [Status](#status)). From a clone:

```bash
pip install .
cd /path/to/your/repo && git checkout your-branch
testward replay --base origin/main --command "pytest {file} -q"
```

Exit code 0: every changed test held or was signed off. 1: at least one needs sign-off.
2: the replay could not run; the message names the reason.

The working tree must have no uncommitted changes to tracked files, because the replay rewrites
test files in place and switches to the merge base for control runs. It puts the checkout back
when it finishes.

In GitHub Actions, see the workflow in [`docs/deploy.md`](docs/deploy.md). For sign-offs, run the
server (`docs/deploy.md`), create a project, and store its token as `TESTWARD_TOKEN`.

### Settings (`.testward.toml` on the base branch)

```toml
command = "pytest {file} -q"      # {file} is each changed test file
setup = "pip install -e ."         # optional, run after switching to the base code
timeout_seconds = 300              # per test file, 1 to 3600
max_files = 40                     # changed test files replayed per run, 1 to 200
test_globs = ["test_*.py", "*_test.py", "*.test.*", "*.spec.*"]
support_globs = ["conftest.py", "*.snap", "pytest.ini"]   # restored with the tests, not run alone
```

## What it does not catch

- A change that neuters the test runner through a file outside the globs, for example
  `addopts = "-k 'not total'"` in `pyproject.toml`. Add runner config files to `support_globs`
  so they are restored too. `pyproject.toml` cannot be restored this way without also reverting
  dependencies.
- Weak tests that a change adds. Only tests that existed at the base are replayed.
- A changed snapshot or fixture whose test file is untouched: it is restored and listed in the
  report, but no test file is run for it.
- Which case in a file failed. Replay is per file.
- Test runners that stop child processes badly: on timeout the runner is killed, its
  grandchildren may not be.

## How it was checked

- `python -m pytest -q`: 25 passed (13 replay tests on real temporary git repositories, 12
  server tests), Windows 11, Python 3.14.
- A live run: `uvicorn` server, account and project created over HTTP, `testward replay
  --server` against a fresh repository in which a commit breaks `total()` and loosens its
  assertion. Result: exit 1 with the table above, checkout clean and back on its branch;
  after a sign-off through the web form, exit 0; after one more edit to the same test, exit 1
  again; with a wrong token, HTTP 401 and exit 1.

Not checked: the GitHub Action on a hosted runner, Linux and macOS, the Docker image, any test
runner other than a plain `python {file}` script, any repository larger than the fixtures.

## Status

**Killed as a merge gate on 2026-11-13 by its own pre-registered test.** Replaying 447 merged
agent pull requests from the AIDev dataset ([`study/RESULT.md`](study/RESULT.md)): the old
tests fail on the new code in 62 of 170 conclusive replays (36.5%), and reading all 62 found
59 intended behaviour changes and 3 real regressions (two from stale branches merged over
newer work, one a dropped read-only check), after a second rater and history tracing. A gate
that stops a third of honest test-editing pull requests to surface three real problems in
sixty is not worth installing.

What survives: the replay itself is a cheap, exact answer to "did this change alter behaviour
an existing test pinned down", useful as a note to a reviewer (`testward replay` exits 1 and
prints the table). The sign-off server is kept as built and is not being developed.

No users. [`docs/market.md`](docs/market.md) holds the earlier evidence, the rivals and the
pricing reasoning.

Other documents: [`docs/architecture.md`](docs/architecture.md),
[`docs/security.md`](docs/security.md), [`docs/deploy.md`](docs/deploy.md).

MIT licensed.

[swarm]: https://dev.to/moonrunnerkc/catching-the-shortcuts-ai-coding-agents-take-to-look-done-45mm
[study]: https://github.com/zaidwhy/flake-laundering
