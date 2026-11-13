"""Draw the pre-registered sample and resolve each pull request's commits from the GitHub API.

Metadata only: nothing is cloned or run. Resumable: pull requests already in the output file
are skipped. Usage: python sample.py <seed> <size> <out.jsonl>
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import duckdb

PER_REPOSITORY = 3
OVERSAMPLE = 1.6  # some pull requests no longer resolve; draw extra, keep the first <size> that do


def gh_json(path: str) -> dict | None:
    done = subprocess.run(["gh", "api", path], capture_output=True, text=True, encoding="utf-8")
    if done.returncode != 0:
        return None
    return json.loads(done.stdout)


def main(seed: int, size: int, out_path: Path) -> None:
    db = duckdb.connect()
    # hash() with a fixed seed string gives an order that does not depend on row order.
    drawn = db.execute(
        f"""
        WITH ranked AS (
            SELECT *, row_number() OVER (
                PARTITION BY full_name ORDER BY hash(pr_id::VARCHAR || '{seed}')
            ) AS within_repository
            FROM 'candidates.parquet'
        )
        SELECT pr_id, full_name, number, agent, html_url, stars, test_files, removed_files
        FROM ranked WHERE within_repository <= {PER_REPOSITORY}
        ORDER BY hash(pr_id::VARCHAR || '{seed}')
        LIMIT {int(size * OVERSAMPLE)}
        """
    ).fetchall()
    columns = ["pr_id", "repository", "number", "agent", "url", "stars", "test_files", "removed_files"]

    seen = set()
    resolved = 0
    if out_path.exists():
        for line in out_path.read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            seen.add(row["pr_id"])
            resolved += row["resolves"]

    with out_path.open("a", encoding="utf-8") as out:
        for values in drawn:
            if resolved >= size:
                break
            row = dict(zip(columns, values))
            if row["pr_id"] in seen:
                continue
            pull = gh_json(f"repos/{row['repository']}/pulls/{row['number']}")
            merge_sha = (pull or {}).get("merge_commit_sha")
            commit = gh_json(f"repos/{row['repository']}/commits/{merge_sha}") if merge_sha else None
            parents = [p["sha"] for p in (commit or {}).get("parents", [])]
            row.update(
                resolves=bool(pull and pull.get("merged") and parents),
                merge_sha=merge_sha,
                first_parent=parents[0] if parents else None,
                parent_count=len(parents),
                changed_files=(pull or {}).get("changed_files"),
            )
            out.write(json.dumps(row) + "\n")
            out.flush()
            resolved += row["resolves"]
    print(f"{resolved} resolving pull requests in {out_path}")


if __name__ == "__main__":
    main(int(sys.argv[1]), int(sys.argv[2]), Path(sys.argv[3]))
