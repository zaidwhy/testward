# testward handoff (2026-11-13)

## State

Public at github.com/zaidwhy/testward. **Killed as a product** by the pre-registered
prevalence study in `study/` (RESULT.md): 62 of 170 conclusive replays need sign-off, 59
intended, 3 unclear, 0 laundered.

- Replay CLI, GitHub Action, sign-off server, docs: built, 25 tests pass, CI green on push.
- Study: PREREG, DEVIATIONS, RESULT, raw rows and labels in `study/results/`.

Venv: `.venv` (`uv venv`), install with
`uv pip install --python .venv/Scripts/python.exe -e ".[server,dev]"`.

## Open, all optional

1. The study is a follow-up to flake-laundering and could be written up or deposited. Not
   deposited; that needs Zaid's go-ahead. A second rater on `results/labels-*.jsonl` and a human
   comparison group would be the first things a reviewer asks for.
2. The three unclear pull requests were not investigated.
3. Not verified: the Action on someone else's repository, the Docker image, phone-width pages.

## Things that will bite

- Never run `study/replay_one.py` on sampled rows locally: it executes the sampled
  repository's code. `selftest.sh` is the only local entry point.
- Port 8765 on this machine belongs to the browser bridge.
- The craft-guard hook reads `raise ... from` inside an f-string line as SQL.
- A background `gh run` watcher and a foreground download of the same run race on the same
  folder; use one.
