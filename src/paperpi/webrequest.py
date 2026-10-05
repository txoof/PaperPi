"""The one helper every plugin uses for web requests.

The limits come from ``docs/decisions/errors-and-time-limits.md`` and :mod:`paperpi.limits`:

- 10 seconds to connect,
- 30 seconds in total, including one retry after 5 seconds,
- at most 20 MB in the answer, after unpacking.

Only failures that may go away by themselves are retried: no connection, no answer in time,
or the server answering "busy" or "server error" (status 429 or 5xx). An answer like "not
found" (404) is not retried.

Built on Python's own ``http.client`` (the part of ``urllib`` that talks to the server), so
PaperPi needs no extra package. Looking up the server's address (DNS) has no time limit of
its own in Python; the plugin's own time limit stops an update that hangs there.

A plugin uses it like this::

    from paperpi import webrequest

    answer = webrequest.get(url, contact=context.settings.email)
    forecast = answer.json()
"""

from __future__ import annotations

import http.client
import json
import ssl
import time
import zlib
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any
from urllib.parse import urljoin, urlsplit

from . import __version__, limits

#: Most redirects ("this moved to ...") followed for one request.
MAX_REDIRECTS = 3

#: Answers that mean "try again later": too many requests, and server errors.
_TRY_AGAIN = {429, 500, 502, 503, 504}
_REDIRECTS = {301, 302, 303, 307, 308}
_CHUNK = 64 * 1024


class WebError(Exception):
    """A web request failed. The message says why, and names the server."""


class _TryAgain(WebError):
    """A failure that may go away by itself, so it is worth one retry."""


@dataclass(frozen=True)
class Answer:
    """A successful answer from a web server."""

    status: int
    """200 (or another 2xx), or 304: nothing changed since ``if_modified_since``."""
    body: bytes
    """The content, already unpacked. Empty for 304."""
    headers: Mapping[str, str]
    """The answer's headers, with lowercase names."""
    url: str
    """The address that answered, after any redirects."""

    @property
    def not_modified(self) -> bool:
        """True when the server says nothing changed since ``if_modified_since``."""
        return self.status == 304

    @property
    def last_modified(self) -> str | None:
        """When the content last changed, as the server wrote it. Pass it back as
        ``if_modified_since`` next time."""
        return self.headers.get("last-modified")

    def json(self) -> Any:
        """The content read as JSON."""
        try:
            return json.loads(self.body)
        except ValueError as error:
            raise WebError(f"{_where(self.url)} did not send valid JSON: {error}") from None


def user_agent(contact: str | None = None) -> str:
    """How PaperPi introduces itself to web servers. Some services, like met.no, require
    contact details, so they can ask before they block a program that misbehaves."""
    text = f"PaperPi/{__version__} (+https://github.com/txoof/PaperPi"
    return f"{text}; {contact})" if contact else f"{text})"


