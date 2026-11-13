"""Population funnel from AIDev metadata. Reads only the columns it needs over HTTP; no
repository code is fetched or run. Writes candidates.parquet and prints the funnel."""

from __future__ import annotations

import duckdb

SOURCE = "https://huggingface.co/datasets/hao-li/AIDev/resolve/main/"
PY_TEST = r"(^|/)(test_[^/]*\.py|[^/]*_test\.py)$"

db = duckdb.connect()
db.execute("INSTALL httpfs; LOAD httpfs; SET enable_progress_bar = false;")

db.execute(
    f"""
    CREATE TABLE merged_python AS
    SELECT p.id AS pr_id, p.number, p.agent, p.html_url, p.merged_at, p.title,
           r.full_name, r.stars
    FROM read_parquet('{SOURCE}pull_request.parquet') p
    JOIN read_parquet('{SOURCE}repository.parquet') r ON r.id = p.repo_id
    WHERE p.merged_at IS NOT NULL AND r.language = 'Python'
    """
)
db.execute(
    f"""
    CREATE TABLE touched AS
    SELECT d.pr_id, d.filename, d.status
    FROM read_parquet('{SOURCE}pr_commit_details.parquet') d
    WHERE d.pr_id IN (SELECT pr_id FROM merged_python)
      AND regexp_matches(d.filename, '{PY_TEST}')
    """
)
# A file first added inside the same pull request did not exist at the base.
db.execute(
    """
    CREATE TABLE existing_test_edits AS
    SELECT pr_id, filename, list(DISTINCT status) AS statuses
    FROM touched
    GROUP BY pr_id, filename
    HAVING NOT list_contains(list(status), 'added')
       AND (list_contains(list(status), 'modified')
            OR list_contains(list(status), 'removed')
            OR list_contains(list(status), 'renamed'))
    """
)
db.execute(
    """
    CREATE TABLE candidates AS
    SELECT m.*, e.test_files, e.removed_files
    FROM merged_python m
    JOIN (
        SELECT pr_id, count(*) AS test_files,
               count(*) FILTER (WHERE list_contains(statuses, 'removed')) AS removed_files
        FROM existing_test_edits GROUP BY pr_id
    ) e USING (pr_id)
    """
)
db.execute("COPY candidates TO 'candidates.parquet' (FORMAT parquet)")


def one(sql: str):
    return db.execute(sql).fetchone()[0]


total = one(f"SELECT count(*) FROM read_parquet('{SOURCE}pull_request.parquet')")
print("pull requests in pull_request.parquet:", total)
print("merged, Python repository:", one("SELECT count(*) FROM merged_python"))
print("  of those, touching any test_*.py / *_test.py:", one("SELECT count(DISTINCT pr_id) FROM touched"))
print("  of those, editing a test file that already existed:", one("SELECT count(*) FROM candidates"))
print("  of those, removing an existing test file:", one("SELECT count(*) FROM candidates WHERE removed_files > 0"))
print("repositories among candidates:", one("SELECT count(DISTINCT full_name) FROM candidates"))
print("by agent:")
for agent, merged, cand in db.execute(
    """
    SELECT m.agent, count(*) AS merged, count(c.pr_id) AS candidates
    FROM merged_python m LEFT JOIN candidates c USING (pr_id)
    GROUP BY 1 ORDER BY 2 DESC
    """
).fetchall():
    print(f"  {agent}: {cand} of {merged} merged ({100 * cand / merged:.1f}%)")
