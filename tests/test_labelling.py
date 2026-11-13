from __future__ import annotations

import importlib.util
import json
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

STUDY = Path(__file__).resolve().parent.parent / "study"


def load_study_module(name: str):
    spec = importlib.util.spec_from_file_location(name, STUDY / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


label_server = load_study_module("label_server")
agreement = load_study_module("agreement")


@pytest.fixture
def served(tmp_path):
    labels_path = tmp_path / "labels-zaid.jsonl"
    server = label_server.create_server(0, labels_path=labels_path)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_address[1]
    yield f"http://127.0.0.1:{port}", port, labels_path
    server.shutdown()
    server.server_close()
    thread.join(timeout=5)


def fetch(url: str, payload=None, raw: bytes | None = None, headers: dict | None = None):
    body = raw if raw is not None else (json.dumps(payload).encode() if payload is not None else None)
    request = urllib.request.Request(url, data=body, headers=headers or {})
    if body is not None:
        request.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(request) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as failure:
        return failure.code, failure.read()


def get_json(url: str):
    status, body = fetch(url)
    assert status == 200
    return json.loads(body)


def test_items_are_62_stable_and_free_of_first_rater_data(served):
    base, _, _ = served
    first = get_json(base + "/api/items")
    second = get_json(base + "/api/items")
    assert len(first) == 62
    assert [item["id"] for item in first] == [item["id"] for item in second]
    assert len({item["id"] for item in first}) == 62
    assert all("agent" not in item for item in first)
    assert all(set(item) == {"id", *label_server.SERVED_FIELDS} for item in first)

    served_text = json.dumps(first)
    for name in ("labels-a.jsonl", "labels-b.jsonl"):
        for line in (STUDY / "results" / name).read_text(encoding="utf-8").splitlines():
            reason = json.loads(line)["reason"]
            assert reason not in served_text


def test_post_saves_and_relabel_returns_latest(served):
    base, _, labels_path = served
    url = get_json(base + "/api/items")[0]["url"]
    assert get_json(base + "/api/labels") == {}

    status, _ = fetch(base + "/api/labels", {"url": url, "label": "intended", "note": "first"})
    assert status == 200
    assert get_json(base + "/api/labels")[url]["label"] == "intended"

    status, _ = fetch(base + "/api/labels", {"url": url, "label": "laundered"})
    assert status == 200
    latest = get_json(base + "/api/labels")[url]
    assert latest["label"] == "laundered"
    assert latest["note"] == ""
    assert len(labels_path.read_text(encoding="utf-8").splitlines()) == 2


def test_unknown_url_is_rejected_naming_url(served):
    base, _, labels_path = served
    status, body = fetch(base + "/api/labels", {"url": "https://example.com/x", "label": "intended"})
    assert status == 400
    assert "url" in json.loads(body)["error"]
    assert not labels_path.exists()


def test_bad_label_is_rejected_naming_label(served):
    base, _, _ = served
    url = get_json(base + "/api/items")[0]["url"]
    status, body = fetch(base + "/api/labels", {"url": url, "label": "maybe"})
    assert status == 400
    assert "label" in json.loads(body)["error"]


def test_oversized_body_is_413(served):
    base, _, labels_path = served
    url = get_json(base + "/api/items")[0]["url"]
    status, _ = fetch(base + "/api/labels", {"url": url, "label": "intended", "note": "x" * 5000})
    assert status == 413
    assert not labels_path.exists()


def test_foreign_origin_is_403_and_local_origin_is_accepted(served):
    base, port, _ = served
    url = get_json(base + "/api/items")[0]["url"]
    payload = {"url": url, "label": "unclear"}
    status, _ = fetch(base + "/api/labels", payload, headers={"Origin": "http://evil.example"})
    assert status == 403
    status, _ = fetch(base + "/api/labels", payload, headers={"Origin": f"http://localhost:{port}"})
    assert status == 200


def test_page_is_served_and_never_uses_inner_html(served):
    base, _, _ = served
    status, body = fetch(base + "/")
    assert status == 200
    assert "innerHTML" not in body.decode("utf-8")


def write_labels(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


def test_agreement_matches_hand_computed_values(tmp_path, capsys):
    # Zaid vs first rater over 10 PRs:
    #   intended/intended 4, laundered/laundered 2, unclear/unclear 1,
    #   intended/laundered 1, laundered/intended 1, unclear/intended 1
    # observed = 7/10 = 0.7
    # Zaid marginals: intended 5, laundered 3, unclear 2; rater: intended 6, laundered 3, unclear 1
    # expected = .5*.6 + .3*.3 + .2*.1 = .30 + .09 + .02 = .41
    # kappa = (.7 - .41) / (1 - .41) = .29 / .59 = 0.4915
    pairs = (
        [("intended", "intended")] * 4 + [("laundered", "laundered")] * 2 + [("unclear", "unclear")]
        + [("intended", "laundered"), ("laundered", "intended"), ("unclear", "intended")]
    )
    urls = [f"https://github.com/o/r/pull/{n}" for n in range(len(pairs))]
    write_labels(tmp_path / "labels-zaid.jsonl", [
        {"url": url, "label": mine, "note": "n"} for url, (mine, _) in zip(urls, pairs)
    ])
    write_labels(tmp_path / "labels-a.jsonl", [
        {"url": url, "label": theirs, "reason": "r"} for url, (_, theirs) in zip(urls[:6], pairs[:6])
    ])
    write_labels(tmp_path / "labels-b.jsonl", [
        {"url": url, "label": theirs, "reason": "r"} for url, (_, theirs) in zip(urls[6:], pairs[6:])
    ])
    assert agreement.main(tmp_path) == 0
    out = capsys.readouterr().out
    assert "raw agreement: 7/10 (70.0%)" in out
    assert "Cohen's kappa: 0.492" in out
    assert out.count("first rater:") == 3


def test_agreement_reports_first_pass_labels_separately(tmp_path, capsys):
    url = "https://github.com/o/r/pull/1"
    other = "https://github.com/o/r/pull/2"
    write_labels(tmp_path / "labels-zaid.jsonl", [
        {"url": url, "label": "unclear", "note": ""}, {"url": other, "label": "intended", "note": ""},
    ])
    write_labels(tmp_path / "labels-a.jsonl", [
        {"url": url, "label": "laundered", "reason": "r", "first_label": "unclear", "first_reason": "f"},
        {"url": other, "label": "intended", "reason": "r"},
    ])
    write_labels(tmp_path / "labels-b.jsonl", [])
    agreement.main(tmp_path)
    out = capsys.readouterr().out
    final_part, first_pass_part = out.split("first-pass labels")
    assert "raw agreement: 1/2" in final_part
    assert "raw agreement: 2/2" in first_pass_part


def test_agreement_all_same_label_says_kappa_undefined(tmp_path, capsys):
    urls = [f"https://github.com/o/r/pull/{n}" for n in range(3)]
    write_labels(tmp_path / "labels-zaid.jsonl", [{"url": u, "label": "intended", "note": ""} for u in urls])
    write_labels(tmp_path / "labels-a.jsonl", [{"url": u, "label": "intended", "reason": "r"} for u in urls])
    write_labels(tmp_path / "labels-b.jsonl", [])
    assert agreement.main(tmp_path) == 0
    out = capsys.readouterr().out
    assert "undefined" in out
    assert "raw agreement: 3/3 (100.0%)" in out


def test_agreement_missing_zaid_file_exits_2(tmp_path, capsys):
    assert agreement.main(tmp_path) == 2
    assert "labels-zaid.jsonl" in capsys.readouterr().err
