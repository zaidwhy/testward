"""The sign-off ledger: receives replay reports from CI and records which test edits a
human accepted. The sign-off lives here, outside the repository, because anything inside
the repository can be written by the same change that weakened the test."""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from . import credentials
from .ledger import SESSION_SECONDS, Ledger

log = logging.getLogger("testward.server")

SESSION_COOKIE = "tw_session"
REPORT_BYTES_LIMIT = 512 * 1024
FORM_BYTES_LIMIT = 16 * 1024
EMAIL_SHAPE = re.compile(r"[^@\s]{1,64}@[^@\s]{1,185}\.[^@\s]{2,}")
REASON_MIN, REASON_MAX = 10, 500
PROJECT_NAME_MAX = 80
COMMIT = r"^[0-9a-f]{40,64}$"


@dataclass(frozen=True)
class Settings:
    database: Path
    base_url: str
    allow_signup: bool = True

    @classmethod
    def from_environment(cls) -> "Settings":
        return cls(
            database=Path(os.environ.get("TESTWARD_DB", "data/testward.sqlite3")),
            base_url=os.environ.get("TESTWARD_BASE_URL", "http://127.0.0.1:8000").rstrip("/"),
            allow_signup=os.environ.get("TESTWARD_ALLOW_SIGNUP", "1") == "1",
        )

    @property
    def secure_cookies(self) -> bool:
        return self.base_url.startswith("https://")


class ReportedFile(BaseModel):
    model_config = ConfigDict(extra="ignore")
    path: str = Field(min_length=1, max_length=500)
    status: Literal["modified", "deleted", "renamed"]
    new_path: str | None = Field(default=None, max_length=500)
    fingerprint: str = Field(pattern=r"^[0-9a-f]{32}$")
    verdict: Literal["held", "needs_signoff", "inconclusive"]
    head_exit: int | None = None
    control_exit: int | None = None
    seconds: float = Field(default=0, ge=0, le=1_000_000)
    note: str = Field(default="", max_length=300)
    log_tail: str = Field(default="", max_length=4000)


class ReportContext(BaseModel):
    model_config = ConfigDict(extra="ignore")
    repository: str = Field(default="", max_length=200)
    change_url: str = Field(default="", max_length=500)

    @field_validator("change_url")
    @classmethod
    def only_web_links(cls, value: str) -> str:
        # Rendered as a link in the dashboard, so anything but http(s) is refused.
        if value and urlsplit(value).scheme not in ("http", "https"):
            raise ValueError("change_url must be an http or https URL")
        return value


