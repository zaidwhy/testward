from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient

from testward.server.app import REPORT_BYTES_LIMIT, Settings, create_app

BASE_URL = "http://testserver"
FINGERPRINT = "ab" * 16
PASSWORD = "correct horse battery"


def report(fingerprint: str = FINGERPRINT, verdict: str = "needs_signoff", **context) -> dict:
    return {
        "schema_version": 1,
        "base": "origin/main",
        "head": "a" * 40,
        "merge_base": "b" * 40,
        "command": "pytest {file}",
        "config_source": "merge base",
        "support_changed": [],
        "context": context,
        "files": [
            {
                "path": "tests/test_total.py",
                "status": "modified",
                "new_path": None,
                "fingerprint": fingerprint,
                "verdict": verdict,
                "head_exit": 1,
                "control_exit": 0,
                "seconds": 0.4,
                "note": "",
                "log_tail": "AssertionError: <script>alert(1)</script>",
            }
        ],
    }


@pytest.fixture
def app(tmp_path):
    return create_app(Settings(database=tmp_path / "ledger.sqlite3", base_url=BASE_URL))


def browser(app) -> TestClient:
    return TestClient(app, follow_redirects=False)


def csrf(page_html: str) -> str:
    return re.search(r'name="csrf_token" value="([^"]+)"', page_html).group(1)


def account(app, email: str) -> tuple[TestClient, str]:
    client = browser(app)
    created = client.post("/signup", data={"email": email, "password": PASSWORD})
    assert created.status_code == 303 and created.headers["location"] == "/app"
    return client, csrf(client.get("/app").text)


def project(client: TestClient, token: str, name: str = "acme/shop") -> tuple[int, str]:
    created = client.post("/app/projects", data={"name": name, "csrf_token": token})
    assert created.status_code == 200
    project_token = re.search(r"<pre>(tw_[\w-]+)</pre>", created.text).group(1)
    project_id = int(re.search(r"/app/projects/(\d+)/", created.text).group(1))
    return project_id, project_token


def send(app, project_token: str, body: dict):
    return browser(app).post(
        "/api/v1/reports", json=body, headers={"Authorization": f"Bearer {project_token}"}
    )


def test_health_reports_ok(app):
    assert browser(app).get("/health").json() == {"status": "ok"}


def test_public_pages_render_without_an_account(app):
    client = browser(app)
    assert "change the tests to pass" in client.get("/").text
    assert "TESTWARD_TOKEN" in client.get("/docs").text
    assert client.get("/app").headers["location"] == "/login"


def test_signup_refuses_short_password_and_duplicate_email(app):
    client = browser(app)
    short = client.post("/signup", data={"email": "a@example.test", "password": "short"})
    assert short.status_code == 400 and "10 to 200 characters" in short.text
    account(app, "a@example.test")
    again = client.post("/signup", data={"email": "A@Example.test", "password": PASSWORD})
    assert again.status_code == 409 and "already has an account" in again.text


def test_login_locks_after_five_wrong_passwords(app):
    account(app, "a@example.test")
    client = browser(app)
    for _ in range(5):
        wrong = client.post("/login", data={"email": "a@example.test", "password": "nope-nope-nope"})
        assert wrong.status_code == 401
    locked = client.post("/login", data={"email": "a@example.test", "password": PASSWORD})
    assert locked.status_code == 429 and "wait 15 minutes" in locked.text


def test_logout_ends_the_session(app):
    client, token = account(app, "a@example.test")
    assert client.post("/logout", data={"csrf_token": token}).status_code == 303
    assert client.get("/app").headers["location"] == "/login"


def test_forms_need_the_session_csrf_token_and_same_origin(app):
    client, token = account(app, "a@example.test")
    forged = client.post("/app/projects", data={"name": "x", "csrf_token": "guess"})
    assert forged.status_code == 403
    cross_site = client.post(
        "/app/projects",
        data={"name": "x", "csrf_token": token},
        headers={"Origin": "https://evil.example"},
    )
    assert cross_site.status_code == 403
    assert "No projects yet" in client.get("/app").text


def test_report_needs_a_known_project_token(app):
    assert browser(app).post("/api/v1/reports", json=report()).status_code == 401
    assert send(app, "tw_not-a-real-token", report()).status_code == 401


