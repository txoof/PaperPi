"""The shared web-request helper (paperpi.webrequest), tested against small local servers."""

import gzip
import json
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from paperpi import __version__, webrequest
from paperpi.webrequest import WebError


class Server:
    """A web server on this computer. ``answers`` maps a path to a list of answers, used in
    turn (the last one repeats). An answer is (status, headers, body) or a function that
    gets the handler and writes its own answer."""

    def __init__(self):
        self.answers = {}
        self.requests = []  # (path, headers) of every request; headers keep repeated names
        server = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def do_GET(self):
                server.requests.append((self.path, self.headers))
                todo = server.answers.get(self.path.split("?")[0], [(404, {}, b"")])
                answer = todo.pop(0) if len(todo) > 1 else todo[0]
                if callable(answer):
                    answer(self)
                    return
                status, headers, body = answer
                self.send_response(status)
                for name, value in headers.items():
                    self.send_header(name, value)
                if "Content-Length" not in headers:
                    self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass

        class Quiet(ThreadingHTTPServer):
            def handle_error(self, request, client_address):
                pass  # the helper hangs up early on purpose in some tests

        self.http = Quiet(("127.0.0.1", 0), Handler)
        self.http.daemon_threads = True
        self.url = f"http://127.0.0.1:{self.http.server_port}"
        threading.Thread(target=self.http.serve_forever, args=(0.05,), daemon=True).start()

    def close(self):
        self.http.shutdown()
        self.http.server_close()


@pytest.fixture
def server():
    s = Server()
    yield s
    s.close()


@pytest.fixture
def other():
    s = Server()
    yield s
    s.close()


class FakeSleep:
    """Records waits instead of waiting, so retry tests don't take 5 seconds."""

    def __init__(self):
        self.waits = []

    def __call__(self, seconds):
        self.waits.append(seconds)


def raw(*parts, pause=0.0):
    """An answer written by hand, piece by piece, with ``pause`` seconds between pieces.
    The connection is closed afterwards."""

    def answer(handler):
        for part in parts:
            try:
                handler.wfile.write(part)
                handler.wfile.flush()
            except OSError:
                return  # the client hung up
            time.sleep(pause)
        handler.close_connection = True

    return answer


# --- Answers ---------------------------------------------------------------------------------


def test_gets_json_and_introduces_itself(server):
    server.answers["/f"] = [(200, {"Last-Modified": "Mon, 05 Oct 2026 10:00:00 GMT"}, b'{"a": 1}')]
    answer = webrequest.get(server.url + "/f?lat=52.52", contact="me@example.com")
    assert answer.status == 200
    assert answer.json() == {"a": 1}
    assert answer.last_modified == "Mon, 05 Oct 2026 10:00:00 GMT"
    assert not answer.not_modified
    path, headers = server.requests[0]
    assert path == "/f?lat=52.52"
    assert headers["User-Agent"] == (
        f"PaperPi/{__version__} (+https://github.com/txoof/PaperPi; me@example.com)"
    )
    assert headers["Accept-Encoding"] == "gzip"
    assert "If-Modified-Since" not in headers


def test_user_agent_without_contact():
    assert webrequest.user_agent() == f"PaperPi/{__version__} (+https://github.com/txoof/PaperPi)"


def test_unpacks_gzip(server):
    data = json.dumps({"hours": list(range(1000))}).encode()
    server.answers["/z"] = [(200, {"Content-Encoding": "gzip"}, gzip.compress(data))]
    assert webrequest.get(server.url + "/z").body == data


def test_answer_without_length_and_in_chunks(server):
    """Servers may leave out the length, or send the content in chunks of known size."""
    head = b"HTTP/1.1 200 OK\r\nConnection: close\r\n"
    server.answers["/nolength"] = [raw(head + b"\r\nhello")]
    chunks = b"Transfer-Encoding: chunked\r\n\r\n5\r\nhello\r\n6\r\n world\r\n0\r\n\r\n"
    server.answers["/chunked"] = [raw(head + chunks)]
    assert webrequest.get(server.url + "/nolength").body == b"hello"
    assert webrequest.get(server.url + "/chunked").body == b"hello world"