def get(
    url: str,
    *,
    contact: str | None = None,
    headers: Mapping[str, str] | None = None,
    if_modified_since: str | None = None,
    max_bytes: int = limits.WEB_ANSWER_BYTES,
    connect_timeout: float = limits.WEB_CONNECT,
    total: float = limits.WEB_TOTAL,
    retry_wait: float = limits.WEB_RETRY_WAIT,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> Answer:
    """Download ``url`` (``http`` or ``https``) and return the answer.

    ``contact`` (an email address or web address) is added to the User-Agent header.
    ``if_modified_since`` is the ``last_modified`` of an earlier answer; if nothing changed
    since, the answer has status 304 and no content. ``clock`` and ``sleep`` are for tests.

    Raises :class:`WebError` with a plain message when the request fails.
    """
    sent = {
        "User-Agent": user_agent(contact),
        "Accept-Encoding": "gzip",
        **(headers or {}),
    }
    if if_modified_since:
        sent["If-Modified-Since"] = if_modified_since
    deadline = clock() + total

    def attempt() -> Answer:
        return _follow(url, sent, deadline, connect_timeout, total, max_bytes, clock)

    try:
        return attempt()
    except _TryAgain as first:
        if clock() + retry_wait >= deadline:
            raise WebError(str(first)) from None
        sleep(retry_wait)
        try:
            return attempt()
        except _TryAgain as second:
            raise WebError(f"{second} (also on the retry)") from None


def _follow(url, sent, deadline, connect_timeout, total, max_bytes, clock) -> Answer:
    """One attempt, following up to :data:`MAX_REDIRECTS` redirects."""
    for _ in range(MAX_REDIRECTS + 1):
        answer = _once(url, sent, deadline, connect_timeout, total, max_bytes, clock)
        if isinstance(answer, Answer):
            return answer
        new = urljoin(url, answer)
        if urlsplit(url).scheme == "https" and urlsplit(new).scheme != "https":
            raise WebError(f"{_where(url)} redirected from https to an unsafe address")
        url = new
    raise WebError(f"{_where(url)}: more than {MAX_REDIRECTS} redirects")


def _once(url, sent, deadline, connect_timeout, total, max_bytes, clock) -> Answer | str:
    """One request. Returns the answer, or the new address for a redirect."""
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise WebError(f"not a web address: {url!r}")
    where = _where(url)
    remaining = deadline - clock()
    if remaining <= 0:
        raise _TryAgain(f"{where} did not answer within {total:g} s")
    timeout = min(connect_timeout, remaining)
    if parts.scheme == "https":
        connection = http.client.HTTPSConnection(
            parts.hostname, parts.port, timeout=timeout, context=ssl.create_default_context()
        )
    else:
        connection = http.client.HTTPConnection(parts.hostname, parts.port, timeout=timeout)
    connected = False
    try:
        connection.connect()
        connected = True
        sock = connection.sock  # kept: http.client drops it once the answer is read
        _limit(sock, deadline, clock)
        path = parts.path or "/"
        connection.request("GET", f"{path}?{parts.query}" if parts.query else path, headers=sent)
        response = connection.getresponse()
        status = response.status
        if status in _REDIRECTS:
            location = response.getheader("Location")
            if not location:
                raise WebError(f"{where} sent a redirect without an address")
            return location
        if status in _TRY_AGAIN:
            raise _TryAgain(f"{where} answered {status} {response.reason}")
        if status != 304 and not 200 <= status < 300:
            raise WebError(f"{where} answered {status} {response.reason}")
        found = {name.lower(): value for name, value in response.getheaders()}
        if status == 304:
            return Answer(status, b"", found, url)
        return Answer(
            status, _read(response, sock, found, where, deadline, max_bytes, clock), found, url
        )
    except TimeoutError:
        if connected:
            raise _TryAgain(f"{where} did not answer within {total:g} s") from None
        raise _TryAgain(f"could not connect to {where} within {timeout:g} s") from None
    except ssl.SSLError as error:
        # A certificate that can't be checked won't fix itself in 5 seconds.
        raise WebError(f"no safe connection to {where}: {error}") from None
    except (OSError, http.client.HTTPException) as error:
        raise _TryAgain(f"could not reach {where}: {error}") from None
    finally:
        connection.close()


def _read(response, sock, found, where, deadline, max_bytes, clock) -> bytes:
    """Read the content in pieces, so neither the time limit nor the size limit can be
    passed by much. Unpacks gzip on the way."""
    too_big = WebError(f"{where} sent more than {max_bytes:,} bytes")
    encoding = found.get("content-encoding", "identity").lower()
    if encoding == "gzip":
        unpack = zlib.decompressobj(16 + zlib.MAX_WBITS)
    elif encoding == "identity":
        unpack = None
        if int(found.get("content-length") or 0) > max_bytes:
            raise too_big
    else:
        raise WebError(f"{where} packed its answer as {encoding!r}, which PaperPi can't read")
    pieces, size = [], 0
    while not response.isclosed():  # closes itself after the last piece
        _limit(sock, deadline, clock)
        piece = response.read(_CHUNK)
        if not piece:
            break
        if unpack:
            try:
                piece = unpack.decompress(piece, max_bytes - size + 1)
            except zlib.error as error:
                raise WebError(f"{where} sent broken gzip data: {error}") from None
            if unpack.unconsumed_tail:
                raise too_big
        size += len(piece)
        if size > max_bytes:
            raise too_big
        pieces.append(piece)
    return b"".join(pieces)


def _limit(sock, deadline, clock) -> None:
    """Let the next wait on the connection's socket last no longer than the time that is left."""
    remaining = deadline - clock()
    if remaining <= 0:
        raise TimeoutError
    sock.settimeout(remaining)


def _where(url: str) -> str:
    """The server and path, for messages. The query is left out: it may hold an API key."""
    parts = urlsplit(url)
    return f"{parts.netloc}{parts.path}"
