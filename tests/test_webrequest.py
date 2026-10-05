"""The shared web-request helper (paperpi.webrequest), tested against a small local server."""

import gzip
import json
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
        self.requests = []  # (path, headers) of every request
        server = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                server.requests.append((self.path, dict(self.headers)))
                todo = server.answers.get(self.path.split("?")[0], [(404, {}, b"")])
                answer = todo.pop(0) if len(todo) > 1 else todo[0]
                if callable(answer):
                    answer(self)
                    return
                status, headers, body = answer
                self.send_response(status)
                for name, value in headers.items():
                    self.send_header(name, value)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass

        self.http = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
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


class FakeSleep:
    """Records waits instead of waiting, so retry tests don't take 5 seconds."""

    def __init__(self):
        self.waits = []

    def __call__(self, seconds):
        self.waits.append(seconds)


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


def test_user_agent_without_contact():
    assert webrequest.user_agent() == f"PaperPi/{__version__} (+https://github.com/txoof/PaperPi)"


def test_unpacks_gzip(server):
    data = json.dumps({"hours": list(range(1000))}).encode()
    server.answers["/z"] = [(200, {"Content-Encoding": "gzip"}, gzip.compress(data))]
    assert webrequest.get(server.url + "/z").body == data


def test_not_modified_since(server):
    server.answers["/f"] = [(304, {}, b"")]
    answer = webrequest.get(server.url + "/f", if_modified_since="Mon, 05 Oct 2026 10:00:00 GMT")
    assert answer.not_modified
    assert answer.body == b""
    assert server.requests[0][1]["If-Modified-Since"] == "Mon, 05 Oct 2026 10:00:00 GMT"


def test_retries_once_after_a_server_error(server):
    server.answers["/f"] = [(503, {}, b"busy"), (200, {}, b"ok")]
    sleep = FakeSleep()
    assert webrequest.get(server.url + "/f", sleep=sleep).body == b"ok"
    assert sleep.waits == [5.0]
    assert len(server.requests) == 2


def test_gives_up_after_one_retry(server):
    server.answers["/f"] = [(500, {}, b"")]
    sleep = FakeSleep()
    with pytest.raises(WebError, match=r"answered 500 .*also on the retry"):
        webrequest.get(server.url + "/f", sleep=sleep)
    assert len(server.requests) == 2


def test_not_found_is_not_retried(server):
    sleep = FakeSleep()
    with pytest.raises(WebError, match=r"127\.0\.0\.1:\d+/missing answered 404"):
        webrequest.get(server.url + "/missing", sleep=sleep)
    assert sleep.waits == []
    assert len(server.requests) == 1


def test_no_server_is_retried():
    # Port 9 on this computer has nothing listening, so the connection is refused at once.
    sleep = FakeSleep()
    with pytest.raises(WebError, match="could not reach 127.0.0.1:9.*also on the retry"):
        webrequest.get("http://127.0.0.1:9/", sleep=sleep)
    assert sleep.waits == [5.0]


def test_no_retry_when_the_time_is_used_up(server):
    server.answers["/f"] = [(503, {}, b"")]
    now = [0.0]

    def sleep(seconds):
        now[0] += seconds

    def clock():
        now[0] += 13  # every look at the clock costs 13 s
        return now[0]

    with pytest.raises(WebError) as failed:
        webrequest.get(server.url + "/f", clock=clock, sleep=sleep)
    assert "also on the retry" not in str(failed.value)
    assert len(server.requests) == 1


def test_slow_answer_is_cut_off(server):
    def slow(handler):
        handler.send_response(200)
        handler.send_header("Content-Length", "100")
        handler.end_headers()
        handler.wfile.write(b"x")
        handler.wfile.flush()
        time.sleep(2)

    server.answers["/slow"] = [slow]
    start = time.monotonic()
    with pytest.raises(WebError, match=r"did not answer within 0\.5 s"):
        webrequest.get(server.url + "/slow", total=0.5, retry_wait=0.1)
    assert time.monotonic() - start < 1.5


def test_too_big_by_length(server):
    server.answers["/big"] = [(200, {}, b"x" * 2000)]
    with pytest.raises(WebError, match="more than 1,000 bytes"):
        webrequest.get(server.url + "/big", max_bytes=1000)


def test_too_big_after_unpacking(server):
    bomb = gzip.compress(b"\0" * 1_000_000)  # small packed, large unpacked
    server.answers["/bomb"] = [(200, {"Content-Encoding": "gzip"}, bomb)]
    with pytest.raises(WebError, match="more than 10,000 bytes"):
        webrequest.get(server.url + "/bomb", max_bytes=10_000)


def test_broken_gzip(server):
    server.answers["/z"] = [(200, {"Content-Encoding": "gzip"}, b"not gzip at all")]
    with pytest.raises(WebError, match="broken gzip"):
        webrequest.get(server.url + "/z")


def test_unknown_packing(server):
    server.answers["/z"] = [(200, {"Content-Encoding": "br"}, b"...")]
    with pytest.raises(WebError, match="packed its answer as 'br'"):
        webrequest.get(server.url + "/z")


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


def test_bad_json(server):
    server.answers["/f"] = [(200, {}, b"<html>")]
    with pytest.raises(WebError, match="did not send valid JSON"):
        webrequest.get(server.url + "/f").json()


def test_messages_leave_out_the_query(server):
    with pytest.raises(WebError) as failed:
        webrequest.get(server.url + "/missing?appid=SECRET123")
    assert "SECRET123" not in str(failed.value)


@pytest.mark.parametrize("url", ["ftp://example.com/x", "file:///etc/passwd", "example.com"])
def test_only_web_addresses(url):
    with pytest.raises(WebError, match="not a web address"):
        webrequest.get(url)