def test_not_modified_since(server):
    server.answers["/f"] = [(304, {"ETag": "x"}, b"")]
    sleep = FakeSleep()
    answer = webrequest.get(
        server.url + "/f", if_modified_since="Mon, 05 Oct 2026 10:00:00 GMT", sleep=sleep
    )
    assert answer.not_modified
    assert answer.body == b""
    assert answer.headers["etag"] == "x"
    assert server.requests[0][1]["If-Modified-Since"] == "Mon, 05 Oct 2026 10:00:00 GMT"
    assert sleep.waits == []
    with pytest.raises(WebError, match="nothing changed"):
        answer.json()


def test_bad_json(server):
    server.answers["/f"] = [(200, {}, b"<html>")]
    with pytest.raises(WebError, match="did not send valid JSON"):
        webrequest.get(server.url + "/f").json()


def test_bad_length_header_is_not_a_crash(server):
    server.answers["/f"] = [raw(b"HTTP/1.1 200 OK\r\nContent-Length: abc\r\n\r\nhello")]
    assert webrequest.get(server.url + "/f").body == b"hello"


# --- Headers the plugin sends ----------------------------------------------------------------


def test_plugin_headers_replace_ours_whatever_their_case(server):
    server.answers["/f"] = [(200, {}, b"ok")]
    webrequest.get(server.url + "/f", headers={"accept-encoding": "identity", "X-Key": "k"})
    headers = server.requests[0][1]
    assert headers.get_all("Accept-Encoding") == ["identity"]
    assert headers["X-Key"] == "k"


def test_plugin_headers_stay_with_the_first_server(server, other):
    server.answers["/start"] = [(302, {"Location": other.url + "/end"}, b"")]
    other.answers["/end"] = [(200, {}, b"there")]
    answer = webrequest.get(server.url + "/start", headers={"Authorization": "Bearer SECRET"})
    assert answer.body == b"there"
    assert server.requests[0][1]["Authorization"] == "Bearer SECRET"
    assert "Authorization" not in other.requests[0][1]
    assert other.requests[0][1]["User-Agent"].startswith("PaperPi/")


def test_header_with_a_line_break(server):
    with pytest.raises(WebError, match="characters that can't be sent") as failed:
        webrequest.get(server.url + "/f", headers={"X-Key": "SECRET\r\nEvil: 1"})
    assert "SECRET" not in str(failed.value)


# --- Retries ---------------------------------------------------------------------------------


@pytest.mark.parametrize("status", [429, 500, 502, 503, 504])
def test_retries_once_after_try_again_later(server, status):
    server.answers["/f"] = [(status, {}, b"busy"), (200, {}, b"ok")]
    sleep = FakeSleep()
    assert webrequest.get(server.url + "/f", sleep=sleep).body == b"ok"
    assert sleep.waits == [5.0]
    assert len(server.requests) == 2


@pytest.mark.parametrize("status", [400, 403, 404, 501])
def test_other_errors_are_not_retried(server, status):
    server.answers["/f"] = [(status, {}, b"")]
    sleep = FakeSleep()
    with pytest.raises(WebError, match=rf"^127\.0\.0\.1:\d+ answered {status} "):
        webrequest.get(server.url + "/f", sleep=sleep)
    assert sleep.waits == []
    assert len(server.requests) == 1


def test_gives_up_after_one_retry(server):
    server.answers["/f"] = [(500, {}, b"")]
    with pytest.raises(WebError, match=r"answered 500 .*\(on the retry: .*answered 500"):
        webrequest.get(server.url + "/f", sleep=FakeSleep())
    assert len(server.requests) == 2


def test_no_server_is_retried():
    # A socket that is bound but not listening refuses connections.
    closed = socket.socket()
    closed.bind(("127.0.0.1", 0))
    port = closed.getsockname()[1]
    sleep = FakeSleep()
    try:
        with pytest.raises(WebError, match=rf"could not reach 127.0.0.1:{port}.*\(on the retry: "):
            webrequest.get(f"http://127.0.0.1:{port}/", sleep=sleep)
    finally:
        closed.close()
    assert sleep.waits == [5.0]


def test_broken_secure_connection_is_retried(server):
    # The local server doesn't speak https, so the secure connection fails at once.
    sleep = FakeSleep()
    with pytest.raises(WebError, match="could not reach 127.0.0.1"):
        webrequest.get(server.url.replace("http:", "https:") + "/f", sleep=sleep)
    assert sleep.waits == [5.0]


