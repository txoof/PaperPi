"""The web pages and what each address does.

=================  ==============================================================
Address            What it does
=================  ==============================================================
``/``              the home page: the picture on the screen now (``/now`` is that part
                   of the page, asked for again every few seconds; ``/screen/picture``
                   the picture, ``?id=<id>`` a plugin's latest), and a card for each
                   plugin in the config file: switch on or off, change the order, remove,
                   settings (``/plugins/<n>/...?id=<id>``, n = place in the file,
                   counted from 0, and the plugin's id to check it is still there)
``/screen/...``    ask the screen for something: ``skip``, ``refresh``, ``dismiss``,
                   ``show`` (Show now) and ``try-again`` (see :mod:`paperpi.scheduler`)
``/setup``         the first visitor sets the password (only while none is set)
``/login``         log in; also says how to reset a forgotten password
``/logout``        log out (a button on every page)
``/plugins/...``   a plugin's settings page, and the changes the home page makes;
                   ``/plugins`` (the old Active Plugins page) opens the home page;
                   ``/plugins/<n>/preview`` draws the settings form's
                   values without saving them; ``/plugins/<n>/search/<setting>`` runs
                   that setting's helper and ``/plugins/<n>/use/<setting>`` puts a
                   choice into the form (all three are parts of the settings page)
``/library``       Plugin Library: every plugin type with an example picture
                   (``/library/pictures/<file>``; ``/library/<type>/picture`` is the
                   picture's part of the page, asked for again until it is drawn);
                   ``/library/<type>`` adds one and opens its settings
``/static/...``    the style sheet, the home page's script, SortableJS (drag to change
                   the order) and htmx (a small JavaScript file that updates one part of
                   a page without loading the whole page again)
=================  ==============================================================

Every other page needs a log-in, unless ``login = false`` in ``[web]``. Forms are only
accepted when they are sent from a page of the web interface itself, so another website
can't send them in the visitor's name. And PaperPi only answers when it is opened by an IP
address or ``localhost``: a website could otherwise point a name of its own at the Pi
("DNS rebinding") and then use the pages as if they were its own.
"""

from __future__ import annotations

import hashlib
import ipaddress
import json
import logging
from collections.abc import Awaitable, Callable
from datetime import datetime
from pathlib import Path
from typing import Annotated
from urllib.parse import urlencode, urlsplit

from fastapi import FastAPI, Form, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.concurrency import run_in_threadpool

from .. import __version__, limits
from ..config import folder_name
from .auth import COOKIE_SECONDS, Auth, new_cookie
from .config_file import EditError
from .forms import Read, fields, form_texts
from .helpers import Searcher, SearchFailed, language
from .home import Controls, Snapshots, card_key, cards, now_part
from .password import PasswordError, password_problem
from .pictures import Pictures
from .plugins import FormErrors, PluginEditor, library, library_item
from .preview import Busy, Previewer, PreviewFailed

COOKIE = "paperpi_login"
log = logging.getLogger(__name__)
_HERE = Path(__file__).parent
#: Pages that work without a log-in (and everything in ``/static/``).
_OPEN = ("/setup", "/login")
#: A plugin's ID, sent as ``id`` in a form or in the address.
_FormId = Annotated[str, Form(alias="id")]
_QueryId = Annotated[str, Query(alias="id")]


