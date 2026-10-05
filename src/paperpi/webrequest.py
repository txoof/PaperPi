"""The one helper every plugin uses for web requests.

The limits come from ``docs/decisions/errors-and-time-limits.md`` and :mod:`paperpi.limits`:

- 10 seconds to connect,
- 30 seconds in total, including one retry after 5 seconds,
- at most 5 MB in the answer, after unpacking (a plugin can ask for more, e.g. for images).

Only failures that may go away by themselves are retried: no connection, no answer in time,
a connection that breaks off, or the server answering "too many requests" (429) or "server
error" (500, 502, 503, 504). An answer like "not found" (404) is not retried.

Built on Python's ``http.client``, the standard module that ``urllib`` also uses to talk to
web servers, so PaperPi needs no extra package. Looking up the server's address (DNS) has
no time limit of its own in Python; the plugin's own time limit stops an update that hangs
there.

A plugin uses it like this::

    from paperpi import webrequest

    answer = webrequest.get(url, contact=context.settings.email)
    forecast = answer.json()
"""

from __future__ import annotations

import functools
import http.client
import json
import socket
import ssl
import threading
import time
import zlib
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote, urljoin, urlsplit

from . import __version__, limits

#: Most redirects ("this moved to ...") followed for one request.
MAX_REDIRECTS = 3

#: Answers that mean "try again later": too many requests, and server errors.
_TRY_AGAIN = {429, 500, 502, 503, 504}
_REDIRECTS = {301, 302, 303, 307, 308}
_CHUNK = 64 * 1024
# Characters left as they are when a path or query is made safe to send.
_SAFE = "/%:@!$&'()*+,;=-._~?"


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
        """When the content last changed, as the server wrote it (``None`` if it didn't
        say). Pass it back as ``if_modified_since`` next time."""
        return self.headers.get("last-modified")

    def json(self) -> Any:
        """The content read as JSON."""
        if self.not_modified:
            raise WebError(f"{_where(self.url)}: no content, nothing changed (check not_modified)")
        try:
            return json.loads(self.body)
        except ValueError:
            raise WebError(f"{_where(self.url)} did not send valid JSON") from None


