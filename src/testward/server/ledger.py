"""SQLite storage for accounts, projects, replay reports and sign-offs."""

from __future__ import annotations

import json
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from . import credentials

SCHEMA_VERSION = 1
SESSION_SECONDS = 14 * 24 * 3600
REPORTS_KEPT_PER_PROJECT = 500
REPORTS_PER_HOUR = 120
LOGIN_FAILURES_ALLOWED = 5
LOGIN_WINDOW_SECONDS = 15 * 60
PROJECTS_PER_ACCOUNT = 50

SCHEMA = """
CREATE TABLE schema_version (version INTEGER NOT NULL);
CREATE TABLE accounts (
    id INTEGER PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    created_at INTEGER NOT NULL
);
CREATE TABLE sessions (
    token_digest TEXT PRIMARY KEY,
    account_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    csrf_token TEXT NOT NULL,
    expires_at INTEGER NOT NULL
);
CREATE TABLE login_failures (email TEXT NOT NULL, failed_at INTEGER NOT NULL);
CREATE INDEX login_failures_by_email ON login_failures(email, failed_at);
CREATE TABLE projects (
    id INTEGER PRIMARY KEY,
    account_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    token_digest TEXT NOT NULL UNIQUE,
    created_at INTEGER NOT NULL
);
CREATE TABLE reports (
    id INTEGER PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    head TEXT NOT NULL,
    merge_base TEXT NOT NULL,
    change_url TEXT NOT NULL,
    received_at INTEGER NOT NULL,
    body TEXT NOT NULL
);
CREATE INDEX reports_by_project ON reports(project_id, received_at);
CREATE TABLE signoffs (
    id INTEGER PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    fingerprint TEXT NOT NULL,
    path TEXT NOT NULL,
    reason TEXT NOT NULL,
    signed_by TEXT NOT NULL,
    signed_at INTEGER NOT NULL,
    UNIQUE (project_id, fingerprint)
);
"""


