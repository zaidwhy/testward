# testward handoff (2026-11-13)

## State

Built in one session. Local git repository on `main`, not pushed, no remote. No users.

- Replay CLI, GitHub Action (`action.yml`), sign-off server, docs: all written.
- `python -m pytest -q` in `.venv`: 25 passed (Windows 11, Python 3.14).
- Live flow run by hand on 127.0.0.1:8791: flagged (exit 1), signed off (exit 0), re-flagged
  after a further edit (exit 1), wrong token (401).

Venv: `.venv` (created with `uv venv`), install with
`uv pip install --python .venv/Scripts/python.exe -e ".[server,dev]"`.

## Not verified

The Action on a hosted runner; Linux and macOS; the Docker image (never built); pytest, Jest or
any real runner as the replay command; the pages at phone width (headless Edge cannot go
below about 500 px); light theme.

## Next, in order

1. Kill test 1 in `docs/market.md`: replay merged agent pull requests from the AIDev dataset
   and count "needs sign-off". This decides whether anything else is worth doing.
2. Zaid: `gh repo create zaidwhy/testward --private --source . --push`, tag `v0`, then run the
   Action on a real pull request.
3. Only if the kill test passes: email verification and password reset, sign-up rate limit,
   GitHub App for one-click sign-off.

## Things that will bite

- Port 8765 on this machine belongs to the browser bridge; use another port for the server.
- The craft-guard hook reads `raise ... from` inside an f-string line as SQL. Build the message
  on its own line.
- A replay killed mid-run can leave the checkout detached at the merge base.