def user_agent(contact: str | None = None) -> str:
    """How PaperPi introduces itself to web servers, in the User-Agent header (the line in
    every request that names the program). Some services, like met.no, require contact
    details, so they can ask before they block a program that misbehaves."""
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

    ``contact`` (an email or web address) is added to the User-Agent header. ``headers``
    are sent as well, but only to the server of ``url``: after a redirect to another server
    they are left out, so an API key can't reach it. ``if_modified_since`` is the
    ``last_modified`` of an earlier answer; if nothing changed since, the answer has status
    304 and no content. ``clock`` and ``sleep`` are for tests.

    Raises :class:`WebError` with a plain message when the request fails.
    """
    own = {"User-Agent": user_agent(contact), "Accept-Encoding": "gzip"}
    if if_modified_since:
        own["If-Modified-Since"] = if_modified_since
    # Header names don't depend on upper or lower case, so a plugin's "accept-encoding"
    # replaces PaperPi's instead of being sent as a second one.
    extra = dict(headers or {})
    replaced = {name.lower() for name in extra}
    sent = {name: value for name, value in own.items() if name.lower() not in replaced} | extra
    deadline = clock() + total

    def attempt() -> Answer:
        return _follow(url, sent, own, deadline, connect_timeout, total, max_bytes, clock)

    try:
        return attempt()
    except _TryAgain as first:
        # A retry is only worth it with enough time left to connect and get an answer.
        if deadline - clock() - retry_wait < retry_wait:
            raise WebError(str(first)) from None
        sleep(retry_wait)
        try:
            return attempt()
        except _TryAgain as second:
            raise WebError(f"{first} (on the retry: {second})") from None


def _follow(url, sent, own, deadline, connect_timeout, total, max_bytes, clock) -> Answer:
    """One attempt, following up to :data:`MAX_REDIRECTS` redirects."""
    first = _origin(url)
    for _ in range(MAX_REDIRECTS + 1):
        headers = sent if _origin(url) == first else own
        answer = _once(url, headers, deadline, connect_timeout, total, max_bytes, clock)
        if isinstance(answer, Answer):
            return answer
        new = urljoin(url, answer)
        if urlsplit(url).scheme == "https" and urlsplit(new).scheme != "https":
            raise WebError(f"{_where(url)} redirected from https to an unsafe address")
        url = new
    raise WebError(f"{_where(url)}: more than {MAX_REDIRECTS} redirects")


def _once(url, sent, deadline, connect_timeout, total, max_bytes, clock) -> Answer | str:
    """One request. Returns the answer, or the new address for a redirect."""
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError:
        raise WebError("not a web address: the port is not a number from 0 to 65535") from None
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise WebError("not a web address: it must start with http:// or https://")
    where = _where(url)
    if deadline - clock() <= 0:
        raise _TryAgain(f"{where} did not answer within {total:g} s")
    connect_by = min(clock() + connect_timeout, deadline)
    if parts.scheme == "https":
        connection = http.client.HTTPSConnection(parts.hostname, port, context=_tls())
    else:
        connection = http.client.HTTPConnection(parts.hostname, port)
    connection._create_connection = functools.partial(_connect, until=connect_by, clock=clock)
    target = quote(parts.path or "/", safe=_SAFE)
    if parts.query:
        target += "?" + quote(parts.query, safe=_SAFE)
    watch = None
    connected = False
    try:
        connection.connect()
        connected = True
        sock = connection.sock  # kept: http.client drops it once the answer is read
        watch = _shut_at(sock, deadline - clock())
        _limit(sock, deadline, clock)
        connection.request("GET", target, headers=sent)
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
        body = _read(response, sock, found, where, deadline, max_bytes, clock)
        return Answer(status, body, found, url)
    except (TimeoutError, OSError, http.client.HTTPException) as error:
        if connected and deadline - clock() <= 0.05:
            # Too slow, or the watch closed the connection at the time limit.
            raise _TryAgain(f"{where} did not answer within {total:g} s") from None
        if isinstance(error, http.client.InvalidURL):
            raise WebError(f"{where}: the address has characters that can't be sent") from None
        if isinstance(error, ssl.SSLCertVerificationError):
            # A certificate that can't be checked won't fix itself in 5 seconds.
            raise WebError(f"no safe connection to {where}: {error.verify_message}") from None
        if isinstance(error, TimeoutError) and not connected:
            raise _TryAgain(f"could not connect to {where} within {connect_timeout:g} s") from None
        raise _TryAgain(f"could not reach {where}: {type(error).__name__}") from None
    except (ValueError, UnicodeError):
        # For example a header with a line break, or letters that can't be sent.
        raise WebError(f"{where}: the request has characters that can't be sent") from None
    finally:
        if watch:
            watch.cancel()
        connection.close()


def _connect(address, timeout=None, source_address=None, *, until, clock):
    """Connect to the first of the server's addresses that answers. All addresses together
    get the connect time, not each one (Python's own way gives each the full time)."""
    host, port = address
    last: OSError = TimeoutError()
    for family, kind, proto, _, place in socket.getaddrinfo(host, port, 0, socket.SOCK_STREAM):
        left = until - clock()
        if left <= 0:
            break
        sock = socket.socket(family, kind, proto)
        try:
            sock.settimeout(left)
            sock.connect(place)
            return sock
        except OSError as error:
            sock.close()
            last = error
    raise last


def _shut_at(sock, seconds: float) -> threading.Timer:
    """Close the connection when the time limit is reached, even while a read is waiting.
    Needed because a server that sends one byte at a time resets every socket wait."""

    def shut():
        try:
            sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass

    watch = threading.Timer(max(seconds, 0), shut)
    watch.daemon = True
    watch.start()
    return watch


def _read(response, sock, found, where, deadline, max_bytes, clock) -> bytes:
    """Read the content in pieces, keeping to the size limit. Unpacks gzip (the common way
    servers pack answers to send fewer bytes) on the way."""
    too_big = WebError(f"{where} sent more than {max_bytes:,} bytes")
    encoding = found.get("content-encoding", "identity").lower()
    if encoding == "gzip":
        unpack = zlib.decompressobj(16 + zlib.MAX_WBITS)
    elif encoding == "identity":
        unpack = None
        if (response.length or 0) > max_bytes:
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
            except zlib.error:
                raise WebError(f"{where} sent broken gzip data") from None
            if unpack.unconsumed_tail:
                raise too_big
        size += len(piece)
        if size > max_bytes:
            raise too_big
        pieces.append(piece)
        if unpack and unpack.eof:
            break  # anything after the end of the gzip data is not read
    if deadline - clock() <= 0:
        raise TimeoutError  # the watch closed the connection: the content may be cut off
    if unpack and not unpack.eof:
        raise WebError(f"{where} sent incomplete gzip data")
    return b"".join(pieces)


def _limit(sock, deadline, clock) -> None:
    """Let the next wait on the connection's socket (the operating system's end of the
    connection) last no longer than the time that is left."""
    remaining = deadline - clock()
    if remaining <= 0:
        raise TimeoutError
    sock.settimeout(remaining)


@functools.cache
def _tls() -> ssl.SSLContext:
    """Settings for secure (https) connections: certificates are checked. Made once."""
    return ssl.create_default_context()


def _origin(url: str) -> tuple:
    parts = urlsplit(url)
    try:
        return parts.scheme, parts.hostname, parts.port
    except ValueError:
        return parts.scheme, parts.hostname, None


def _where(url: str) -> str:
    """The server's name (and port), for messages. The rest is left out: the path or the
    query may hold an API key or a location, and the address may hold a password."""
    parts = urlsplit(url)
    host = parts.hostname or "?"
    try:
        port = parts.port
    except ValueError:
        port = None
    return f"{host}:{port}" if port else host