@pytest.mark.parametrize(("fails_at", "retried"), [(20.0, True), (21.0, False), (26.0, False)])
def test_the_retry_counts_in_the_total(server, fails_at, retried):
    """30 s in total: a retry needs the 5 s wait plus at least 5 s to try."""
    now = [0.0]

    def busy(handler):
        now[0] = fails_at  # the first attempt took this long
        handler.send_response(503)
        handler.send_header("Content-Length", "0")
        handler.end_headers()

    server.answers["/f"] = [busy, (200, {}, b"ok")]

    def sleep(seconds):
        now[0] += seconds

    if retried:
        assert webrequest.get(server.url + "/f", clock=lambda: now[0], sleep=sleep).body == b"ok"
    else:
        with pytest.raises(WebError, match="answered 503") as failed:
            webrequest.get(server.url + "/f", clock=lambda: now[0], sleep=sleep)
        assert "on the retry" not in str(failed.value)
    assert len(server.requests) == (2 if retried else 1)


# --- Time limits -----------------------------------------------------------------------------


def test_connect_time_is_shared_by_all_addresses(monkeypatch):
    """A server name with three addresses that don't answer still gets 10 s, not 30 s."""
    now = [0.0]
    timeouts = []

    class Silent:
        def __init__(self, *args):
            self.timeout = None

        def settimeout(self, seconds):
            self.timeout = seconds

        def connect(self, place):
            timeouts.append(self.timeout)
            now[0] += min(self.timeout, 4)  # each address waits 4 s, then gives up
            raise TimeoutError

        def close(self):
            pass

    addresses = [
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", (f"192.0.2.{i}", 80)) for i in (1, 2, 3)
    ]
    monkeypatch.setattr(webrequest.socket, "getaddrinfo", lambda *a: addresses)
    monkeypatch.setattr(webrequest.socket, "socket", Silent)
    with pytest.raises(WebError, match=r"could not connect to example\.com within 10 s"):
        webrequest.get("http://example.com/", clock=lambda: now[0], sleep=FakeSleep())
    assert timeouts[:3] == [10.0, 6.0, 2.0]


def test_slow_answer_is_cut_off(server):
    server.answers["/slow"] = [raw(b"HTTP/1.1 200 OK\r\nContent-Length: 100\r\n\r\nx", pause=2)]
    start = time.monotonic()
    with pytest.raises(WebError, match=r"did not answer within 0\.5 s"):
        webrequest.get(server.url + "/slow", total=0.5, retry_wait=0.1)
    assert time.monotonic() - start < 1.5


