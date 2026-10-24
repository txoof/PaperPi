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
``/login``         log in; also says how to reset a forgotten password. Both pages show
                   the picture on the screen now and its plugin's name
                   (``/login/picture``: only that picture, open to everyone)
``/logout``        log out (a button on every page)
``/plugins/...``   a plugin's settings page, and the changes the home page makes;
                   ``/plugins`` (the old Active Plugins page) opens the home page;
                   ``/plugins/<n>/preview`` draws the settings form's
                   values without saving them; ``/plugins/<n>/search/<setting>`` runs
                   that setting's helper and ``/plugins/<n>/use/<setting>`` puts a
                   choice into the form (all three are parts of the settings page)
``/library``       Plugin Library: every plugin type with an example picture
                   (``/library/pictures/<file>``; ``/library/<type>/picture`` is the
                   picture's part of the page, asked for again until it is drawn,
                   ``?layout=<name>`` for another layout); ``/library/<type>/look``
                   (Look closer) shows each layout's picture bigger (``?layout=<name>``);
                   ``/library/<type>`` adds one and opens its settings;
                   ``/library/<type>/readme`` shows its README
``/changes``       Review changes: hand edits to the config file that PaperPi does not
                   use yet (``/changes/apply`` loads the file again, ``/changes/undo``
                   puts back the file PaperPi uses); a bar on every page links here while
                   there are some
``/warnings``      what needs attention now (``/warnings/reload`` loads the config file
                   again), and the recent warnings and errors; ``/log`` is the Full log
                   (``/log/new`` the lines after a number, ``/log/download`` all of them)
``/system``        Screen & system: the screen in use, the ``[display]`` and ``[web]``
                   settings (a POST to ``/system`` saves them all; ``/system/port``
                   checks a new port while it is typed, ``/system/web/undo`` keeps the
                   address in use, ``/system/password`` changes the password) and facts
                   about this Pi (``/system/pi``, asked for again while the page is open);
                   ``/system/screen`` Change screen… (used from the next start;
                   ``/system/screen/undo`` and ``/system/screen/back`` put back the
                   screen in use or the previous one), ``/system/restart`` restarts
                   PaperPi when it runs as a service; ``/system/web/keep`` keeps new
                   web settings on trial and ``/system/web/back`` goes back to the old
                   ones (the box on every page; ``/warnings/web-seen`` hides the note
                   that it went back)
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

import asyncio
import hashlib
import ipaddress
import json
import logging
import os
import time
from collections.abc import Awaitable, Callable
from datetime import date, datetime
from pathlib import Path
from typing import Annotated
from urllib.parse import urlencode, urlsplit

from epdlib.drivers.it8951 import MODELS as IT8951_MODELS
from fastapi import FastAPI, Form, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.concurrency import run_in_threadpool

from .. import __version__, config, limits
from ..config import ConfigError, folder_name, read_text
from ..logbook import Logbook
from ..plugins import readme as readme_text
from . import changes, keep, logs, readme, system, warnings
from .auth import COOKIE_SECONDS, Auth, new_cookie
from .config_file import EditError, UnknownForm, fingerprint, kept_path, saved_here
from .config_file import read as read_config
from .forms import Read, fields, form_texts
from .helpers import Searcher, SearchFailed, language
from .home import Controls, Now, Snapshots, card_key, cards, now_part
from .password import PasswordError, password_problem
from .pictures import Pictures
from .plugins import (
    FormErrors,
    LibraryItem,
    PluginEditor,
    added_names,
    library,
    library_item,
)
from .preview import Busy, Previewer, PreviewFailed