class Ledger:
    def __init__(self, path: Path):
        self.path = path

    @contextmanager
    def _db(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def create_tables(self) -> None:
        """Run once at startup."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._db() as conn:
            conn.execute("PRAGMA journal_mode = WAL")
            exists = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE name = 'schema_version'"
            ).fetchone()
            if exists:
                found = conn.execute("SELECT version FROM schema_version").fetchone()["version"]
                if found != SCHEMA_VERSION:
                    raise RuntimeError(
                        f"{self.path} is schema {found}, this build expects {SCHEMA_VERSION}"
                    )
                return
            conn.executescript(SCHEMA)
            conn.execute("INSERT INTO schema_version VALUES (?)", (SCHEMA_VERSION,))

    def is_reachable(self) -> bool:
        with self._db() as conn:
            return conn.execute("SELECT version FROM schema_version").fetchone() is not None

    def create_account(self, email: str, password: str) -> int | None:
        with self._db() as conn:
            try:
                cursor = conn.execute(
                    "INSERT INTO accounts (email, password_hash, created_at) VALUES (?, ?, ?)",
                    (email, credentials.hash_password(password), int(time.time())),
                )
            except sqlite3.IntegrityError:
                return None
            return cursor.lastrowid

    def login_is_locked(self, email: str) -> bool:
        since = int(time.time()) - LOGIN_WINDOW_SECONDS
        with self._db() as conn:
            failures = conn.execute(
                "SELECT COUNT(*) AS n FROM login_failures WHERE email = ? AND failed_at > ?",
                (email, since),
            ).fetchone()["n"]
        return failures >= LOGIN_FAILURES_ALLOWED

    def check_login(self, email: str, password: str) -> int | None:
        with self._db() as conn:
            account = conn.execute(
                "SELECT id, password_hash FROM accounts WHERE email = ?", (email,)
            ).fetchone()
            if account and credentials.password_matches(password, account["password_hash"]):
                conn.execute("DELETE FROM login_failures WHERE email = ?", (email,))
                return account["id"]
            conn.execute("INSERT INTO login_failures VALUES (?, ?)", (email, int(time.time())))
            conn.execute(
                "DELETE FROM login_failures WHERE failed_at < ?",
                (int(time.time()) - LOGIN_WINDOW_SECONDS,),
            )
            return None

    def open_session(self, account_id: int) -> str:
        token = credentials.new_token()
        with self._db() as conn:
            conn.execute("DELETE FROM sessions WHERE expires_at < ?", (int(time.time()),))
            conn.execute(
                "INSERT INTO sessions VALUES (?, ?, ?, ?)",
                (
                    credentials.token_digest(token),
                    account_id,
                    credentials.new_token(),
                    int(time.time()) + SESSION_SECONDS,
                ),
            )
        return token

    def session(self, token: str) -> sqlite3.Row | None:
        with self._db() as conn:
            return conn.execute(
                "SELECT s.account_id, s.csrf_token, a.email FROM sessions s "
                "JOIN accounts a ON a.id = s.account_id "
                "WHERE s.token_digest = ? AND s.expires_at > ?",
                (credentials.token_digest(token), int(time.time())),
            ).fetchone()

    def close_session(self, token: str) -> None:
        with self._db() as conn:
            conn.execute(
                "DELETE FROM sessions WHERE token_digest = ?", (credentials.token_digest(token),)
            )

    def create_project(self, account_id: int, name: str) -> tuple[int, str] | None:
        """Returns the project id and its token; the token is not recoverable afterwards."""
        token = credentials.new_token("tw_")
        with self._db() as conn:
            owned = conn.execute(
                "SELECT COUNT(*) AS n FROM projects WHERE account_id = ?", (account_id,)
            ).fetchone()["n"]
            if owned >= PROJECTS_PER_ACCOUNT:
                return None
            cursor = conn.execute(
                "INSERT INTO projects (account_id, name, token_digest, created_at) "
                "VALUES (?, ?, ?, ?)",
                (account_id, name, credentials.token_digest(token), int(time.time())),
            )
            return cursor.lastrowid, token

    def rotate_project_token(self, account_id: int, project_id: int) -> str | None:
        token = credentials.new_token("tw_")
        with self._db() as conn:
            changed = conn.execute(
                "UPDATE projects SET token_digest = ? WHERE id = ? AND account_id = ?",
                (credentials.token_digest(token), project_id, account_id),
            ).rowcount
        return token if changed else None

    def projects(self, account_id: int) -> list[sqlite3.Row]:
        with self._db() as conn:
            return conn.execute(
                "SELECT p.id, p.name, "
                "(SELECT COUNT(*) FROM reports r WHERE r.project_id = p.id) AS report_count "
                "FROM projects p WHERE p.account_id = ? ORDER BY p.created_at DESC",
                (account_id,),
            ).fetchall()

    def project(self, account_id: int, project_id: int) -> sqlite3.Row | None:
        with self._db() as conn:
            return conn.execute(
                "SELECT id, name FROM projects WHERE id = ? AND account_id = ?",
                (project_id, account_id),
            ).fetchone()

    def project_for_token(self, token: str) -> int | None:
        with self._db() as conn:
            row = conn.execute(
                "SELECT id FROM projects WHERE token_digest = ?",
                (credentials.token_digest(token),),
            ).fetchone()
        return row["id"] if row else None

    def record_report(self, project_id: int, report: dict) -> int | None:
        """Stores the report. Returns None when the project is over its hourly limit."""
        now = int(time.time())
        with self._db() as conn:
            recent = conn.execute(
                "SELECT COUNT(*) AS n FROM reports WHERE project_id = ? AND received_at > ?",
                (project_id, now - 3600),
            ).fetchone()["n"]
            if recent >= REPORTS_PER_HOUR:
                return None
            cursor = conn.execute(
                "INSERT INTO reports (project_id, head, merge_base, change_url, received_at, body) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    project_id,
                    report["head"],
                    report["merge_base"],
                    report["context"].get("change_url", ""),
                    now,
                    json.dumps(report),
                ),
            )
            conn.execute(
                "DELETE FROM reports WHERE project_id = ? AND id NOT IN ("
                "SELECT id FROM reports WHERE project_id = ? ORDER BY id DESC LIMIT ?)",
                (project_id, project_id, REPORTS_KEPT_PER_PROJECT),
            )
            return cursor.lastrowid

    def signed_fingerprints(self, project_id: int) -> set[str]:
        with self._db() as conn:
            rows = conn.execute(
                "SELECT fingerprint FROM signoffs WHERE project_id = ?", (project_id,)
            ).fetchall()
        return {row["fingerprint"] for row in rows}

    def recent_reports(self, project_id: int, limit: int = 30) -> list[dict]:
        with self._db() as conn:
            rows = conn.execute(
                "SELECT id, received_at, change_url, body FROM reports "
                "WHERE project_id = ? ORDER BY id DESC LIMIT ?",
                (project_id, limit),
            ).fetchall()
        return [
            {
                "id": row["id"],
                "received_at": row["received_at"],
                "change_url": row["change_url"],
                **json.loads(row["body"]),
            }
            for row in rows
        ]

    def fingerprint_was_reported(self, project_id: int, fingerprint: str) -> str | None:
        """The path a fingerprint belongs to, if a stored report flagged it for sign-off."""
        for report in self.recent_reports(project_id, limit=REPORTS_KEPT_PER_PROJECT):
            for entry in report["files"]:
                if entry["fingerprint"] == fingerprint and entry["verdict"] == "needs_signoff":
                    return entry["path"]
        return None

    def sign_off(
        self, project_id: int, fingerprint: str, path: str, reason: str, signed_by: str
    ) -> None:
        with self._db() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO signoffs "
                "(project_id, fingerprint, path, reason, signed_by, signed_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (project_id, fingerprint, path, reason, signed_by, int(time.time())),
            )

    def revoke_signoff(self, project_id: int, signoff_id: int) -> None:
        with self._db() as conn:
            conn.execute(
                "DELETE FROM signoffs WHERE id = ? AND project_id = ?", (signoff_id, project_id)
            )

    def signoffs(self, project_id: int) -> list[sqlite3.Row]:
        with self._db() as conn:
            return conn.execute(
                "SELECT id, fingerprint, path, reason, signed_by, signed_at FROM signoffs "
                "WHERE project_id = ? ORDER BY signed_at DESC LIMIT 200",
                (project_id,),
            ).fetchall()