@pytest.mark.parametrize(
    "answer",
    [
        # Content one byte at a time: every byte would start a socket wait anew.
        [b"HTTP/1.1 200 OK\r\nContent-Length: 40\r\n\r\n"] + [b"x"] * 40,
        [b"HTTP/1.1 200 OK\r\nConnection: close\r\n\r\n"] + [b"x"] * 40,
        [b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n"] + [b"1\r\nx\r\n"] * 40,
        # The headers one byte at a time.
        [bytes([c]) for c in b"HTTP/1.1 200 OK\r\nX-Slow: " + b"y" * 40],
    ],
    ids=["length", "no-length", "chunked", "headers"],
)
def test_a_server_that_sends_slowly_is_cut_off(server, answer):
    server.answers["/drip"] = [raw(*answer, pause=0.05)]
    start = time.monotonic()
    with pytest.raises(WebError, match=r"did not answer within 0\.5 s"):
        webrequest.get(server.url + "/drip", total=0.5, retry_wait=0.1)
    assert time.monotonic() - start < 1.2


# --- Size and packing ------------------------------------------------------------------------


def test_too_big_by_length(server):
    server.answers["/big"] = [(200, {}, b"x" * 2000)]
    with pytest.raises(WebError, match="more than 1,000 bytes"):
        webrequest.get(server.url + "/big", max_bytes=1000)


@pytest.mark.parametrize(
    "head",
    [b"Connection: close\r\n\r\n", b"Transfer-Encoding: chunked\r\n\r\n"],
    ids=["no-length", "chunked"],
)
def test_too_big_without_a_length(server, head):
    piece = b"x" * 500
    body = piece * 4 if b"close" in head else (b"1f4\r\n" + piece + b"\r\n") * 4 + b"0\r\n\r\n"
    server.answers["/big"] = [raw(b"HTTP/1.1 200 OK\r\n" + head + body)]
    with pytest.raises(WebError, match="more than 1,000 bytes"):
        webrequest.get(server.url + "/big", max_bytes=1000)


def test_too_big_after_unpacking(server):
    bomb = gzip.compress(b"\0" * 1_000_000)  # small packed, large unpacked
    server.answers["/bomb"] = [(200, {"Content-Encoding": "gzip"}, bomb)]
    with pytest.raises(WebError, match="more than 10,000 bytes"):
        webrequest.get(server.url + "/bomb", max_bytes=10_000)


def test_nothing_after_the_end_of_gzip_is_read(server):
    packed = gzip.compress(b"forecast")
    junk = b"\0" * 2_000_000
    server.answers["/z"] = [(200, {"Content-Encoding": "gzip"}, packed + junk)]
    assert webrequest.get(server.url + "/z", max_bytes=1000).body == b"forecast"


def test_cut_off_gzip(server):
    packed = gzip.compress(json.dumps(list(range(500))).encode())
    server.answers["/z"] = [(200, {"Content-Encoding": "gzip"}, packed[: len(packed) // 2])]
    with pytest.raises(WebError, match="incomplete gzip"):
        webrequest.get(server.url + "/z")


def test_broken_gzip(server):
    server.answers["/z"] = [(200, {"Content-Encoding": "gzip"}, b"not gzip at all")]
    with pytest.raises(WebError, match="broken gzip"):
        webrequest.get(server.url + "/z")


def test_unknown_packing(server):
    server.answers["/z"] = [(200, {"Content-Encoding": "br"}, b"...")]
    with pytest.raises(WebError, match="packed its answer as 'br'"):
        webrequest.get(server.url + "/z")


# --- Redirects -------------------------------------------------------------------------------


def test_follows_redirects(server):
    server.answers["/old"] = [(301, {"Location": "/new"}, b"")]
    server.answers["/new"] = [(200, {}, b"here")]
    answer = webrequest.get(server.url + "/old")
    assert answer.body == b"here"
    assert answer.url == server.url + "/new"


def test_too_many_redirects(server):
    server.answers["/loop"] = [(302, {"Location": "/loop"}, b"")]
    with pytest.raises(WebError, match="more than 3 redirects"):
        webrequest.get(server.url + "/loop")
    assert len(server.requests) == 4


def test_redirect_without_address(server):
    server.answers["/r"] = [(302, {}, b"")]
    with pytest.raises(WebError, match="redirect without an address"):
        webrequest.get(server.url + "/r")


def test_no_redirect_from_https_to_http(monkeypatch):
    calls = []

    def once(url, *args):
        calls.append(url)
        return "http://example.com/plain"

    monkeypatch.setattr(webrequest, "_once", once)
    with pytest.raises(WebError, match="from https to an unsafe address"):
        webrequest.get("https://example.com/start")
    assert calls == ["https://example.com/start"]


# --- Addresses and messages ------------------------------------------------------------------


def test_spaces_and_other_letters_are_sent_safely(server):
    server.answers["/%E1%8D%8A%E1%8B%B0%E1%88%8D"] = [(200, {}, b"ok")]
    assert webrequest.get(server.url + "/ፊደል?q=Addis Ababa").body == b"ok"
    assert server.requests[0][0] == "/%E1%8D%8A%E1%8B%B0%E1%88%8D?q=Addis%20Ababa"


def test_messages_name_only_the_server(server):
    with pytest.raises(WebError) as failed:
        webrequest.get(server.url.replace("//", "//user:PASSWORD@") + "/key/SECRET1?appid=SECRET2")
    message = str(failed.value)
    assert "SECRET" not in message
    assert "PASSWORD" not in message
    assert message.startswith("127.0.0.1:")


@pytest.mark.parametrize(
    "url",
    ["ftp://example.com/x", "file:///etc/passwd", "example.com", "http://example.com:99999/"],
)
def test_only_web_addresses(url):
    with pytest.raises(WebError, match="not a web address"):
        webrequest.get(url)