def test_oversized_and_malformed_reports_are_refused_with_the_field_named(app):
    client, token = account(app, "a@example.test")
    _, project_token = project(client, token)

    huge = report()
    huge["files"] = [dict(huge["files"][0], path=f"tests/test_{i}.py", log_tail="x" * 4000) for i in range(200)]
    assert len(str(huge)) > REPORT_BYTES_LIMIT
    assert send(app, project_token, huge).status_code == 413

    bad_link = send(app, project_token, report(change_url="javascript:alert(1)"))
    assert bad_link.status_code == 422 and "context.change_url" in bad_link.json()["detail"]

    bad_print = send(app, project_token, report(fingerprint="zz"))
    assert bad_print.status_code == 422 and "files.0.fingerprint" in bad_print.json()["detail"]


def test_signoff_flow_from_report_to_passing_rerun(app):
    client, token = account(app, "a@example.test")
    project_id, project_token = project(client, token)

    first = send(app, project_token, report(change_url="https://github.com/acme/shop/pull/7"))
    assert first.status_code == 200 and first.json()["signed_off"] == []

    page = client.get(f"/app/projects/{project_id}").text
    assert "Waiting for sign-off (1)" in page
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in page and "<script>alert(1)" not in page
    assert 'href="https://github.com/acme/shop/pull/7"' in page

    too_short = client.post(
        f"/app/projects/{project_id}/signoffs",
        data={"fingerprint": FINGERPRINT, "reason": "ok", "csrf_token": token},
    )
    assert too_short.status_code == 400 and "10 to 500" in too_short.text

    signed = client.post(
        f"/app/projects/{project_id}/signoffs",
        data={
            "fingerprint": FINGERPRINT,
            "reason": "Totals now exclude the shipping line by design",
            "csrf_token": token,
        },
    )
    assert signed.status_code == 303
    after = client.get(f"/app/projects/{project_id}").text
    assert "Waiting for sign-off (0)" in after and "exclude the shipping line" in after

    assert send(app, project_token, report()).json()["signed_off"] == [FINGERPRINT]
    edited_again = "cd" * 16
    assert send(app, project_token, report(fingerprint=edited_again)).json()["signed_off"] == []

    signoff_id = re.search(r"/signoffs/(\d+)/revoke", after).group(1)
    client.post(
        f"/app/projects/{project_id}/signoffs/{signoff_id}/revoke", data={"csrf_token": token}
    )
    assert send(app, project_token, report()).json()["signed_off"] == []


def test_signoff_is_refused_for_an_edit_no_report_flagged(app):
    client, token = account(app, "a@example.test")
    project_id, project_token = project(client, token)
    send(app, project_token, report(verdict="held"))
    refused = client.post(
        f"/app/projects/{project_id}/signoffs",
        data={"fingerprint": FINGERPRINT, "reason": "pre-approving just in case", "csrf_token": token},
    )
    assert refused.status_code == 404


def test_one_account_cannot_see_or_sign_another_accounts_project(app):
    owner_client, owner_token = account(app, "owner@example.test")
    project_id, project_token = project(owner_client, owner_token)
    send(app, project_token, report())

    other_client, other_token = account(app, "other@example.test")
    assert other_client.get(f"/app/projects/{project_id}").status_code == 404
    stolen = other_client.post(
        f"/app/projects/{project_id}/signoffs",
        data={"fingerprint": FINGERPRINT, "reason": "signing someone else's edit", "csrf_token": other_token},
    )
    assert stolen.status_code == 404
    rotated = other_client.post(f"/app/projects/{project_id}/token", data={"csrf_token": other_token})
    assert rotated.status_code == 404
    assert send(app, project_token, report()).json()["signed_off"] == []


def test_replacing_the_token_stops_the_old_one(app):
    client, token = account(app, "a@example.test")
    project_id, old = project(client, token)
    page = client.post(f"/app/projects/{project_id}/token", data={"csrf_token": token}).text
    new = re.search(r"<pre>(tw_[\w-]+)</pre>", page).group(1)
    assert send(app, old, report()).status_code == 401
    assert send(app, new, report()).status_code == 200
