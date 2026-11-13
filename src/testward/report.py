"""Report shapes: the JSON a server stores and the Markdown a reviewer reads."""

from __future__ import annotations

from .replay import HELD, INCONCLUSIVE, NEEDS_SIGNOFF, SCHEMA_VERSION, FileResult, Report

VERDICT_TEXT = {
    HELD: "held: the old test still passes",
    NEEDS_SIGNOFF: "needs sign-off: the old test fails on the new code",
    INCONCLUSIVE: "inconclusive",
}


def to_dict(report: Report, context: dict[str, str] | None = None, include_logs: bool = True) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "base": report.base,
        "head": report.head,
        "merge_base": report.merge_base,
        "command": report.command,
        "config_source": report.config_source,
        "support_changed": report.support_changed,
        "context": context or {},
        "files": [
            {
                "path": f.path,
                "status": f.status,
                "new_path": f.new_path,
                "fingerprint": f.fingerprint,
                "verdict": f.verdict,
                "head_exit": f.head_exit,
                "control_exit": f.control_exit,
                "seconds": round(f.seconds, 2),
                "note": f.note,
                "waived": f.waived,
                "log_tail": f.log_tail if include_logs else "",
            }
            for f in report.files
        ],
    }


def headline(report: Report) -> str:
    if not report.files:
        return "no existing test was modified, deleted or renamed"
    open_count = len(report.unresolved())
    waived = sum(1 for f in report.files if f.waived)
    held = sum(1 for f in report.files if f.verdict == HELD)
    unsure = sum(1 for f in report.files if f.verdict == INCONCLUSIVE)
    parts = [f"{open_count} need sign-off", f"{held} held"]
    if waived:
        parts.append(f"{waived} signed off")
    if unsure:
        parts.append(f"{unsure} inconclusive")
    return f"{len(report.files)} changed test file(s): " + ", ".join(parts)


def _exit(code: int | None, ran: bool) -> str:
    if not ran:
        return "not run"
    return "timeout" if code is None else f"exit {code}"


def _row(f: FileResult) -> str:
    verdict = "signed off" if f.waived else VERDICT_TEXT[f.verdict]
    if f.note:
        verdict += f" ({f.note})"
    change = f"renamed to `{f.new_path}`" if f.new_path else f.status
    return (
        f"| `{f.path}` | {change} | {_exit(f.head_exit, f.replayed)} "
        f"| {_exit(f.control_exit, f.control_ran)} | {verdict} |"
    )


def to_markdown(report: Report) -> str:
    lines = [f"## testward: {headline(report)}", ""]
    if report.files:
        lines += [
            f"Tests as they were at `{report.merge_base[:10]}` were run against the code at "
            f"`{report.head[:10]}` with `{report.command}` (config from {report.config_source}).",
            "",
            "| Test file | Change | Old test, new code | Old test, old code | Verdict |",
            "|---|---|---|---|---|",
            *[_row(f) for f in report.files],
            "",
        ]
        for f in report.files:
            if f.verdict != HELD and f.log_tail:
                fence = "````"
                lines += [
                    f"<details><summary>Output of the old <code>{f.path}</code> on the new code</summary>",
                    "",
                    f"{fence}text",
                    f.log_tail.strip(),
                    fence,
                    "",
                    "</details>",
                    "",
                ]
    if report.support_changed:
        listed = ", ".join(f"`{p}`" for p in report.support_changed[:20])
        lines += [
            f"Fixtures or snapshots also changed and were restored for the replay: {listed}.",
            "",
        ]
    return "\n".join(lines)
