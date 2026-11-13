# How testward is put together

Two programs. The replay runs where the code is (a laptop or a CI job) and never needs the
server. The server only remembers reports and human sign-offs.

```
CI job / laptop                                  server (one container)
-----------------                                ----------------------
testward replay                                  FastAPI + SQLite file
  git: merge base, changed test files            /api/v1/reports   project token
  restore base tests, run, control run   --->    /app/...          session cookie + CSRF
  exit 0 / 1 / 2                         <---    signed-off fingerprints
```

## Replay (`src/testward/`)

| File | Job |
|---|---|
| `git.py` | Git plumbing as argument lists: merge base, name-status diff with rename detection, blobs, checkouts |
| `config.py` | `.testward.toml` parsing with bounds; glob matching for test and support files |
| `replay.py` | The procedure: overlay base tests on head, run each, control-run failures at the merge base, restore the checkout |
| `report.py` | The JSON sent to the server and the Markdown shown to a reviewer |
| `cli.py` | Arguments, exit codes, the upload and sign-off lookup |

The replay has no third-party dependencies; it needs Python 3.11+ and `git`.

Decisions worth knowing:

- **In place, not in a worktree.** Tests run in the existing checkout so installed
  dependencies, editable installs and `node_modules` keep working. The cost is that the tree
  must be clean and a process killed mid-run can leave the checkout at the merge base;
  `git checkout <branch>` recovers it.
- **Per file.** Any test runner works because the only contract is "command plus file path,
  exit code". Per-case replay would need a parser per framework.
- **The control run** is what keeps a flaky or already-broken test from being blamed on the
  change.
- **Fingerprint** = SHA-256 of path, base blob id and head blob id. It names one specific test
  edit, so a sign-off cannot outlive a further edit.

## Server (`src/testward/server/`)

| File | Job |
|---|---|
| `app.py` | Routes, request limits, report validation, security headers |
| `ledger.py` | SQLite: accounts, sessions, projects, reports, sign-offs; tables created once at startup with a `schema_version` row |
| `credentials.py` | scrypt password hashes, random tokens, token digests |
| `templates/` | Server-rendered pages, no JavaScript |

Data lifetime: a report is kept until a project has 500 newer ones. Sign-offs are kept until
revoked. Sessions last 14 days.

Limits enforced: report body 512 KB, 200 files per report, 4,000 characters of log per file,
120 reports per project per hour, form bodies 16 KB, 50 projects per account, sign-off reason
10 to 500 characters, 5 failed logins per email per 15 minutes.

SQLite means one server instance. That is enough until write volume says otherwise; the
ledger class is the only code that would change for Postgres.

## Not built

Billing, team accounts (a project has one owner), email verification and password reset, a
GitHub App, comments on the pull request (the Action writes the job summary instead).