def create_app(
    auth: Auth,
    editor: PluginEditor | None = None,
    previewer: Previewer | None = None,
    pictures: Pictures | None = None,
    searcher: Searcher | None = None,
    controls: Controls | None = None,
) -> FastAPI:
    """The web interface, using ``auth`` for the password and log-in, ``editor`` to
    change the plugins in the config file, ``previewer`` to draw previews, ``pictures``
    for the Plugin Library's example pictures (default: none), ``searcher`` for the
    settings helpers' searches and ``controls`` (the scheduler) for what is on screen
    (without it, the home page shows only the config file)."""
    editor = editor or PluginEditor(auth.config_file)
    previewer = previewer or Previewer()
    pictures = pictures or Pictures(None)
    searcher = searcher or Searcher()
    snapshots = Snapshots()
    app = FastAPI(title="PaperPi", docs_url=None, redoc_url=None, openapi_url=None)
    app.mount("/static", StaticFiles(directory=_HERE / "static"), name="static")
    templates = Jinja2Templates(directory=_HERE / "templates")
    templates.env.globals.update(
        version=__version__,
        auth=auth,
        text_limit=limits.HELPER_TEXT,
        time_limit=limits.HELPER_SEARCH,
    )
    templates.env.filters["number"] = _number
    templates.env.filters["sentence"] = lambda text: text[:1].upper() + text[1:]
    templates.env.filters["card_key"] = card_key

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
        path = request.url.path
        # The look (style.css, theme.js) is the same for everyone, so the "open me by my
        # address" page can use it too.
        static = path.startswith("/static/") and request.method in ("GET", "HEAD")
        if not static and not _known_host(request.headers.get("host", "")):
            return page(request, "by_address.html", 400, address=_own_address(request))
        if request.method not in ("GET", "HEAD") and not _same_site(request):
            return Response("Forms are only accepted from PaperPi's own pages.", 403)
        if auth.login and path not in _OPEN and not path.startswith("/static/"):
            if auth.password_hash is None:
                return _go_to(request, "/setup")
            if not auth.cookie_ok(request.cookies.get(COOKIE)):
                return _go_to(request, "/login")
        return await call_next(request)

    @app.middleware("http")
    async def check(request: Request, call_next: Callable[[Request], Awaitable[Response]]):
        response = await refused_or_page(request, call_next)
        path = request.url.path
        response.headers["X-Frame-Options"] = "DENY"
        # Browsers never take a text or a picture for a page.
        response.headers["X-Content-Type-Options"] = "nosniff"
        # Previews are pictures sent inside the page (data: addresses), never saved.
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; img-src 'self' data:; frame-ancestors 'none'; "
            "form-action 'self'; base-uri 'none'"
        )
        response.headers["Referrer-Policy"] = "same-origin"
        if not path.startswith(("/static/", "/library/pictures/", "/screen/picture")):
            response.headers["Cache-Control"] = "no-store"
        return response

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

    def found_rows() -> tuple[list, list[str], bool]:
        """The config file's plugin blocks, the file's problems, and whether it was read."""
        try:
            found = editor.plugin_list()
        except EditError as error:
            return [], [str(error)], False
        return found.rows, found.problems, True

    def summary():
        return controls.summary if controls is not None else None

    def home_page(request: Request, status: int = 200, problem: str | None = None):
        rows, problems, read = found_rows()
        if not read and status == 200:
            status = 500
        done = request.query_params.get("done")
        # The name is looked up by the ID in the address: a link can't put other text on
        # the page.
        plugin_id = request.query_params.get("id")
        name = next((row.name for row in rows if plugin_id and row.id == plugin_id), None)
        snapshots.keep_only({row.id for row in rows})
        return page(
            request,
            "home.html",
            status,
            **home_values(rows),
            running=controls is not None,
            problems=[p for p in dict.fromkeys(problems) if p != problem],
            problem=problem,
            done=done if done in _DONE else None,
            message=_DONE.get(done or ""),
            name=name,
            hand_edits=request.query_params.get("hand") == "1",
        )

    def home_values(rows: list) -> dict:
        now, shown = datetime.now(), summary()
        examples = {row.type: pictures.shown(row.type) for row in rows}
        values = {
            "now": now_part(shown, rows, snapshots, now),
            "cards": cards(rows, shown, snapshots, examples, now),
        }
        # What the screen part shows; the same text when nothing changed.
        values["seen"] = hashlib.sha256(repr(values).encode()).hexdigest()[:16]
        return values

    def now_page(request: Request, asked: str | None = None):
        rows, _, _ = found_rows()
        values = home_values(rows)
        if asked is None and request.query_params.get("seen") == values["seen"]:
            return Response(status_code=204)  # htmx then leaves the page as it is
        return page(
            request,
            "now.html",
            running=controls is not None,
            asked=_DONE.get(asked or ""),
            live=True,
            **values,
        )

    def saved(done: str, hand_edits: bool, plugin_id: str = "") -> RedirectResponse:
        values = {"done": done} | ({"id": plugin_id} if plugin_id else {})
        query = urlencode(values | ({"hand": "1"} if hand_edits else {}))
        return RedirectResponse(f"/?{query}", status_code=303)

    # The pages answer a part of the page (htmx) or a form sent without JavaScript.
    def changed(request: Request, done: str, hand_edits: bool) -> Response:
        if request.headers.get("hx-request") == "true":
            return Response(status_code=204)
        return saved(done, hand_edits)

    def refused(request: Request, status: int, problem: str) -> Response:
        if request.headers.get("hx-request") == "true":
            return Response(problem, status, media_type="text/plain")
        return home_page(request, status, problem)

    @app.get("/", response_class=HTMLResponse)
    def home(request: Request):
        return home_page(request)

    @app.get("/now", response_class=HTMLResponse)
    def now_part_page(request: Request):
        return now_page(request)

    @app.get("/screen/picture")
    def screen_picture(plugin_id: _QueryId = "", v: int = 0):
        found = snapshots.png(plugin_id)
        if found is None:
            return Response("No such picture.", 404)
        number, png = found
        # The address holds the picture's number, so the browser may keep it; a picture
        # that changed meanwhile is sent as it is now, but not kept.
        keep = "private, max-age=86400" if number == v else "no-store"
        return Response(png, media_type="image/png", headers={"Cache-Control": keep})

    def asked(request: Request, what: str, ask: Callable[[], None]) -> Response:
        if controls is None:
            return refused(request, 409, "PaperPi's screen is not running.")
        ask()
        if request.headers.get("hx-request") == "true":
            return now_page(request, what)
        return RedirectResponse(f"/?done={what}", status_code=303)

    @app.post("/screen/skip", response_class=HTMLResponse)
    def skip(request: Request):
        return asked(request, "skip", lambda: controls.skip())

    @app.post("/screen/refresh", response_class=HTMLResponse)
    def refresh(request: Request):
        return asked(request, "refresh", lambda: controls.refresh())

    @app.post("/screen/dismiss", response_class=HTMLResponse)
    def dismiss(request: Request, plugin_id: _FormId = ""):
        return asked(request, "dismiss", lambda: controls.dismiss(plugin_id))

    @app.post("/screen/show", response_class=HTMLResponse)
    def show_now(request: Request, plugin_id: _FormId = ""):
        return asked(request, "show", lambda: controls.show_now(plugin_id))

    @app.post("/screen/try-again", response_class=HTMLResponse)
    def try_again(request: Request, plugin_id: _FormId = ""):
        return asked(request, "again", lambda: controls.try_again(plugin_id or None))

    @app.get("/plugins")
    def plugins_page(request: Request):
        query = request.url.query
        return RedirectResponse("/" + (f"?{query}" if query else ""), status_code=303)

    @app.post("/plugins/{index}/move", response_class=HTMLResponse)
    def move(
        request: Request,
        index: int,
        plugin_id: _FormId = "",
        step: str = Form(""),
        to: str = Form(""),
    ):
        place = int(to) if to.isascii() and to.isdigit() else None
        if place is None and step not in ("up", "down"):
            return refused(request, 400, "Choose up or down.")
        try:
            if place is not None:
                hand_edits = editor.move_to(index, plugin_id, place)
            else:
                hand_edits = editor.move(index, plugin_id, -1 if step == "up" else 1)
        except EditError as error:
            return refused(request, 409, str(error))
        return changed(request, "saved", hand_edits)

    @app.post("/plugins/{index}/enabled", response_class=HTMLResponse)
    def switch(request: Request, index: int, plugin_id: _FormId = "", on: str = Form("")):
        try:
            hand_edits = editor.set_enabled(index, plugin_id, on == "1")
        except EditError as error:
            return home_page(request, 409, str(error))
        return saved("saved", hand_edits)

    @app.get("/plugins/{index}/remove", response_class=HTMLResponse)
    def remove_page(request: Request, index: int, plugin_id: _QueryId = ""):
        try:
            row = editor.row(index, plugin_id)
        except EditError as error:
            return home_page(request, 409, str(error))
        return page(request, "remove.html", row=row)

    @app.post("/plugins/{index}/remove", response_class=HTMLResponse)
    def remove(request: Request, index: int, plugin_id: _FormId = ""):
        try:
            hand_edits = editor.remove(index, plugin_id)
        except EditError as error:
            return home_page(request, 409, str(error))
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
            return home_page(request, 409, str(error))
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
            more_open=any(f.error or f.changed for f in groups["more"]),
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
        plugin_id, sent = _settings_form(await request.form())
        try:
            hand_edits = await run_in_threadpool(editor.save_settings, index, plugin_id, sent)
        except FormErrors as error:
            return await run_in_threadpool(
                settings_page, request, index, plugin_id, 400, error.found
            )
        except EditError as error:
            return await run_in_threadpool(home_page, request, 409, str(error))
        return settings_saved(index, plugin_id, "saved", hand_edits)

    @app.post("/plugins/{index}/preview", response_class=HTMLResponse)
    async def preview(request: Request, index: int):
        # Only a part of the settings page (htmx), so every answer is a 200: htmx doesn't
        # show the others.
        plugin_id, sent = _settings_form(await request.form())
        try:
            job = await run_in_threadpool(editor.preview_job, index, plugin_id, sent)
            drawn = await run_in_threadpool(previewer.draw, job)
        except FormErrors as error:
            return page(request, "preview.html", errors=error.found.errors)
        except (EditError, Busy, PreviewFailed) as error:
            return page(request, "preview.html", problem=str(error))
        except Exception:  # noqa: BLE001 - e.g. no plugin process could be started
            log.exception("preview of %s", plugin_id)
            problem = "The preview could not be drawn. PaperPi's log has the details."
            return page(request, "preview.html", problem=problem)
        return page(request, "preview.html", drawn=drawn, job=job)

    @app.post("/plugins/{index}/search/{key}", response_class=HTMLResponse)
    async def search(request: Request, index: int, key: str):
        # Only a part of the settings page (htmx), so every answer is a 200.
        plugin_id, sent = _settings_form(await request.form())
        text = (sent.pop("_search", None) or [""])[-1]
        job = None
        try:
            spoken = language(request.headers.get("accept-language"))
            job = await run_in_threadpool(
                editor.search_job, index, plugin_id, sent, key, text, spoken
            )
            found = await run_in_threadpool(searcher.find, job)
        except FormErrors as error:
            return page(request, "found.html", errors=error.found.errors)
        except (EditError, Busy, SearchFailed) as error:
            helper = job.helper if job else None
            return page(request, "found.html", problem=str(error), helper=helper)
        except Exception:  # noqa: BLE001 - e.g. no plugin process could be started
            log.exception("search of %s, %s", plugin_id, key)
            problem = "The search failed. PaperPi's log has the details."
            return page(request, "found.html", problem=problem)
        # What Use sends back: each setting with its texts, as the form sends them.
        uses = [
            json.dumps({k: form_texts(v) for k, v in choice.fill.items()})
            for choice in found.choices
        ]
        values = {"found": found, "helper": job.helper, "uses": uses}
        return page(request, "found.html", index=index, key=key, **values)

    @app.post("/plugins/{index}/use/{key}", response_class=HTMLResponse)
    async def use(request: Request, index: int, key: str):
        # Only a part of the settings page (htmx), so every answer is a 200.
        plugin_id, sent = _settings_form(await request.form())
        fill = _fill((sent.pop("_use", None) or [""])[-1])
        if not fill:
            return page(request, "filled.html", problem="This choice can't be used.", shown=[])
        try:
            shown = await run_in_threadpool(editor.filled, index, plugin_id, sent, key, fill)
        except EditError as error:
            return page(request, "filled.html", problem=str(error), shown=[])
        if not shown:
            problem = "This choice has nothing the form can fill in."
            return page(request, "filled.html", problem=problem, shown=[])
        return page(request, "filled.html", shown=shown)

    def settings_saved(index: int, plugin_id: str, done: str, hand_edits: bool):
        values = {"id": plugin_id, "done": done} | ({"hand": "1"} if hand_edits else {})
        return RedirectResponse(f"/plugins/{index}/settings?{urlencode(values)}", 303)

    def library_page(request: Request, status: int = 200, problem: str | None = None):
        items = library()
        shown = {item.type: pictures.shown(item.type) for item in items}
        return page(request, "library.html", status, items=items, shown=shown, problem=problem)

    @app.get("/library", response_class=HTMLResponse)
    def library_list(request: Request):
        return library_page(request)

    @app.get("/library/pictures/{name}")
    def library_picture(name: str):
        found = pictures.path(name)
        if found is None:
            return Response("No such picture.", 404)
        # The name changes with the picture, so the browser may keep it.
        return FileResponse(
            found, media_type="image/png", headers={"Cache-Control": "private, max-age=86400"}
        )

    @app.get("/library/{plugin_type}/picture", response_class=HTMLResponse)
    def library_picture_part(request: Request, plugin_type: str):
        # Only a part of the Library page (htmx), so every answer is a 200.
        item = library_item(plugin_type)
        shown = pictures.shown(plugin_type) if item is not None else None
        return page(request, "picture.html", item=item, picture=shown)

    def add_page(request: Request, plugin_type: str, status: int = 200, **values):
        item = library_item(plugin_type)
        if item is None:
            return library_page(request, 404, "No such plugin.")
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
        try:
            rows = editor.plugin_list().rows
        except EditError:  # the file can't be read a moment later: show what can be shown
            rows = []
        index = next((r.index for r in rows if r.id == plugin_id), None)
        if index is None:  # moved away or removed by hand meanwhile
            return saved("added", hand_edits, plugin_id)
        return settings_saved(index, plugin_id, "added", hand_edits)

    @app.post("/logout")
    def logout():
        response = RedirectResponse("/login", status_code=303)
        response.delete_cookie(COOKIE, httponly=True, samesite="strict")
        return response

    return app


