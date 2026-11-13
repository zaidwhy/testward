"""Turn replay rows into the pre-registered numbers.

Usage: python analyze.py <out-*.jsonl ...>
Prints the table and writes flagged.jsonl (one row per pull request that needs sign-off),
which is what the reading pass labels.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from math import sqrt
from pathlib import Path


def wilson(hits: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return 0.0, 1.0
    p = hits / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return max(centre - half, 0.0), min(centre + half, 1.0)


def outcome(row: dict) -> str:
    """One label per pull request, in the order the exclusions apply."""
    if row["stage"] == "clone":
        return "clone failed"
    if row.get("changed_files") is not None and row.get("diff_files") != row["changed_files"]:
        return "excluded: merge commit is not the pull request diff"
    verdicts = row.get("verdicts")
    if verdicts is None:
        return "replay did not run"
    if not verdicts:
        return "no existing test changed at replay"
    values = set(verdicts.values())
    if "needs_signoff" in values:
        stable = all(
            rerun.get(path) == "needs_signoff"
            for rerun in row.get("reruns") or []
            for path, verdict in verdicts.items()
            if verdict == "needs_signoff"
        )
        return "needs sign-off" if stable and len(row.get("reruns") or []) == 2 else "unstable"
    return "held" if values == {"held"} else "inconclusive"


def main(paths: list[Path]) -> None:
    rows: dict[int, dict] = {}
    for path in paths:
        for line in path.read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            rows[row["pr_id"]] = row
    labelled = {pr_id: outcome(row) for pr_id, row in rows.items()}
    counts = Counter(labelled.values())
    print(f"pull requests with a result row: {len(rows)}")
    for label, n in counts.most_common():
        print(f"  {label}: {n}")

    flagged = counts["needs sign-off"]
    conclusive = flagged + counts["held"]
    measurable = [r for r in rows.values() if labelled[r["pr_id"]] not in (
        "clone failed", "excluded: merge commit is not the pull request diff",
        "no existing test changed at replay")]
    yield_low, yield_high = wilson(conclusive, len(measurable))
    print(f"\nconclusive replays: {conclusive} of {len(measurable)} attempted "
          f"({100 * conclusive / max(len(measurable), 1):.1f}%, 95% CI "
          f"{100 * yield_low:.1f}-{100 * yield_high:.1f}%)")
    low, high = wilson(flagged, conclusive)
    print(f"needs sign-off: {flagged} of {conclusive} conclusive "
          f"({100 * flagged / max(conclusive, 1):.1f}%, 95% CI {100 * low:.1f}-{100 * high:.1f}%)")

    floor_runs = [r for r in rows.values() if r.get("floor")]
    floor_hits = [r for r in floor_runs if "needs_signoff" in r["floor"].values()]
    print(f"floor control (comment-only change): {len(floor_hits)} of {len(floor_runs)} flagged; must be 0")

    print("\nby agent (needs sign-off / conclusive):")
    by_agent: dict[str, list[int]] = {}
    for row in rows.values():
        label = labelled[row["pr_id"]]
        if label in ("needs sign-off", "held"):
            tally = by_agent.setdefault(row["agent"], [0, 0])
            tally[0] += label == "needs sign-off"
            tally[1] += 1
    for agent, (hits, n) in sorted(by_agent.items(), key=lambda item: -item[1][1]):
        print(f"  {agent}: {hits} / {n}")

    with open("flagged.jsonl", "w", encoding="utf-8") as out:
        for row in rows.values():
            if labelled[row["pr_id"]] == "needs sign-off":
                files = [p for p, v in row["verdicts"].items() if v == "needs_signoff"]
                out.write(json.dumps({"url": row["url"], "agent": row["agent"], "files": files}) + "\n")
    print(f"\nflagged.jsonl: {flagged} pull requests to read and label")


if __name__ == "__main__":
    main([Path(p) for p in sys.argv[1:]])
