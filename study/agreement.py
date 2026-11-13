"""Agreement between the second rater (labels-zaid.jsonl) and the first rater."""
from __future__ import annotations

import json
import sys
from pathlib import Path

RESULTS_DIR = Path(__file__).resolve().parent / "results"
LABELS = ("intended", "laundered", "unclear")
TOTAL_PRS = 62


def latest_by_url(path: Path) -> dict[str, dict]:
    latest: dict[str, dict] = {}
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                entry = json.loads(line)
                latest[entry["url"]] = entry
    return latest


def cohen_kappa(pairs: list[tuple[str, str]]) -> float | None:
    total = len(pairs)
    if total == 0:
        return None
    observed = sum(1 for mine, theirs in pairs if mine == theirs) / total
    expected = sum(
        (sum(1 for mine, _ in pairs if mine == label) / total)
        * (sum(1 for _, theirs in pairs if theirs == label) / total)
        for label in LABELS
    )
    if expected == 1:
        return None
    return (observed - expected) / (1 - expected)


def report_block(title: str, pairs: list[tuple[str, str]]) -> list[str]:
    lines = [title]
    if not pairs:
        return lines + ["  no PRs labelled by both raters", ""]
    agreed = sum(1 for mine, theirs in pairs if mine == theirs)
    lines.append(f"  raw agreement: {agreed}/{len(pairs)} ({100 * agreed / len(pairs):.1f}%)")
    kappa = cohen_kappa(pairs)
    if kappa is None:
        lines.append("  Cohen's kappa: undefined (expected agreement is 1, both raters use one label throughout)")
    else:
        lines.append(f"  Cohen's kappa: {kappa:.3f}")
    lines.append("  confusion table (rows: Zaid, columns: first rater)")
    lines.append("  " + " " * 10 + "".join(f"{label:>11}" for label in LABELS))
    for mine in LABELS:
        counts = [sum(1 for m, t in pairs if m == mine and t == theirs) for theirs in LABELS]
        lines.append("  " + f"{mine:<10}" + "".join(f"{count:>11}" for count in counts))
    lines.append("")
    return lines


def build_report(zaid: dict[str, dict], first: dict[str, dict]) -> str:
    shared = [url for url in zaid if url in first]
    final_pairs = [(zaid[url]["label"], first[url]["label"]) for url in shared]
    # first_label exists only on rows the first rater revised; elsewhere it equals label
    first_pass_pairs = [(zaid[url]["label"], first[url].get("first_label", first[url]["label"])) for url in shared]

    lines = [f"Zaid has labelled {len(zaid)} of {TOTAL_PRS} PRs; {len(shared)} overlap with the first rater.", ""]
    lines += report_block("Against the first rater's final labels", final_pairs)
    lines += report_block("Against the first rater's first-pass labels", first_pass_pairs)
    lines.append("Disagreements with the final labels")
    disagreements = [url for url in shared if zaid[url]["label"] != first[url]["label"]]
    if not disagreements:
        lines.append("  none")
    for url in disagreements:
        lines.append(f"  {url}")
        lines.append(f"    Zaid: {zaid[url]['label']}; note: {zaid[url].get('note') or '(none)'}")
        lines.append(f"    first rater: {first[url]['label']}; reason: {first[url].get('reason', '')}")
    return "\n".join(lines)


def main(results_dir: Path = RESULTS_DIR) -> int:
    zaid_path = results_dir / "labels-zaid.jsonl"
    if not zaid_path.exists():
        print(f"missing file: {zaid_path}", file=sys.stderr)
        return 2
    first: dict[str, dict] = {}
    for name in ("labels-a.jsonl", "labels-b.jsonl"):
        first.update(latest_by_url(results_dir / name))
    print(build_report(latest_by_url(zaid_path), first))
    return 0


if __name__ == "__main__":
    sys.exit(main())
