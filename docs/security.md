# Security review

Reviewed 2026-11-13 by the author of the code, by reading it and by the tests named below. No
independent review and no penetration test has been done.

## What an attacker wants

1. To get a weakened test past the gate (the attacker is the author of the change, possibly an
   agent).
2. To read or forge another team's reports and sign-offs.
3. To take over an account or exhaust the server.

## Getting past the gate

| Attack | Status |
|---|---|
| Change the test command to something that always passes | Closed: the command is read from the merge base (`test_command_comes_from_the_base_branch_not_from_the_change`) |
| Commit a sign-off alongside the weakened test | Closed: sign-offs exist only on the server, made by a signed-in person |
| Get one sign-off, then weaken the test further | Closed: the fingerprint changes with the file content (checked in the live run and `test_signoff_flow_from_report_to_passing_rerun`) |
| Sign off an edit before any report flags it | Closed: the server refuses fingerprints no stored report flagged |
| Neuter the runner through a config file outside the globs (`pyproject.toml` `addopts`, a Jest config) | **Open.** Partly mitigated by adding runner config files to `support_globs`. A change to the workflow file itself is also outside testward's reach; protect it with branch rules or CODEOWNERS |
| Make the old test pass by special-casing `TESTWARD_REPLAY` in the code | **Open.** The variable is set for runners that need it; code that reads it is visible in the diff |
| Remove the testward job from the workflow | Outside scope: make the check required in branch protection |

## The Action runs untrusted code

The replay executes the pull request's code, as any test job does. Use the `pull_request`
trigger with `permissions: contents: read`. Never `pull_request_target`. Fork pull requests get
no secrets, so they run without sign-offs and fail closed. Action inputs are passed as
environment variables, not interpolated into the script. Every subprocess is an argument list;
nothing goes through a shell.

## Server

| Area | What is done | Gap |
|---|---|---|
| Passwords | scrypt (n=2^14, r=8, p=1), 16-byte salt, constant-time compare, 10 to 200 characters | No breached-password check |
| Sessions | 256-bit random token, only its SHA-256 stored, HttpOnly, SameSite=Lax, Secure when the base URL is https, 14 days | No "sign out everywhere" |
| CSRF | Per-session token on every state-changing form, plus an Origin check on all browser POSTs | The Origin check depends on `TESTWARD_BASE_URL` being set correctly |
| Login guessing | 5 failures per email per 15 minutes | By email, so someone can lock out a known address for 15 minutes. No per-IP limit, because behind a proxy the IP is not trustworthy without configuration |
| Project tokens | 256-bit, shown once, only the digest stored, replaceable | One token per project, no scopes |
| Isolation | Every project query filters by the owning account (`test_one_account_cannot_see_or_sign_another_accounts_project`) | Single owner per project |
| Injection | All SQL is parameterized. Templates autoescape. `change_url` must be http or https. CSP `default-src 'none'`, no scripts served | |
| Request size | Limits listed in `architecture.md`, enforced while reading the body | |
| Accounts | Email format check only | **No email verification and no password reset.** Anyone can register any address. No sign-up rate limit; set `TESTWARD_ALLOW_SIGNUP=0` on a private server |
| Storage abuse | 500 reports per project, 50 projects per account | Worst case about 12.8 GB per account; no per-account quota |

## Data sent to the server

Commit ids, test file paths, the test command, exit codes and up to 4,000 characters of output
per failing replay. Test output can contain secrets a test printed; `--no-logs` keeps it out.
No source code is sent.

## Before running this for other people

Add email verification and password reset, a sign-up rate limit, a per-account storage quota,
TLS at the proxy, and off-host backups of the SQLite file.
