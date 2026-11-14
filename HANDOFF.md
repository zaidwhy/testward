# testward handoff (2026-11-14)

## State

Public at github.com/zaidwhy/testward. **Killed as a product** by the pre-registered
prevalence study in `study/` (RESULT.md): 62 of 170 conclusive replays need sign-off, 61
intended, 1 real regression (sshpilot#418, a fix lost in a stale-branch merge).

- Replay CLI, GitHub Action, sign-off server, docs: built, 25 tests pass, CI green on push.
- Study: PREREG, DEVIATIONS, RESULT, raw rows and labels in `study/results/`.

Venv: `.venv` (`uv venv`), install with
`uv pip install --python .venv/Scripts/python.exe -e ".[server,dev]"`.

## Done 2026-11-14

- Zaid labelled all 62 (`study/results/labels-zaid.jsonl`); agreement 54/62, kappa 0.18
  (`results/agreement-zaid.txt`). The 8 disagreements were traced read-only through each
  repository: agentflow#1 and robotocore#97 are real regressions, so the study now reports 3 of
  62 real (59 intended). Kill unchanged (H2 fails at 95.2% intended). RESULT.md and README
  updated.
- Deposited on Zenodo: concept DOI 10.5281/zenodo.24219408, v0.1.0 = 24219409 (GitHub release
  v0.1.0; Zenodo GitHub integration is on for this repo, so a new release makes a new version).

## Next

Nothing required. Optional: a new study on stale-branch merges (2 of the 3 real cases were a
stale agent branch merged over newer work, which can be detected without replaying tests).

## Open, all optional

1. The study is a follow-up to flake-laundering and could be written up or deposited. Not
   deposited; that needs Zaid's go-ahead. A second rater on `results/labels-*.jsonl` and a human
   comparison group would be the first things a reviewer asks for.
2. The three first-pass unclear pull requests were traced; the 59 first-pass "intended" labels were not.
3. Not verified: the Action on someone else's repository, the Docker image, phone-width pages.

## Things that will bite

- Never run `study/replay_one.py` on sampled rows locally: it executes the sampled
  repository's code. `selftest.sh` is the only local entry point.
- Port 8765 on this machine belongs to the browser bridge.
- The craft-guard hook reads `raise ... from` inside an f-string line as SQL.
- A background `gh run` watcher and a foreground download of the same run race on the same
  folder; use one.
