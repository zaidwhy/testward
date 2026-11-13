"""Run every sample row whose position falls in this chunk through replay_one.py.

Resumable: rows already in the output file are skipped.
Usage: python run_chunk.py <sample.jsonl> <chunk> <chunks> <out.jsonl>
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent


def main(sample: Path, chunk: int, chunks: int, out_path: Path) -> None:
    rows = [json.loads(line) for line in sample.read_text(encoding="utf-8").splitlines()]
    rows = [row for row in rows if row["resolves"]]
    done = set()
    if out_path.exists():
        done = {json.loads(line)["pr_id"] for line in out_path.read_text(encoding="utf-8").splitlines()}
    for position, row in enumerate(rows):
        if position % chunks != chunk or row["pr_id"] in done:
            continue
        print(f"[{position}] {row['repository']}#{row['number']}", flush=True)
        subprocess.run(
            [sys.executable, str(HERE / "replay_one.py"), "work", str(out_path)],
            input=json.dumps(row).encode(),
            check=False,
        )


if __name__ == "__main__":
    main(Path(sys.argv[1]), int(sys.argv[2]), int(sys.argv[3]), Path(sys.argv[4]))
