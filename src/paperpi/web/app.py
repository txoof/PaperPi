"""The web pages and what each address does.

=================  ==============================================================
Address            What it does
=================  ==============================================================
``/``              the home page
``/setup``         the first visitor sets the password (only while none is set)
``/login``         log in; also says how to reset a forgotten password
``/logout``        log out (a button on every page)
``/plugins``       Active Plugins: the plugins in the config file; switch on or off, move
                   up or down, remove, settings (``/plugins/<n>/...?id=<id>``, n = place
                   in the file, counted from 0, and the plugin's id to check it is
                   still there)
``/library``       Plugin Library: every plugin type; ``/library/<type>`` adds one and
                   opens its settings
``/static/...``    the style sheet and htmx (a small JavaScript file that updates
                   one part of a page without loading the whole page again)
=================  ==============================================================

Every other page needs a log-in, unless ``login = false`` in ``[web]``. Forms are only
accepted when they are sent from a page of the web interface itself, so another website
can't send them in the visitor's name. And PaperPi only answers when it is opened by an IP
address or ``localhost``: a website could otherwise point a name of its own at the Pi
("DNS rebinding") and then use the pages as if they were its own.
"""

from __future__ import annotations

import ipaddress
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Annotated
from urllib.parse import urlencode, urlsplit

from fastapi import FastAPI, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.concurrency import run_in_threadpool

from .. import __version__
from ..config import folder_name
from .auth import COOKIE_SECONDS, Auth, new_cookie
from .config_file import EditError
from .forms import Read, fields
from .helpers import helper_html
from .password import PasswordError, password_problem
from .plugins import FormErrors, PluginEditor, library, library_item

COOKIE = "paperpi_login"
_HERE = Path(__file__).parent
#: Pages that work without a log-in (and everything in ``/static/``).
_OPEN = ("/setup", "/login")
#: A plugin's ID, sent as ``id`` in a form or in the address.
_FormId = Annotated[str, Form(alias="id")]
_QueryId = Annotated[str, Query(alias="id")]


