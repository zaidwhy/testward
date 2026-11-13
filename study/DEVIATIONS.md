# Deviations from PREREG.md

Each entry is dated and was written when the change was made.

## 2026-11-13, after pilot 1 (run 43414787332, 30 pull requests from the head of sample A)

Pilot 1 result: 30 rows; 4 had no existing test changed at replay; of the other 26, 8 were
conclusive (4 held, 4 needs sign-off) and 18 inconclusive. Floor control: 0 of 25 flagged.
Conclusive yield 31%, under the 40% bar. 15 of the 18 inconclusive rows were a missing
dependency or a pytest plugin named in the repository's own options.

Changes to the environment setup only. The verdict logic, the test command, the sample and
the kill rules are unchanged.

1. Install from the repository's lock file when there is one (`uv sync --all-extras
   --all-groups`, or `poetry install --all-extras --all-groups`).
2. Install every extra and every PEP 735 dependency group that `pyproject.toml` declares,
   in place of guessing four extra names.
3. Also install `requirements/*.txt` (first 8 files).
4. Pre-install five common pytest plugins (asyncio, cov, mock, xdist, timeout).
5. Python 3.12 in place of 3.11; `libegl1` and `libgl1` on the runner.
6. Budget per pull request 20 minutes in place of 15.

The pilot rows were seen before these changes, including which four were flagged. They stay
in sample A and are re-run under the new setup; the result table reports sample A with and
without those 30 rows.

## 2026-11-13, after pilot 2 (run 43415455865, the same 30 pull requests)

Pilot 2 result: 12 of 26 conclusive (46%; 7 held, 5 needs sign-off), floor control 0 of 24.
Two repositories that were conclusive in pilot 1 became inconclusive because a pre-installed
pytest plugin they do not use broke their suite.

7. A pytest plugin is installed only when the repository's own configuration files name it.
8. `pip` is upgraded in the fresh virtualenv so `--group` works.

No further setup changes are made after this point. Sample A runs once with this setup.

## 2026-11-13, sampling

Three pull requests were drawn into both samples. They are counted in sample A and removed
from sample B at analysis, leaving 147.

## 2026-11-13, after the first write-up

The plan had one labelling pass. The three pull requests it left "unclear" were afterwards
traced through commit and file history on GitHub. Two became "intended" and one became a real
regression that meets the "laundered" rubric. The first-pass labels are kept beside the
revised ones in `results/labels-*.jsonl`, and RESULT.md reports both. The 59 first-pass
"intended" labels were not re-examined.
