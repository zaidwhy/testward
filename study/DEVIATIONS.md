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