def create_app(auth: Auth, editor: PluginEditor | None = None) -> FastAPI:
    """The web interface, using ``auth`` for the password and log-in and ``editor`` to
    change the plugins in the config file."""
    editor = editor or PluginEditor(auth.config_file)
    app = FastAPI(title="PaperPi", docs_url=None, redoc_url=None, openapi_url=None)
    app.mount("/static", StaticFiles(directory=_HERE / "static"), name="static")
    templates = Jinja2Templates(directory=_HERE / "templates")
    templates.env.globals.update(version=__version__, auth=auth, helper_html=helper_html)
    templates.env.filters["number"] = _number
    templates.env.filters["sentence"] = lambda text: text[:1].upper() + text[1:]

    def page(request: Request, template: str, status: int = 200, **values) -> HTMLResponse:
        return templates.TemplateResponse(request, template, values, status_code=status)

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

    async def refused_or_page(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        if not _known_host(request.headers.get("host", "")):
            return page(request, "by_address.html", 400, address=_own_address(request))
        if request.method not in ("GET", "HEAD") and not _same_site(request):
            return Response("Forms are only accepted from PaperPi's own pages.", 403)
        path = request.url.path
        if auth.login and path not in _OPEN and not path.startswith("/static/"):
            if auth.password_hash is None:
                return RedirectResponse("/setup", status_code=303)
            if not auth.cookie_ok(request.cookies.get(COOKIE)):
                return RedirectResponse("/login", status_code=303)
        return await call_next(request)

    @app.middleware("http")
    async def check(request: Request, call_next: Callable[[Request], Awaitable[Response]]):
        response = await refused_or_page(request, call_next)
        path = request.url.path
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; frame-ancestors 'none'; form-action 'self'; base-uri 'none'"
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
        if await run_in_threadpool(auth.check, str(form.get("password", "")), stored):
            return logged_in(request, stored)
        return page(request, "login.html", 401, problem="Wrong password.")

    def plugin_list(request: Request, status: int = 200, problem: str | None = None):
        try:
            found = editor.plugin_list()
        except EditError as error:
            rows, problems = [], [str(error)]
            status = 500 if status == 200 else status
        else:
            rows, problems = found.rows, found.problems
        done = request.query_params.get("done")
        # The name is looked up by the ID in the address: a link can't put other text on
        # the page.
        plugin_id = request.query_params.get("id")
        name = next((row.name for row in rows if plugin_id and row.id == plugin_id), None)
        return page(
            request,
            "plugins.html",
            status,
            rows=rows,
            problems=[p for p in dict.fromkeys(problems) if p != problem],
            problem=problem,
            done=done if done in ("saved", "added", "removed") else None,
            name=name,
            hand_edits=request.query_params.get("hand") == "1",
            config_file=auth.config_file,
        )

    def saved(done: str, hand_edits: bool, plugin_id: str = "") -> RedirectResponse:
        values = {"done": done} | ({"id": plugin_id} if plugin_id else {})
        query = urlencode(values | ({"hand": "1"} if hand_edits else {}))
        return RedirectResponse(f"/plugins?{query}", status_code=303)

    @app.get("/plugins", response_class=HTMLResponse)
    def plugins_page(request: Request):
        return plugin_list(request)

    @app.post("/plugins/{index}/move", response_class=HTMLResponse)
    def move(request: Request, index: int, plugin_id: _FormId = "", step: str = Form("")):
        if step not in ("up", "down"):
            return plugin_list(request, 400, "Choose up or down.")
        try:
            hand_edits = editor.move(index, plugin_id, -1 if step == "up" else 1)
        except EditError as error:
            return plugin_list(request, 409, str(error))
        return saved("saved", hand_edits)

    @app.post("/plugins/{index}/enabled", response_class=HTMLResponse)
    def switch(request: Request, index: int, plugin_id: _FormId = "", on: str = Form("")):
        try:
            hand_edits = editor.set_enabled(index, plugin_id, on == "1")
        except EditError as error:
            return plugin_list(request, 409, str(error))
        return saved("saved", hand_edits)

    @app.get("/plugins/{index}/remove", response_class=HTMLResponse)
    def remove_page(request: Request, index: int, plugin_id: _QueryId = ""):
        try:
            row = editor.row(index, plugin_id)
        except EditError as error:
            return plugin_list(request, 409, str(error))
        return page(request, "remove.html", row=row)

    @app.post("/plugins/{index}/remove", response_class=HTMLResponse)
    def remove(request: Request, index: int, plugin_id: _FormId = ""):
        try:
            hand_edits = editor.remove(index, plugin_id)
        except EditError as error:
            return plugin_list(request, 409, str(error))
        return saved("removed", hand_edits)

    def settings_page(
        request: Request,
        index: int,
        plugin_id: str,
        status: int = 200,
        found: Read | None = None,
    ) -> HTMLResponse:
        try:
            plugin, block = editor.settings(index, plugin_id)
            row = editor.row(index, plugin_id)
        except EditError as error:
            return plugin_list(request, 409, str(error))
        errors = found.errors if found else {}
        shown = fields(plugin, block, found.sent if found else None, errors)
        groups = {g: [f for f in shown if f.group == g] for g in ("name", "own", "common", "more")}
        # Errors that belong to no field on the page (a broken id, ...).
        other = [m for k, m in errors.items() if k not in {f.key for f in shown}]
        done = request.query_params.get("done")
        return page(
            request,
            "settings.html",
            status,
            row=row,
            plugin=plugin,
            groups=groups,
            more_open=any(f.error or f.value != f.default for f in groups["more"]),
            folder=folder_name(row.id),
            done=done if done in ("saved", "added") and not found else None,
            hand_edits=request.query_params.get("hand") == "1",
            problem="; ".join(other) if other else FormErrors.MESSAGE if found else None,
        )

    @app.get("/plugins/{index}/settings", response_class=HTMLResponse)
    def settings_form(request: Request, index: int, plugin_id: _QueryId = ""):
        return settings_page(request, index, plugin_id)

    @app.post("/plugins/{index}/settings", response_class=HTMLResponse)
    async def save_settings(request: Request, index: int):
        form = await request.form()
        plugin_id = str(form.get("id", ""))
        sent = {k: [str(v) for v in form.getlist(k)] for k in form if k != "id"}
        try:
            hand_edits = await run_in_threadpool(editor.save_settings, index, plugin_id, sent)
        except FormErrors as error:
            return await run_in_threadpool(
                settings_page, request, index, plugin_id, 400, error.found
            )
        except EditError as error:
            return await run_in_threadpool(plugin_list, request, 409, str(error))
        return settings_saved(index, plugin_id, "saved", hand_edits)

    def settings_saved(index: int, plugin_id: str, done: str, hand_edits: bool):
        values = {"id": plugin_id, "done": done} | ({"hand": "1"} if hand_edits else {})
        return RedirectResponse(f"/plugins/{index}/settings?{urlencode(values)}", 303)

    @app.get("/library", response_class=HTMLResponse)
    def library_page(request: Request):
        return page(request, "library.html", items=library())

    def add_page(request: Request, plugin_type: str, status: int = 200, **values):
        item = library_item(plugin_type)
        if item is None:
            return page(request, "library.html", 404, items=library(), problem="No such plugin.")
        values.setdefault("name", editor.suggested_name(item))
        return page(request, "add.html", status, item=item, **values)

    @app.get("/library/{plugin_type}", response_class=HTMLResponse)
    def add_form(request: Request, plugin_type: str):
        return add_page(request, plugin_type)

    @app.post("/library/{plugin_type}", response_class=HTMLResponse)
    def add(request: Request, plugin_type: str, name: str = Form("")):
        item = library_item(plugin_type)
        if item is None:
            return add_page(request, plugin_type)
        try:
            hand_edits, plugin_id = editor.add(item, name)
        except EditError as error:
            return add_page(request, plugin_type, 400, name=name, problem=str(error))
        # On to its settings page, to fill in what it needs (agreed with txoof, M5 part 3a).
        rows = editor.plugin_list().rows
        index = next((r.index for r in rows if r.id == plugin_id), None)
        if index is None:  # moved away by hand meanwhile
            return saved("added", hand_edits, plugin_id)
        return settings_saved(index, plugin_id, "added", hand_edits)

    @app.post("/logout")
    def logout():
        response = RedirectResponse("/login", status_code=303)
        response.delete_cookie(COOKIE, httponly=True, samesite="strict")
        return response

    return app


def _number(value: float) -> str:
    """A number as the pages show it: ``604800``, not ``604800.0``."""
    return str(int(value)) if float(value).is_integer() else str(value)


def _known_host(host: str) -> bool:
    """True for an IP address or ``localhost``, with or without a port (see the top)."""
    if host.startswith("["):  # an IPv6 address: [::1]:8080
        name = host[1:].partition("]")[0]
    elif host.count(":") == 1:
        name = host.partition(":")[0]
    else:
        name = host
    if name.casefold() == "localhost":
        return True
    try:
        ipaddress.ip_address(name)
    except ValueError:
        return False
    return True


def _own_address(request: Request) -> str:
    """The address to show on the "open PaperPi by its IP address" page."""
    host, port = request.scope.get("server") or ("192.168.1.20", 8080)
    host = f"[{host}]" if ":" in str(host) else host
    return f"http://{host}:{port}"


def _same_site(request: Request) -> bool:
    """False for a form sent from another website (checked with the headers browsers add)."""
    if request.headers.get("sec-fetch-site", "same-origin") not in ("same-origin", "none"):
        return False
    origin = request.headers.get("origin")
    if origin is None:
        return True
    return urlsplit(origin).netloc == request.headers.get("host")
