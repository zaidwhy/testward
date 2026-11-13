#!/usr/bin/env bash
# Harness check on a repository built here, so no outside code runs. Expects one
# needs_signoff (the loosened test), one held, and a floor control with no needs_signoff.
# Usage: bash selftest.sh <scratch_dir>
set -eu
HERE="$(cd "$(dirname "$0")" && pwd)"
WORK="$1"; rm -rf "$WORK"; mkdir -p "$WORK/origin"
cd "$WORK/origin"
git init -q -b main; git config user.email dev@example.invalid; git config user.name dev
mkdir tests
printf 'def total(prices):\n    return sum(prices)\n' > shop.py
printf 'import sys; sys.path.insert(0, ".")\nfrom shop import total\n\ndef test_total():\n    assert total([1, 2, 3]) == 6\n' > tests/test_total.py
printf 'import sys; sys.path.insert(0, ".")\nfrom shop import total\n\ndef test_empty():\n    assert total([]) == 0\n' > tests/test_empty.py
git add -A; git commit -q -m base
PARENT=$(git rev-parse HEAD)
printf 'def total(prices):\n    return sum(prices[1:])\n' > shop.py
printf 'import sys; sys.path.insert(0, ".")\nfrom shop import total\n\ndef test_total():\n    assert total([1, 2, 3])\n' > tests/test_total.py
printf 'import sys; sys.path.insert(0, ".")\nfrom shop import total\n\ndef test_empty():\n    assert total([]) == 0  # empty basket\n' > tests/test_empty.py
git commit -q -am "make CI green"
MERGE=$(git rev-parse HEAD)

export TESTWARD_SOURCE="$(cd "$HERE/.." && pwd -W 2>/dev/null || pwd)"
ROW="{\"pr_id\": 1, \"repository\": \"local/selftest\", \"number\": 1, \"agent\": \"none\", \"url\": \"\", \"stars\": 0, \"merge_sha\": \"$MERGE\", \"first_parent\": \"$PARENT\", \"changed_files\": 3, \"clone_url\": \"$(pwd -W 2>/dev/null || pwd)\"}"
echo "$ROW" | python "$HERE/replay_one.py" "$WORK/run" "$WORK/out.jsonl"
python - "$WORK/out.jsonl" <<'PY'
import json, sys
row = json.loads(open(sys.argv[1]).read().splitlines()[-1])
print({k: row.get(k) for k in ("stage", "installed", "diff_files", "verdicts", "reruns", "floor", "seconds", "error")})
assert row["stage"] == "done", row
assert row["verdicts"] == {"tests/test_empty.py": "held", "tests/test_total.py": "needs_signoff"}
assert all(r == row["verdicts"] for r in row["reruns"])
assert set(row["floor"].values()) == {"held"}, row["floor"]
print("selftest ok")
PY
