"""The web pages and what each address does.

=================  ==============================================================
Address            What it does
=================  ==============================================================
``/``              the home page
``/setup``         the first visitor sets the password (only while none is set)
``/login``         log in; also says how to reset a forgotten password
``/logout``        log out (a button on every page)
``/static/...``    the style sheet and htmx (a small JavaScript file that updates
                   one part of a page without loading the whole page again)
=================  ==============================================================

Every other page needs a log-in, unless ``login = false`` in ``[web]``. Forms are only
accepted when they are sent from a page of the web interface itself, so another website
can't send them in the visitor's name.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.concurrency import run_in_threadpool

from .. import __version__
from .auth import COOKIE_SECONDS, Auth, new_cookie
from .password import PasswordError, password_problem

COOKIE = "paperpi_login"
_HERE = Path(__file__).parent
#: Pages that work without a log-in (and everything in ``/static/``).
_OPEN = ("/setup", "/login")


def create_app(auth: Auth) -> FastAPI:
    """The web interface, using ``auth`` for the password and log-in."""
    app = FastAPI(title="PaperPi", docs_url=None, redoc_url=None, openapi_url=None)
    app.mount("/static", StaticFiles(directory=_HERE / "static"), name="static")
    templates = Jinja2Templates(directory=_HERE / "templates")
    templates.env.globals.update(version=__version__, auth=auth)

    def page(request: Request, name: str, status: int = 200, **values) -> HTMLResponse:
        return templates.TemplateResponse(request, name, values, status_code=status)

    def logged_in(request: Request, stored: str) -> RedirectResponse:
        response = RedirectResponse("/", status_code=303)
        response.set_cookie(
            COOKIE,
            new_cookie(stored),
            max_age=COOKIE_SECONDS,
            httponly=True,
            samesite="strict",
        )
        return response

    @app.middleware("http")
    async def check(request: Request, call_next: Callable[[Request], Awaitable[Response]]):
        if request.method not in ("GET", "HEAD") and not _same_site(request):
            return Response("Forms are only accepted from PaperPi's own pages.", 403)
        path = request.url.path
        if auth.login and path not in _OPEN and not path.startswith("/static/"):
            if auth.password_hash is None:
                return RedirectResponse("/setup", status_code=303)
            if not auth.cookie_ok(request.cookies.get(COOKIE)):
                return RedirectResponse("/login", status_code=303)
        response = await call_next(request)
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; frame-ancestors 'none'; form-action 'self'"
        )
        response.headers["Referrer-Policy"] = "same-origin"
        if not path.startswith("/static/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/", response_class=HTMLResponse)
    def home(request: Request):
        return page(request, "home.html")

    @app.get("/setup", response_class=HTMLResponse)
    def setup_page(request: Request):
        if not auth.login or auth.password_hash is not None:
            return RedirectResponse("/", status_code=303)
        return page(request, "setup.html")

    @app.post("/setup", response_class=HTMLResponse)
    async def setup(request: Request):
        if not auth.login:
            return RedirectResponse("/", status_code=303)
        form = await request.form()
        password, again = str(form.get("password", "")), str(form.get("again", ""))
        problem = password_problem(password, again)
        if problem is None:
            try:
                # Scrambling takes a moment; other pages are served meanwhile.
                stored = await run_in_threadpool(auth.set_first_password, password)
            except PasswordError as error:
                problem = str(error)
            else:
                return logged_in(request, stored)
        return page(request, "setup.html", 400, problem=problem)

    @app.get("/login", response_class=HTMLResponse)
    def login_page(request: Request):
        if not auth.login:
            return RedirectResponse("/", status_code=303)
        if auth.password_hash is None:
            return RedirectResponse("/setup", status_code=303)
        return page(request, "login.html")

    @app.post("/login", response_class=HTMLResponse)
    async def login(request: Request):
        if not auth.login:
            return RedirectResponse("/", status_code=303)
        form = await request.form()
        stored = auth.password_hash
        if stored is None:
            return RedirectResponse("/setup", status_code=303)
        if await run_in_threadpool(auth.check, str(form.get("password", ""))):
            return logged_in(request, stored)
        return page(request, "login.html", 401, problem="Wrong password.")

    @app.post("/logout")
    def logout():
        response = RedirectResponse("/login", status_code=303)
        response.delete_cookie(COOKIE, httponly=True, samesite="strict")
        return response

    return app


def _same_site(request: Request) -> bool:
    """False for a form sent from another website (checked with the headers browsers add)."""
    if request.headers.get("sec-fetch-site", "same-origin") not in ("same-origin", "none"):
        return False
    origin = request.headers.get("origin")
    if origin is None:
        return True
    return urlsplit(origin).netloc == request.headers.get("host")