COOKIE = "paperpi_login"
log = logging.getLogger(__name__)
_HERE = Path(__file__).parent
#: Pages that work without a log-in (and everything in ``/static/``).
_OPEN = ("/setup", "/login", "/login/picture")
#: Addresses the browser may keep (the others are sent again each time).
_KEPT = ("/static/", "/library/pictures/", "/screen/picture", "/login/picture")
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
    logbook: Logbook | None = None,
    state_dir: Path | None = None,
    web: config.WebSettings | None = None,
    keeper: keep.Keeper | None = None,
) -> FastAPI:
    """The web interface, using ``auth`` for the password and log-in, ``editor`` to
    change the plugins in the config file, ``previewer`` to draw previews, ``pictures``
    for the Plugin Library's example pictures (default: none), ``searcher`` for the
    settings helpers' searches, ``controls`` (the scheduler) for what is on screen
    (without it, the home page shows only the config file) and ``logbook`` for the Full
    log (without it, the page says the log is not kept). ``state_dir`` is PaperPi's state
    folder, whose disk's free space the Screen & system page shows. ``web``: the ``[web]``
    settings the web interface started with (its address and port). ``keeper`` holds the
    ones in use, and the old ones while new ones are on trial (see :mod:`.keep`)."""
    editor = editor or PluginEditor(auth.config_file)
    previewer = previewer or Previewer()
    pictures = pictures or Pictures(None)
    searcher = searcher or Searcher()
    snapshots = Snapshots()
    keeper = keeper or keep.Keeper(web, state_dir)
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
    templates.env.filters["thousands"] = "{:,}".format
    templates.env.filters["sentence"] = lambda text: text[:1].upper() + text[1:]
    templates.env.filters["card_key"] = card_key

    def page(request: Request, template: str, status: int = 200, **values) -> HTMLResponse:
        return templates.TemplateResponse(request, template, values, status_code=status)

    def logged_in(request: Request, stored: str, then: str = "/") -> RedirectResponse:
        response = RedirectResponse(then, status_code=303)
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
        if not path.startswith(_KEPT):
            response.headers["Cache-Control"] = "no-store"
        return response

    def open_page(request: Request, template: str, status: int = 200, **values) -> HTMLResponse:
        """A log-in page, with what is on the screen now (the only thing it shows of PaperPi)."""
        shown = summary()
        rows = found_rows()[0] if shown is not None else []
        full = now_part(shown, rows, snapshots, datetime.now())
        # Only these, so plugin texts (the next plugin, an alert) never show before log-in.
        now = Now(
            full.id,
            full.name,
            since=full.since,
            picture=full.picture,
            width=full.width,
            height=full.height,
        )
        return page(request, template, status, now=now, running=controls is not None, **values)

    @app.get("/setup", response_class=HTMLResponse)
    def setup_page(request: Request):
        if not auth.login or auth.password_hash is not None:
            return RedirectResponse("/", status_code=303)
        return open_page(request, "setup.html")

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
        return open_page(request, "setup.html", 400, problem=problem)

    @app.get("/login", response_class=HTMLResponse)
    def login_page(request: Request):
        if not auth.login:
            return RedirectResponse("/", status_code=303)
        if auth.password_hash is None:
            return RedirectResponse("/setup", status_code=303)
        return open_page(request, "login.html")

    @app.get("/login/picture")
    def login_picture(v: int = 0):
        return screen_picture("", v)

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
        return open_page(request, "login.html", 401, problem="Wrong password.")

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

    def asked(request: Request, what: str, ask: Callable[[], None], back: str = "/") -> Response:
        if controls is None:
            return refused(request, 409, "PaperPi's screen is not running.")
        ask()
        if request.headers.get("hx-request") == "true":
            return now_page(request, what)
        return RedirectResponse(f"{back}?done={what}", status_code=303)

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
    def try_again(request: Request, plugin_id: _FormId = "", back: str = Form("")):
        """``back=warnings``: sent from the Warnings tab, which is opened again."""
        back = "/warnings" if back == "warnings" else "/"
        return asked(request, "again", lambda: controls.try_again(plugin_id or None), back)

    # The config file's plugin blocks for the menu's count, read again only when the file
    # changed (every page shows the count).
    attention_found: dict = {}

    def attention() -> list[warnings.Item]:
        try:
            stat = editor.path.stat()
            key = (stat.st_mtime_ns, stat.st_size)
        except OSError:
            key = None
        if key is None or attention_found.get("key") != key:
            rows, problems, _ = found_rows()
            # A file the web interface can't change safely is still one PaperPi can use.
            problems = [p for p in problems if p != str(UnknownForm())]
            attention_found.update(key=key, found=(rows, problems))
        rows, problems = attention_found["found"]
        items = warnings.needs_attention(summary(), rows, problems, datetime.now())
        if keeper.note is not None:
            items.insert(0, warnings.went_back(keeper.note))
        return items

    # The menu shows how many things need attention, on every page.
    templates.env.globals["attention_count"] = lambda: len(attention())

    def keep_box(request: Request) -> dict | None:
        """The Keep these settings box, on every page while new web settings are on trial."""
        old, used = keeper.old, keeper.used
        if old is None or used is None:
            return None
        host = request.url.hostname or ""
        return {
            "left": keeper.seconds_left(),
            "new": system.web_address(host, used),
            "old": system.web_address(host, old),
            "back": f"port {old.port}" if old.port != used.port else "the old address",
            # Then a browser on another device can't open it.
            "here": system.only_here(old) and not system.only_here(used),
        }

    templates.env.globals["keep_box"] = keep_box

    @app.post("/warnings/web-seen")
    def web_note_seen():
        keeper.note = None
        return RedirectResponse("/warnings", status_code=303)

    def warnings_values(shown: str) -> dict:
        today = date.today()
        values = {
            "items": attention(),
            "days": warnings.recent(logbook, shown, today) if logbook is not None else None,
            "shown": shown,
            "filters": warnings.FILTERS,
        }
        # What the page shows; the same text when nothing changed.
        values["seen"] = hashlib.sha256(repr(values).encode()).hexdigest()[:16]
        return values

    @app.get("/warnings", response_class=HTMLResponse)
    def warnings_page(request: Request, show: str = "", seen: str = ""):
        values = warnings_values(warnings.filter_of(show))
        values |= {"attention": len(values["items"]), "running": controls is not None}
        if request.headers.get("hx-request") == "true":
            # Asked again every few seconds while the page is open.
            if seen == values["seen"]:
                return Response(status_code=204)  # htmx then leaves the page as it is
            return page(request, "_warnings.html", **values, live=True)
        done = request.query_params.get("done")
        return page(
            request,
            "warnings.html",
            **values,
            most=warnings.RECENT,
            message=_DONE.get(done or "") if done in ("again", "reload") else None,
        )

    # Hand edits: read again only when the file or the text PaperPi uses changed (every
    # page shows the bar).
    edits_found: dict = {}

    def hand_edits() -> str | None:
        """The config file's text, when it holds settings PaperPi does not use yet."""
        applied = editor.applied
        if controls is None or applied is None:
            return None  # nothing to apply them to
        try:
            stat = editor.path.stat()
        except OSError:
            return None
        # A save makes a new file (new inode), even within the same timestamp step.
        key = (stat.st_ino, stat.st_mtime_ns, stat.st_size, applied)
        if edits_found.get("key") != key:
            try:
                text = read_text(editor.path)
            except ConfigError:
                text = None  # the Warnings page names it
            if text is not None and not changes.waiting(applied, text):
                text = None
            edits_found.update(key=key, text=text)
        text = edits_found["text"]
        # Checked every time: the web interface may have saved this text a moment ago.
        return None if text is None or saved_here(editor.path, text) else text

    templates.env.globals["hand_edits_waiting"] = lambda: hand_edits() is not None

    def changes_view(
        request: Request,
        status: int = 200,
        done: str = "",
        asking: bool = False,
        problem: str | None = None,
    ) -> HTMLResponse:
        edited = hand_edits()
        found = None
        if edited is not None:
            found = changes.review(editor.applied or "", edited, editor.path.name)
        try:
            changed_at = datetime.fromtimestamp(editor.path.stat().st_mtime)
        except OSError:
            changed_at = None
        return page(
            request,
            "changes.html",
            status,
            review=found,
            running=controls is not None,
            path=editor.path,
            changed_at=changed_at,
            today=date.today(),
            command=_reload_command(),
            message=_DONE.get(done) if done in ("applied", "applying") else None,
            kept=kept_path(editor.path),
            undone=done == "undone" and found is None,
            asking=asking and found is not None,
            seen=fingerprint(edited) if edited is not None else "",
            problem=problem,
        )

    @app.get("/changes", response_class=HTMLResponse)
    def changes_page(request: Request, done: str = "", undo: str = ""):
        return changes_view(request, done=done, asking=undo == "1")

    @app.post("/changes/apply")
    async def apply_changes():
        if controls is None:
            return Response("PaperPi's screen is not running.", 409, media_type="text/plain")
        edited = await run_in_threadpool(hand_edits)
        if edited is not None:
            found = await run_in_threadpool(
                changes.review, editor.applied or "", edited, editor.path.name
            )
            if found.mistakes:  # the page names them; PaperPi would keep the old settings
                return RedirectResponse("/changes", status_code=303)
        controls.reload()
        # PaperPi loads the file between two screen writes: wait a moment, so the page
        # can mostly say it is done.
        end = time.monotonic() + limits.APPLY_WAIT
        while await run_in_threadpool(hand_edits) is not None and time.monotonic() < end:
            await asyncio.sleep(0.1)
        done = "applying" if await run_in_threadpool(hand_edits) is not None else "applied"
        return RedirectResponse(f"/changes?done={done}", status_code=303)

    @app.post("/changes/undo", response_class=HTMLResponse)
    def undo_changes(request: Request, seen: str = Form("")):
        if hand_edits() is None:  # undone already, or applied
            return RedirectResponse("/changes", status_code=303)
        try:
            editor.undo(seen)
        except EditError as error:
            return changes_view(request, 409, problem=str(error))
        return RedirectResponse("/changes?done=undone", status_code=303)

    @app.post("/warnings/reload")
    def reload_config():
        """Load the config file again (after a mistake in it was fixed)."""
        if controls is None:
            return Response("PaperPi's screen is not running.", 409, media_type="text/plain")
        controls.reload()
        return RedirectResponse("/warnings?done=reload", status_code=303)

    def log_values(
        level: str, search: str, follow: str, after: int | None = None, earlier: bool = False
    ) -> dict:
        level = logs.level_of(level)
        search = search[: logs.LONGEST_SEARCH]
        return {
            "shown": (
                logs.show(logbook, level, search, after, earlier) if logbook is not None else None
            ),
            "level": level,
            "search": search,
            "follow": follow == "1",
        }

    @app.get("/log", response_class=HTMLResponse)
    def log_page(request: Request, level: str = "", q: str = "", follow: str = ""):
        part = request.headers.get("hx-request") == "true" and logbook is not None
        return page(
            request,
            "_log.html" if part else "log.html",
            **log_values(level, q, follow),
            running=logbook is not None,
            filters=logs.FILTERS,
            longest_search=logs.LONGEST_SEARCH,
            kept=limits.LOG_LINES,
            most=logs.SHOWN,
        )

    @app.get("/log/new", response_class=HTMLResponse)
    def log_new(request: Request, after: int = 0, level: str = "", q: str = "", earlier: str = ""):
        """The lines after line ``after``, for "New lines as they come"; ``earlier`` says the
        page's last line is from the file."""
        if logbook is None:
            return Response(status_code=204)
        values = log_values(level, q, "1", after, earlier == "1")
        new = values["shown"]
        if not new.rows:
            return Response(status_code=204)  # htmx then leaves the page as it is
        # The count below the list is of all lines, as after loading the page.
        counted = logs.show(logbook, values["level"], values["search"])
        return page(request, "_log_new.html", **values, counted=counted, oob=True)

    @app.get("/log/download")
    def log_download():
        text = logs.as_text(logbook) if logbook is not None else ""
        name = logs.file_name(datetime.now())
        return Response(
            text,
            media_type="text/plain; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{name}"'},
        )

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
        try:
            added = added_names(editor.plugin_list().rows)
        except EditError:
            added = {}  # the page still lists the plugins; Home names the problem
        return page(
            request,
            "library.html",
            status,
            items=items,
            shown=shown,
            added=added,
            problem=problem,
        )

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

    def layout_shown(item: LibraryItem | None, layout: str):
        """The picture of ``layout`` of ``item``, ``None`` for an unknown plugin or
        layout (or without pictures)."""
        if item is None or item.plugin is None:
            return None
        try:
            return pictures.shown(item.type, layout)
        except KeyError:
            return None

    @app.get("/library/{plugin_type}/picture", response_class=HTMLResponse)
    def library_picture_part(request: Request, plugin_type: str, layout: str = ""):
        # Only a part of a page (htmx), so every answer is a 200.
        item = library_item(plugin_type)
        shown = layout_shown(item, layout)
        return page(request, "picture.html", item=item, picture=shown, layout=layout)

    @app.get("/library/{plugin_type}/look", response_class=HTMLResponse)
    def look(request: Request, plugin_type: str, layout: str = ""):
        item = library_item(plugin_type)
        if item is None:
            return library_page(request, 404, "No such plugin.")
        if item.plugin is None:
            return library_page(request, 404, item.description)  # why it is broken
        layout = layout or item.plugin.default_layout
        if layout not in item.plugin.layouts:
            return library_page(request, 404, "This plugin has no such layout.")
        values = {"item": item, "layout": layout, "picture": layout_shown(item, layout)}
        # The Library's window asks for the inside only (library.js).
        part = request.headers.get("hx-request") == "true"
        return page(request, "look_window.html" if part else "look.html", **values)

    def add_page(request: Request, plugin_type: str, status: int = 200, **values):
        item = library_item(plugin_type)
        if item is None:
            return library_page(request, 404, "No such plugin.")
        values.setdefault("name", editor.suggested_name(item))
        # The Library's Add window asks for the form only (library.js).
        part = request.headers.get("hx-request") == "true" and status == 200
        return page(request, "add_window.html" if part else "add.html", status, item=item, **values)

    @app.get("/library/{plugin_type}/readme", response_class=HTMLResponse)
    def readme_page(request: Request, plugin_type: str):
        item = library_item(plugin_type)
        text = readme_text(plugin_type) if item is not None and item.plugin else None
        if text is None:
            return library_page(request, 404, "No README for this plugin.")
        body = readme.to_html(text, [i.type for i in library() if i.plugin])
        return page(request, "readme.html", item=item, body=body)

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

    def system_page(
        request: Request,
        status: int = 200,
        problem: str | None = None,
        wrong: system.SectionErrors | None = None,
    ):
        try:
            text = read_config(editor.path)[1]
            values = system.form(text)
            file_display = system.file_display(text)
        except EditError as error:
            text, values, file_display = None, {}, None
            problem = problem or str(error)
            status = 500 if status == 200 else status
        display = editor.display or file_display
        if wrong is not None:
            values |= wrong.values
        done = request.query_params.get("done", "")
        shown = summary()
        screen_state = shown.screen if shown is not None else None
        new_screen = system.waiting(file_display, editor.display)
        new_web = (
            system.web_waiting(system.file_web(text), keeper.used) if text is not None else None
        )
        before = system.previous(state_dir)
        if before is not None and editor.display is not None and not new_screen:
            if before == system.screen_of(editor.display):
                before = None  # back on it, by hand
            elif screen_state == "ok":
                # The new screen answers: the previous one is not needed any more.
                system.forget_previous(state_dir)
                before = None
        return page(
            request,
            "system.html",
            status,
            values=values,
            saved=system.form(text) if text is not None else {},
            screen=system.screen_facts(display) if display is not None else None,
            screen_state=screen_state,
            running=controls is not None,
            pi=pi_facts(),
            problem=problem,
            errors=wrong.errors if wrong is not None else {},
            done=_SYSTEM_DONE.get(done, ""),
            hand_edits=request.query_params.get("hand") == "1",
            readable=text is not None,
            new_screen=system.screen_of(file_display) if new_screen and file_display else None,
            go_back=before if screen_state in ("failing", "paused") and not new_screen else None,
            describe=system.describe,
            can_restart=can_restart(),
            web_now=system.web_address(request.url.hostname or "", keeper.used)
            if keeper.used
            else None,
            new_web=system.web_address(request.url.hostname or "", new_web) if new_web else None,
            new_web_here=new_web is not None and system.only_here(new_web),
            addresses=system.ADDRESSES,
            change_password=auth.login and auth.password_hash is not None,
        )

    def can_restart() -> bool:
        """PaperPi can restart itself only as a service: systemd starts it again."""
        return controls is not None and _reload_command()[1]

    def restarting(request: Request) -> Response:
        controls.restart()
        try:
            new_web = system.web_waiting(system.file_web(read_config(editor.path)[1]), keeper.used)
        except EditError:
            new_web = None
        moved = None
        if new_web is not None:
            moved = system.web_address(request.url.hostname or "", new_web)
        here = new_web is not None and system.only_here(new_web)
        return page(request, "restarting.html", moved=moved, here=here)

    def used_screen() -> dict | None:
        return system.screen_of(editor.display) if editor.display is not None else None

    def screen_page(request: Request, status: int = 200, wrong=None, problem=None):
        try:
            file_display = system.file_display(read_config(editor.path)[1])
        except EditError as error:
            file_display, problem = None, problem or str(error)
        values = system.screen_form(file_display or editor.display)
        if wrong is not None:
            values |= wrong.values
        return page(
            request,
            "screen.html",
            status,
            values=values,
            errors=wrong.errors if wrong is not None else {},
            problem=problem,
            models=list(IT8951_MODELS.items()),
            shows=system.SHOWS,
        )

    def system_done(done: str) -> RedirectResponse:
        return RedirectResponse(f"/system?done={done}", status_code=303)

    def pi_facts() -> system.PiFacts:
        shown = summary()
        return system.pi_facts(state_dir, shown.written_at if shown is not None else None)

    @app.get("/system", response_class=HTMLResponse)
    def system_settings(request: Request):
        return system_page(request)

    @app.get("/system/pi", response_class=HTMLResponse)
    def system_pi(request: Request):
        return page(request, "_pi.html", pi=pi_facts())

    @app.post("/system", response_class=HTMLResponse)
    async def save_system(request: Request):
        form = await request.form()
        sent = {k: [str(v) for v in form.getlist(k)] for k in form if k != "next"}
        login = file_login()
        try:
            hand_edits = await run_in_threadpool(
                editor.change, lambda text: system.with_values(text, sent, keeper.used)
            )
        except system.SectionErrors as error:
            return system_page(request, 400, str(error), error)
        except EditError as error:
            return system_page(request, 409, str(error))
        use_login(login)
        keeper.saved(file_web())
        # "Save and apply, then go" in the leave-this-page window: only PaperPi's own pages.
        then = str(form.get("next", ""))
        if then.startswith("/") and not then.startswith(("//", "/\\")):
            return RedirectResponse(then, status_code=303)
        query = urlencode({"done": "saved"} | ({"hand": "1"} if hand_edits else {}))
        return RedirectResponse(f"/system?{query}", status_code=303)

    def file_web() -> config.WebSettings | None:
        try:
            return system.file_web(read_config(editor.path)[1])
        except EditError:
            return None

    def file_login() -> bool | None:
        found = file_web()
        return found.login if found is not None else None

    def use_login(before: bool | None) -> None:
        """A log-in switched on or off applies at once, before the config file is loaded
        again: the next page is shown with it (switched on: "Set a password")."""
        found = file_web()
        if found is not None and before is not None and found.login != before:
            auth.use(found)

    @app.get("/system/port", response_class=HTMLResponse)
    def check_port(request: Request, port: str = "", address: str = ""):
        """The port check under the Port field, while typing (htmx)."""
        try:
            saved = system.web_values(read_config(editor.path)[1])
        except EditError:
            return HTMLResponse("")
        try:
            number = int(port.strip())
        except ValueError:
            number = 0
        address = address if address in system.ADDRESSES else str(saved["address"])
        if number == saved["port"] and address == saved["address"]:
            return HTMLResponse("")
        if not 0 < number <= 65535:
            problem = "Choose a whole number from 1 to 65535."
        else:
            problem = system.port_problem(address, number, keeper.used)
        return page(request, "_port.html", port=number, problem=problem)

    @app.post("/system/web/undo", response_class=HTMLResponse)
    def undo_web(request: Request):
        used = keeper.used
        if used is None:
            return system_done("")
        try:
            editor.change(lambda text: system.set_web_address(text, used))
        except EditError as error:
            return system_page(request, 409, str(error))
        keeper.saved(file_web())
        return system_done("web-undone")

    @app.post("/system/web/keep", response_class=HTMLResponse)
    def keep_web(request: Request):
        return system_done("web-kept" if keeper.keep(file_web()) else "")

    @app.post("/system/web/back", response_class=HTMLResponse)
    def web_back(request: Request):
        old = keeper.old
        if old is None:
            return system_done("")
        keeper.back_now()
        here = system.only_here(old) and not system.only_here(keeper.used)
        address = system.web_address(request.url.hostname or "", old)
        return page(request, "going_back.html", old=address, here=here)

    def password_page(request: Request, status: int = 200, problem: str | None = None):
        if not auth.login or auth.password_hash is None:
            return RedirectResponse("/system#web", status_code=303)
        return page(request, "password.html", status, problem=problem)

    @app.get("/system/password", response_class=HTMLResponse)
    def change_password_page(request: Request):
        return password_page(request)

    @app.post("/system/password", response_class=HTMLResponse)
    async def change_password(request: Request):
        if not auth.login or auth.password_hash is None:
            return RedirectResponse("/system#web", status_code=303)
        form = await request.form()
        password, again = str(form.get("password", "")), str(form.get("again", ""))
        problem = password_problem(password, again)
        if problem is None:
            try:
                stored = await run_in_threadpool(
                    auth.change_password, str(form.get("current", "")), password
                )
            except PasswordError as error:
                problem = str(error)
            else:
                # This browser stays logged in; the others need the new password.
                return logged_in(request, stored, "/system?done=password")
        return password_page(request, 400, problem)

    @app.get("/system/screen", response_class=HTMLResponse)
    def change_screen_page(request: Request):
        return screen_page(request)

    @app.post("/system/screen", response_class=HTMLResponse)
    async def change_screen(request: Request):
        form = await request.form()
        sent = {k: [str(v) for v in form.getlist(k)] for k in form}
        used = used_screen()
        try:
            await run_in_threadpool(editor.change, lambda text: system.with_screen(text, sent))
        except system.SectionErrors as error:
            return screen_page(request, 400, error, str(error))
        except EditError as error:
            return screen_page(request, 409, problem=str(error))
        file_display = system.file_display(read_config(editor.path)[1])
        if used is None or not system.waiting(file_display, editor.display):
            return system_done("saved")  # e.g. only the VCOM: it applies at once
        # Keep the screen in use for "Go back", unless it is a new one that does not answer
        # (then the one kept before is the one that worked).
        shown = summary()
        failing = shown is not None and shown.screen in ("failing", "paused")
        if system.previous(state_dir) is None or not failing:
            system.keep_previous(state_dir, used)
        return system_done("screen")

    @app.post("/system/screen/undo", response_class=HTMLResponse)
    def undo_screen(request: Request):
        used = used_screen()
        if used is None:
            return system_done("")
        try:
            editor.change(lambda text: system.set_screen(text, used))
        except EditError as error:
            return system_page(request, 409, str(error))
        if system.previous(state_dir) == used:
            system.forget_previous(state_dir)
        return system_done("undone")

    @app.post("/system/screen/back", response_class=HTMLResponse)
    def go_back(request: Request):
        before = system.previous(state_dir)
        if before is None:
            return system_page(request, 409, "No previous screen is kept.")
        try:
            editor.change(lambda text: system.set_screen(text, before))
        except EditError as error:
            return system_page(request, 409, str(error))
        system.forget_previous(state_dir)
        return restarting(request) if can_restart() else system_done("back")

    @app.post("/system/restart", response_class=HTMLResponse)
    def restart(request: Request):
        if not can_restart():
            return system_page(
                request, 409, "PaperPi was not started as a service, so it can't restart itself."
            )
        return restarting(request)

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
    "reload": "Asked PaperPi to load the config file again.",
    "applied": "Applied. PaperPi uses the changed config file now.",
    "applying": "Asked PaperPi to load the config file again. It does so between two "
    "screen writes, in a moment.",
}


#: What the Screen & system page says after a change (``?done=...``).
_SYSTEM_DONE = {
    "saved": "Saved. PaperPi applies the changes now.",
    "undone": "The new screen is undone: the config file names the screen in use again.",
    "back": "The previous screen is saved again. Restart PaperPi to use it.",
    "web-undone": "Undone: the web interface stays at its current address.",
    "web-kept": "Kept. The web interface stays at this address.",
    "password": "Password changed. Other phones and computers need to log in again.",
}


def _reload_command() -> tuple[str, bool]:
    """How to apply the config file from the command line, and whether PaperPi runs as a
    service (systemd sets ``INVOCATION_ID`` for the programs it starts)."""
    if os.environ.get("INVOCATION_ID"):
        return "sudo systemctl reload paperpi", True
    return f"kill -HUP {os.getpid()}", False


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
