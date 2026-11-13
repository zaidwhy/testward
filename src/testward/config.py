"""Replay settings.

The file is read from the merge base, never from the change under review: a change that
could rewrite its own test command could turn the gate into `true`.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from fnmatch import fnmatch
from pathlib import PurePosixPath

CONFIG_PATH = ".testward.toml"

DEFAULT_TEST_GLOBS = (
    "test_*.py",
    "*_test.py",
    "*.test.*",
    "*.spec.*",
    "*_test.go",
    "*Test.java",
    "*Tests.cs",
    "*_spec.rb",
)
# Restored alongside the tests but never run on their own.
DEFAULT_SUPPORT_GLOBS = ("conftest.py", "*.snap", "*/__snapshots__/*", "__snapshots__/*")

TIMEOUT_LIMIT = 3600
FILE_LIMIT = 200


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class ReplayConfig:
    command: str | None = None
    setup: str | None = None
    test_globs: tuple[str, ...] = DEFAULT_TEST_GLOBS
    support_globs: tuple[str, ...] = DEFAULT_SUPPORT_GLOBS
    timeout_seconds: int = 300
    max_files: int = 40
    source: str = field(default="defaults", compare=False)

    def is_test(self, path: str) -> bool:
        return _matches(path, self.test_globs)

    def is_support(self, path: str) -> bool:
        return not self.is_test(path) and _matches(path, self.support_globs)


def _matches(path: str, globs: tuple[str, ...]) -> bool:
    name = PurePosixPath(path).name
    return any(fnmatch(path if "/" in glob else name, glob) for glob in globs)


def parse(text: str, source: str) -> ReplayConfig:
    try:
        raw = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"{CONFIG_PATH} ({source}) is not valid TOML: {exc}") from exc

    known = {"command", "setup", "test_globs", "support_globs", "timeout_seconds", "max_files"}
    unknown = sorted(set(raw) - known)
    if unknown:
        raise ConfigError(f"{CONFIG_PATH}: unknown key(s) {', '.join(unknown)}")

    return ReplayConfig(
        command=_text(raw, "command"),
        setup=_text(raw, "setup"),
        test_globs=_globs(raw, "test_globs", DEFAULT_TEST_GLOBS),
        support_globs=_globs(raw, "support_globs", DEFAULT_SUPPORT_GLOBS),
        timeout_seconds=_bounded(raw, "timeout_seconds", 300, TIMEOUT_LIMIT),
        max_files=_bounded(raw, "max_files", 40, FILE_LIMIT),
        source=source,
    )


def _text(raw: dict, key: str) -> str | None:
    value = raw.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip() or len(value) > 500:
        raise ConfigError(f"{CONFIG_PATH}: {key} must be a non-empty string of at most 500 characters")
    return value.strip()


def _globs(raw: dict, key: str, default: tuple[str, ...]) -> tuple[str, ...]:
    value = raw.get(key)
    if value is None:
        return default
    ok = isinstance(value, list) and 0 < len(value) <= 50 and all(
        isinstance(g, str) and 0 < len(g) <= 200 for g in value
    )
    if not ok:
        raise ConfigError(f"{CONFIG_PATH}: {key} must be a list of 1 to 50 glob strings")
    return tuple(value)


def _bounded(raw: dict, key: str, default: int, limit: int) -> int:
    value = raw.get(key, default)
    if not isinstance(value, int) or isinstance(value, bool) or not 1 <= value <= limit:
        raise ConfigError(f"{CONFIG_PATH}: {key} must be a whole number from 1 to {limit}")
    return value