#: What the home page says after a change or a request (``?done=...``).
_DONE = {
    "saved": "Saved. PaperPi applies the change now.",
    "added": "",
    "removed": "Plugin removed. PaperPi applies the change now.",
    "skip": "Asked PaperPi to show the next plugin.",
    "refresh": "Asked PaperPi to fetch new data and draw the picture again.",
    "dismiss": "Asked PaperPi to dismiss the alert.",
    "show": "Asked PaperPi to show the plugin now, for one extra turn.",
    "again": "Asked PaperPi to try again now.",
}


def _go_to(request: Request, path: str) -> Response:
    """Send the browser to ``path``. For a part of a page that htmx asked for, htmx opens
    the whole page (else it would show the page inside the part)."""
    if request.headers.get("hx-request") == "true":
        return Response(status_code=204, headers={"HX-Redirect": path})
    return RedirectResponse(path, status_code=303)


def _settings_form(form) -> tuple[str, dict[str, list[str]]]:
    """The plugin ID and the settings of a sent settings form."""
    plugin_id = str(form.get("id", ""))
    return plugin_id, {k: [str(v) for v in form.getlist(k)] for k in form if k != "id"}


def _fill(text: str) -> dict[str, list[str]]:
    """The settings and texts a Use button sends (``{}`` when they are not in that form)."""
    if len(text) > limits.HELPER_USE:
        return {}
    try:
        fill = json.loads(text)
    except (ValueError, RecursionError):  # RecursionError: nested very deeply
        return {}
    texts = fill.values() if isinstance(fill, dict) else [None]
    if not all(isinstance(v, list) and all(isinstance(t, str) for t in v) for v in texts):
        return {}
    return fill


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
