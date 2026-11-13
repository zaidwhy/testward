"""Local labelling server for the independent second rater.

Serves the 62 flagged PRs without the first rater's labels or the agent name,
and appends the rater's own judgements to labels-zaid.jsonl.
"""
from __future__ import annotations

import argparse
import json
import logging
import random
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Lock

logger = logging.getLogger("label_server")

STUDY_DIR = Path(__file__).resolve().parent
RESULTS_DIR = STUDY_DIR / "results"
PAGE_PATH = STUDY_DIR / "label_page.html"
DOSSIER_PATHS = (RESULTS_DIR / "dossier-a.jsonl", RESULTS_DIR / "dossier-b.jsonl")
LABELS_PATH = RESULTS_DIR / "labels-zaid.jsonl"

SHUFFLE_SEED = 20261114
LABELS = ("intended", "laundered", "unclear")
MAX_BODY_BYTES = 4096
MAX_NOTE_CHARS = 500
# "agent" is left out on purpose: knowing which tool wrote the PR could bias the rater.
SERVED_FIELDS = ("url", "title", "body", "author", "merged_by", "changed_files", "flagged_files", "patches")


def load_items(dossier_paths) -> list[dict]:
    rows = []
    for path in dossier_paths:
        with open(path, encoding="utf-8") as handle:
            rows.extend(json.loads(line) for line in handle if line.strip())
    # sort before shuffling so the order does not depend on file order
    rows.sort(key=lambda row: row["url"])
    random.Random(SHUFFLE_SEED).shuffle(rows)
    items = []
    for row in rows:
        item = {field: row.get(field) for field in SERVED_FIELDS}
        item["id"] = row["url"]
        items.append(item)
    return items


def read_latest_labels(labels_path: Path) -> dict[str, dict]:
    latest: dict[str, dict] = {}
    if not Path(labels_path).exists():
        return latest
    with open(labels_path, encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                entry = json.loads(line)
                latest[entry["url"]] = entry
    return latest


class LabelStore:
    def __init__(self, items: list[dict], labels_path: Path):
        self.items = items
        self.known_urls = {item["url"] for item in items}
        self.labels_path = Path(labels_path)
        self._lock = Lock()

    def append(self, url: str, label: str, note: str) -> dict:
        entry = {
            "url": url,
            "label": label,
            "note": note,
            "saved_at": datetime.now(timezone.utc).isoformat(),
        }
        with self._lock:
            with open(self.labels_path, "a", encoding="utf-8") as handle:
                handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return entry

    def latest(self) -> dict[str, dict]:
        with self._lock:
            return read_latest_labels(self.labels_path)


def validate_submission(raw: bytes, known_urls: set[str]) -> tuple[dict | None, str | None]:
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None, "body is not valid JSON"
    if not isinstance(payload, dict):
        return None, "body must be a JSON object"
    if payload.get("url") not in known_urls:
        return None, "url is not one of the dossier PRs"
    if payload.get("label") not in LABELS:
        return None, "label must be one of: " + ", ".join(LABELS)
    note = payload.get("note", "")
    if note is None:
        note = ""
    if not isinstance(note, str) or len(note) > MAX_NOTE_CHARS:
        return None, f"note must be a string of at most {MAX_NOTE_CHARS} characters"
    return {"url": payload["url"], "label": payload["label"], "note": note}, None


def make_handler(store: LabelStore, page_path: Path, port_getter):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            logger.info("%s " + fmt, self.address_string(), *args)

        def _send(self, status: int, body: bytes, content_type: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, status: int, payload) -> None:
            self._send(status, json.dumps(payload).encode("utf-8"), "application/json; charset=utf-8")

        def do_GET(self):
            path = self.path.split("?", 1)[0]
            if path == "/":
                self._send(200, Path(page_path).read_bytes(), "text/html; charset=utf-8")
            elif path == "/api/items":
                self._json(200, store.items)
            elif path == "/api/labels":
                self._json(200, store.latest())
            else:
                self._json(404, {"error": "not found"})

        def do_POST(self):
            if self.path.split("?", 1)[0] != "/api/labels":
                self._json(404, {"error": "not found"})
                return
            origin = self.headers.get("Origin")
            port = port_getter()
            if origin is not None and origin not in (f"http://127.0.0.1:{port}", f"http://localhost:{port}"):
                self._json(403, {"error": "origin not allowed"})
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                self._json(400, {"error": "Content-Length is not a number"})
                return
            if length < 0:
                self._json(400, {"error": "Content-Length is negative"})
                return
            if length > MAX_BODY_BYTES:
                self._json(413, {"error": f"body over {MAX_BODY_BYTES} bytes"})
                return
            submission, problem = validate_submission(self.rfile.read(length), store.known_urls)
            if problem:
                self._json(400, {"error": problem})
                return
            self._json(200, store.append(**submission))

    return Handler


def create_server(port: int = 8790, dossier_paths=DOSSIER_PATHS, labels_path=LABELS_PATH,
                  page_path=PAGE_PATH) -> ThreadingHTTPServer:
    store = LabelStore(load_items(dossier_paths), labels_path)
    holder: dict = {}
    # port 0 means ephemeral, so the Origin check needs the real port after binding
    server = ThreadingHTTPServer(("127.0.0.1", port), make_handler(store, page_path, lambda: holder["port"]))
    holder["port"] = server.server_address[1]
    server.store = store
    return server


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8790)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    server = create_server(args.port)
    logger.info("labelling %d PRs at http://127.0.0.1:%d/ ; saving to %s",
                len(server.store.items), server.server_address[1], LABELS_PATH)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("stopped")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