class IncomingReport(BaseModel):
    model_config = ConfigDict(extra="ignore")
    schema_version: Literal[1]
    base: str = Field(max_length=200)
    head: str = Field(pattern=COMMIT)
    merge_base: str = Field(pattern=COMMIT)
    command: str | None = Field(default=None, max_length=500)
    config_source: str = Field(default="", max_length=40)
    support_changed: list[str] = Field(default_factory=list, max_length=200)
    context: ReportContext = Field(default_factory=ReportContext)
    files: list[ReportedFile] = Field(max_length=200)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_environment()
    ledger = Ledger(settings.database)
    ledger.create_tables()
    pages = Jinja2Templates(directory=Path(__file__).parent / "templates")
    pages.env.filters["when"] = lambda ts: datetime.fromtimestamp(ts, timezone.utc).strftime(
        "%Y-%m-%d %H:%M UTC"
    )
    app = FastAPI(title="testward", docs_url=None, redoc_url=None, openapi_url=None)

    def page(request: Request, name: str, status: int = 200, **values: object) -> Response:
        return pages.TemplateResponse(
            request,
            name,
            {"session": signed_in(request), "base_url": settings.base_url, **values},
            status_code=status,
        )

    def signed_in(request: Request):
        token = request.cookies.get(SESSION_COOKIE)
        return ledger.session(token) if token else None

    def owner(request: Request, csrf_token: str | None = None):
        """The signed-in account. State-changing forms also pass their CSRF token."""
        session = signed_in(request)
        if session is None:
            raise HTTPException(status_code=303, headers={"Location": "/login"})
        if csrf_token is not None and csrf_token != session["csrf_token"]:
            raise HTTPException(status_code=403, detail="form expired; reload the page and retry")
        return session

    def owned_project(session, project_id: int):
        project = ledger.project(session["account_id"], project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="no such project")
        return project

    def start_session(account_id: int) -> Response:
        response = RedirectResponse("/app", status_code=303)
        response.set_cookie(
            SESSION_COOKIE,
            ledger.open_session(account_id),
            max_age=SESSION_SECONDS,
            httponly=True,
            samesite="lax",
            secure=settings.secure_cookies,
        )
        return response

    @app.middleware("http")
    async def guard_browser_posts(request: Request, call_next):
        if request.method == "POST" and not request.url.path.startswith("/api/"):
            origin = request.headers.get("origin")
            if origin and origin != settings.base_url:
                return JSONResponse({"detail": "cross-site form post refused"}, status_code=403)
            declared = request.headers.get("content-length", "0")
            if not declared.isdigit() or int(declared) > FORM_BYTES_LIMIT:
                return JSONResponse(
                    {"detail": f"form body over the {FORM_BYTES_LIMIT} byte limit"}, status_code=413
                )
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["Content-Security-Policy"] = (
            "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; base-uri 'none'"
        )
        return response

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok" if ledger.is_reachable() else "database unreachable"}

    @app.get("/", response_class=HTMLResponse)
    def landing(request: Request):
        return page(request, "landing.html")

    @app.get("/docs", response_class=HTMLResponse)
    def docs(request: Request):
        return page(request, "docs.html")

    @app.get("/signup", response_class=HTMLResponse)
    def signup_form(request: Request):
        return page(request, "account.html", action="signup", open=settings.allow_signup)

    @app.post("/signup")
    def signup(request: Request, email: str = Form(max_length=254), password: str = Form()):
        def refuse(problem: str, status: int = 400):
            return page(request, "account.html", status, action="signup", open=True, problem=problem)

        if not settings.allow_signup:
            raise HTTPException(status_code=403, detail="sign-up is closed on this server")
        email = email.strip().lower()
        if not EMAIL_SHAPE.fullmatch(email):
            return refuse("email: that does not look like an email address")
        low, high = credentials.PASSWORD_MIN, credentials.PASSWORD_MAX
        if not low <= len(password) <= high:
            return refuse(f"password: must be {low} to {high} characters")
        account_id = ledger.create_account(email, password)
        if account_id is None:
            return refuse("email: that address already has an account", 409)
        return start_session(account_id)

    @app.get("/login", response_class=HTMLResponse)
    def login_form(request: Request):
        return page(request, "account.html", action="login", open=True)

    @app.post("/login")
    def login(
        request: Request, email: str = Form(max_length=254), password: str = Form(max_length=200)
    ):
        def refuse(problem: str, status: int):
            return page(request, "account.html", status, action="login", open=True, problem=problem)

        email = email.strip().lower()
        if ledger.login_is_locked(email):
            return refuse("too many failed attempts for this email; wait 15 minutes", 429)
        account_id = ledger.check_login(email, password)
        if account_id is None:
            return refuse("email or password is wrong", 401)
        return start_session(account_id)

    @app.post("/logout")
    def logout(request: Request, csrf_token: str = Form()):
        owner(request, csrf_token)
        ledger.close_session(request.cookies[SESSION_COOKIE])
        response = RedirectResponse("/", status_code=303)
        response.delete_cookie(SESSION_COOKIE)
        return response

    @app.get("/app", response_class=HTMLResponse)
    def projects(request: Request):
        session = owner(request)
        return page(request, "projects.html", projects=ledger.projects(session["account_id"]))

    @app.post("/app/projects", response_class=HTMLResponse)
    def create_project(request: Request, name: str = Form(), csrf_token: str = Form()):
        session = owner(request, csrf_token)
        name = name.strip()
        if not 1 <= len(name) <= PROJECT_NAME_MAX:
            raise HTTPException(400, f"name: must be 1 to {PROJECT_NAME_MAX} characters")
        created = ledger.create_project(session["account_id"], name)
        if created is None:
            raise HTTPException(400, "project limit reached for this account")
        project_id, token = created
        return project_page(request, session, project_id, new_token=token)

    @app.get("/app/projects/{project_id}", response_class=HTMLResponse)
    def show_project(request: Request, project_id: int):
        return project_page(request, owner(request), project_id)

    @app.post("/app/projects/{project_id}/token", response_class=HTMLResponse)
    def rotate_token(request: Request, project_id: int, csrf_token: str = Form()):
        session = owner(request, csrf_token)
        token = ledger.rotate_project_token(session["account_id"], project_id)
        if token is None:
            raise HTTPException(404, "no such project")
        return project_page(request, session, project_id, new_token=token)

    @app.post("/app/projects/{project_id}/signoffs")
    def sign_off(
        request: Request,
        project_id: int,
        fingerprint: str = Form(pattern=r"^[0-9a-f]{32}$"),
        reason: str = Form(),
        csrf_token: str = Form(),
    ):
        session = owner(request, csrf_token)
        owned_project(session, project_id)
        reason = reason.strip()
        if not REASON_MIN <= len(reason) <= REASON_MAX:
            raise HTTPException(400, f"reason: must be {REASON_MIN} to {REASON_MAX} characters")
        path = ledger.fingerprint_was_reported(project_id, fingerprint)
        if path is None:
            raise HTTPException(404, "no report in this project flagged that test edit")
        ledger.sign_off(project_id, fingerprint, path, reason, session["email"])
        log.info("project %s: account %s signed off %s", project_id, session["account_id"], path)
        return RedirectResponse(f"/app/projects/{project_id}", status_code=303)

    @app.post("/app/projects/{project_id}/signoffs/{signoff_id}/revoke")
    def revoke(request: Request, project_id: int, signoff_id: int, csrf_token: str = Form()):
        session = owner(request, csrf_token)
        owned_project(session, project_id)
        ledger.revoke_signoff(project_id, signoff_id)
        return RedirectResponse(f"/app/projects/{project_id}", status_code=303)

    def project_page(request: Request, session, project_id: int, new_token: str | None = None):
        project = owned_project(session, project_id)
        reports = ledger.recent_reports(project_id)
        signed = ledger.signed_fingerprints(project_id)
        waiting: dict[str, dict] = {}
        for report in reports:
            for entry in report["files"]:
                key = entry["fingerprint"]
                if entry["verdict"] == "needs_signoff" and key not in signed and key not in waiting:
                    waiting[key] = {**entry, "report": report}
        return page(
            request,
            "project.html",
            project=project,
            reports=reports,
            waiting=list(waiting.values()),
            signoffs=ledger.signoffs(project_id),
            new_token=new_token,
        )

    @app.post("/api/v1/reports")
    async def receive_report(request: Request):
        scheme, _, token = request.headers.get("authorization", "").partition(" ")
        known = scheme.lower() == "bearer" and token
        project_id = ledger.project_for_token(token) if known else None
        if project_id is None:
            raise HTTPException(401, "missing or unknown project token")

        body = bytearray()
        async for chunk in request.stream():
            body += chunk
            if len(body) > REPORT_BYTES_LIMIT:
                raise HTTPException(413, f"report over the {REPORT_BYTES_LIMIT} byte limit")
        try:
            report = IncomingReport.model_validate_json(bytes(body))
        except ValidationError as invalid:
            first = invalid.errors()[0]
            field_name = ".".join(str(part) for part in first["loc"])
            raise HTTPException(422, field_name + ": " + first["msg"])

        report_id = ledger.record_report(project_id, report.model_dump())
        if report_id is None:
            raise HTTPException(429, "this project sent more than 120 reports in the last hour")
        signed = ledger.signed_fingerprints(project_id)
        return {
            "report_url": f"{settings.base_url}/app/projects/{project_id}",
            "signed_off": sorted(f.fingerprint for f in report.files if f.fingerprint in signed),
        }

    return app
