"""Collect what a rater needs for each flagged pull request: title, description, who merged
it, and the diff of each flagged test file. Metadata only, through the GitHub API.

Usage: python dossier.py flagged.jsonl dossier.jsonl   (resumable)
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

BODY_CHARS = 1200
PATCH_CHARS = 2500


def gh(path: str):
    done = subprocess.run(
        ["gh", "api", "--paginate", path], capture_output=True, text=True, encoding="utf-8"
    )
    return json.loads(done.stdout) if done.returncode == 0 else None


def main(flagged: Path, out_path: Path) -> None:
    seen = set()
    if out_path.exists():
        seen = {json.loads(line)["url"] for line in out_path.read_text(encoding="utf-8").splitlines()}
    with out_path.open("a", encoding="utf-8") as out:
        for line in flagged.read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            if row["url"] in seen:
                continue
            owner, name, number = re.fullmatch(
                r"https://github.com/([^/]+)/([^/]+)/pull/(\d+)", row["url"]
            ).groups()
            pull = gh(f"repos/{owner}/{name}/pulls/{number}") or {}
            files = gh(f"repos/{owner}/{name}/pulls/{number}/files") or []
            patches = {
                f["filename"]: {"status": f["status"], "patch": (f.get("patch") or "")[:PATCH_CHARS]}
                for f in files
                if f["filename"] in row["files"] or f.get("previous_filename") in row["files"]
            }
            out.write(json.dumps({
                "url": row["url"],
                "agent": row["agent"],
                "title": pull.get("title"),
                "body": (pull.get("body") or "")[:BODY_CHARS],
                "author": (pull.get("user") or {}).get("login"),
                "merged_by": (pull.get("merged_by") or {}).get("login"),
                "changed_files": pull.get("changed_files"),
                "flagged_files": row["files"],
                "patches": patches,
            }) + "\n")
            out.flush()


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))
