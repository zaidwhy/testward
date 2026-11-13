# Running it

## The check in GitHub Actions

`.github/workflows/testward.yml` in the repository being guarded:

```yaml
name: testward
on: pull_request
permissions:
  contents: read
jobs:
  replay:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0          # the replay needs the merge base
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      # install whatever your tests need, exactly as your normal test job does
      - run: pip install -e . pytest
      - uses: zaidwhy/testward@v0
        with:
          base: origin/${{ github.base_ref }}
          command: pytest {file} -q
          server: https://your-testward-host        # optional
        env:
          TESTWARD_TOKEN: ${{ secrets.TESTWARD_TOKEN }}   # only with server
```

`zaidwhy/testward@v0` resolves only after the repository is pushed and tagged (below). Make the
job a required check in branch protection, or it is advice.

## The server

Settings come from the environment:

| Variable | Meaning | Default |
|---|---|---|
| `TESTWARD_BASE_URL` | Public URL, no trailing slash. Drives the Origin check, Secure cookies and links in CLI output | `http://127.0.0.1:8000` |
| `TESTWARD_DB` | Path of the SQLite file | `data/testward.sqlite3` |
| `TESTWARD_ALLOW_SIGNUP` | `0` closes registration | `1` |

Local:

```bash
pip install ".[server]"
uvicorn testward.server.app:create_app --factory --port 8000
curl http://127.0.0.1:8000/health      # {"status":"ok"}
```

Container (not built or run during development; treat the first build as a test):

```bash
docker build -t testward .
docker run -d --name testward -p 8000:8000 -v testward-data:/data \
  -e TESTWARD_BASE_URL=https://testward.example.com testward
```

Put it behind a proxy that terminates TLS (Caddy, nginx, or a platform's router). Run one
instance: the database is a single SQLite file on the volume.

Backup: `sqlite3 /data/testward.sqlite3 ".backup '/backup/testward.sqlite3'"` on a schedule,
copied off the host.

## Publishing (steps for Zaid, none done yet)

1. `gh repo create zaidwhy/testward --private --source . --push`, then make it public when
   ready. The Action cannot be used from a private repository by other accounts.
2. `git tag v0.1.0 && git tag v0 && git push --tags`. The workflow above pins `@v0`.
3. PyPI: `uv build && uv publish`. The name `testward` returned 404 on PyPI's JSON API on
   2026-11-13, so it was free then.
4. Deploy the server on the personal account, set `TESTWARD_BASE_URL`, check `/health` with
   `curl -L`.
