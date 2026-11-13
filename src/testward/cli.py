from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

from . import __version__
from .config import ConfigError
from .git import GitError
from .replay import NEEDS_SIGNOFF, ReplayError, Report, replay
from .report import headline, to_dict, to_markdown

log = logging.getLogger("testward")

EXIT_OK, EXIT_NEEDS_SIGNOFF, EXIT_ERROR = 0, 1, 2
UPLOAD_TIMEOUT_SECONDS = 20


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="testward",
        description="Replay the base branch's tests against the current checkout.",
    )
    parser.add_argument("--version", action="version", version=f"testward {__version__}")
    commands = parser.add_subparsers(dest="action", required=True)

    run = commands.add_parser("replay", help="replay changed tests from the merge base")
    run.add_argument("--base", required=True, help="branch or commit the change will merge into")
    run.add_argument("--repo", default=".", help="path to the git checkout (default: .)")
    run.add_argument(
        "--command",
        help="test command when the base branch has no .testward.toml; {file} is the test file",
    )
    run.add_argument("--json", dest="json_path", help="write the report as JSON to this path")
    run.add_argument("--markdown", dest="markdown_path", help="write the report as Markdown here")
    run.add_argument("--strict", action="store_true", help="inconclusive replays also fail")
    run.add_argument(
        "--server",
        help="testward server URL; sends the report and applies human sign-offs "
        "(project token is read from the TESTWARD_TOKEN environment variable)",
    )
    run.add_argument("--no-logs", action="store_true", help="do not send test output to the server")

    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="testward: %(message)s", stream=sys.stderr)
    try:
        return _replay(args)
    except (ConfigError, ReplayError, GitError) as problem:
        log.error("%s", problem)
        return EXIT_ERROR


def _replay(args: argparse.Namespace) -> int:
    report = replay(Path(args.repo), args.base, args.command)

    if args.server and report.files:
        token = os.environ.get("TESTWARD_TOKEN", "")
        if not token:
            raise ReplayError("--server needs the project token in TESTWARD_TOKEN")
        _apply_signoffs(report, args.server, token, include_logs=not args.no_logs)

    if args.json_path:
        Path(args.json_path).write_text(
            json.dumps(to_dict(report, _ci_context()), indent=2), encoding="utf-8"
        )
    markdown = to_markdown(report)
    if args.markdown_path:
        with open(args.markdown_path, "a", encoding="utf-8") as out:
            out.write(markdown + "\n")
    print(markdown)

    log.info("%s", headline(report))
    return EXIT_NEEDS_SIGNOFF if report.unresolved(strict=args.strict) else EXIT_OK


def _ci_context() -> dict[str, str]:
    """Where the report came from, when GitHub Actions says so."""
    context: dict[str, str] = {}
    repository = os.environ.get("GITHUB_REPOSITORY", "")
    if repository:
        context["repository"] = repository[:200]
    pull = re.fullmatch(r"refs/pull/(\d+)/merge", os.environ.get("GITHUB_REF", ""))
    if pull and repository:
        server = os.environ.get("GITHUB_SERVER_URL", "https://github.com")
        context["change_url"] = f"{server}/{repository}/pull/{pull.group(1)}"[:500]
    return context


def _apply_signoffs(report: Report, server: str, token: str, include_logs: bool) -> None:
    """Send the report; mark the files a human already signed off.

    If the server cannot be reached the verdicts stand unsigned, so the gate fails closed.
    """
    body = json.dumps(to_dict(report, _ci_context(), include_logs)).encode()
    request = urllib.request.Request(
        server.rstrip("/") + "/api/v1/reports",
        data=body,
        method="POST",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=UPLOAD_TIMEOUT_SECONDS) as response:
            answer = json.loads(response.read(1_000_000))
    except urllib.error.HTTPError as refused:
        detail = refused.read(2000).decode("utf-8", "replace")
        log.warning("server refused the report (%s): %s", refused.code, detail)
        return
    except (urllib.error.URLError, TimeoutError, ValueError) as unreachable:
        log.warning("could not reach %s, no sign-offs applied: %s", server, unreachable)
        return

    signed = set(answer.get("signed_off", []))
    for result in report.files:
        if result.verdict == NEEDS_SIGNOFF and result.fingerprint in signed:
            result.waived = True
    if answer.get("report_url"):
        log.info("sign off or inspect at %s", answer["report_url"])


if __name__ == "__main__":
    sys.exit(main())
