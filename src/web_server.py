"""Browser mode: the app serves its own page to the user's browser instead of opening a window of its own.

This is how the **Linux package** runs (docs/browser-mode.md). Linux has no web view to lend the app, so a
packaged window meant carrying the whole of Qt WebEngine - Chromium - which made the download 123 MB against
about 20 MB on Windows and macOS. The user's browser is already on their machine, so the package ships none.

What it is: a plain `http.server` on the loopback address, serving `src/ui/` as it is and turning
`POST /api/<method>` into a call on the same `Api` object pywebview would have been given. The page is
unchanged - `src/ui/js/webserver-bridge.js` puts a `window.pywebview.api` in front of it that speaks HTTP, so
all ~200 `pywebview.api.<method>(...)` calls in the page carry on working untouched.

Kept closed:
  - the socket is bound to 127.0.0.1, so nothing off this machine can reach it at all;
  - every `/api/` call must carry the run's own random token in `X-MK8DX-Token`. A custom header is one no
    other site's page can send without our permission first (the browser asks, and we never answer), so a
    page the user has open elsewhere cannot drive the app;
  - the `Host` header must name the loopback address, which is what stops a hostname that resolves to
    127.0.0.1 being used to get around the browser's idea of who we are.

Stopping: the page says it is still there every HEARTBEAT_SECONDS, and sends a beacon when it goes away. The
app quits a few seconds after the page goes away and does not come back, or after IDLE_TIMEOUT with no word
at all - but never while a call is still being answered, so closing the tab during a merge cannot cut it off.
"""

import json
import os
import secrets
import socket
import socketserver
import sys
import threading
import time
from email.utils import formatdate
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import diag
import host_tools

HEARTBEAT_SECONDS = 20          # how often the page says it is still there (must survive a browser throttling a hidden tab)
IDLE_TIMEOUT = 180              # nothing from a page that HAS loaded for this long: it is gone
FIRST_LOAD_TIMEOUT = 30 * 60    # nobody ever opened the link: give a person time to find it and paste it
CLOSING_GRACE = 6               # the page sent "I'm going away": this long for a reload to bring it back
MAX_BODY = 64 * 1024 * 1024     # a call's arguments (a cropped picture arrives as a data: URI, so this is not small)

CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8",
    ".json": "application/json; charset=utf-8", ".svg": "image/svg+xml", ".png": "image/png", ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg", ".gif": "image/gif", ".webp": "image/webp", ".ico": "image/x-icon",
    ".woff": "font/woff", ".woff2": "font/woff2", ".ttf": "font/ttf", ".map": "application/json; charset=utf-8",
}

# Put into index.html before the page's own scripts, so webserver-bridge.js has the token and the method names
# before anything asks pywebview for anything. (From source in a pywebview window none of this is there and the
# bridge does nothing - the real pywebview.api is already in place.)
_PRELUDE = """<script>window.__mk8dxServer = {token:"%s", methods:%s, heartbeat:%d};</script>
<script src="js/webserver-bridge.js"></script>
"""


def api_methods(api):
    """The names the page may call - what pywebview would expose: every public method of the Api object."""
    return sorted(name for name in dir(api)
                  if not name.startswith("_") and callable(getattr(api, name, None)))


class _Server(ThreadingHTTPServer):
    daemon_threads = True
    # SO_REUSEADDR so restarting the app on a fixed MK8DX_PORT isn't refused for a minute by the last run's
    # socket sitting in TIME_WAIT. On Unix that is all it does - it cannot take a port another program is
    # listening on. On Windows it can, so there it stays off.
    allow_reuse_address = sys.platform != "win32"

    def server_bind(self):
        """Binds the socket WITHOUT http.server's reverse-DNS lookup.

        HTTPServer.server_bind calls socket.getfqdn() to fill in `server_name`, which nothing here ever reads.
        On a machine with no reverse entry for 127.0.0.1 that call blocks until the resolver gives up - seconds
        at a time, before the app has printed the link to open, so it simply looks hung. Seen on a macOS CI
        runner: the first few starts took over ten seconds each, then the OS cached the answer and the rest were
        instant."""
        socketserver.TCPServer.server_bind(self)
        self.server_name, self.server_port = self.server_address[0], self.server_address[1]


class _Handler(BaseHTTPRequestHandler):
    server_version = "MK8DXModManager"
    sys_version = ""
    protocol_version = "HTTP/1.1"

    # ---- plumbing ----

    def log_message(self, fmt, *args):
        pass        # (the app's own log says what matters; a line per request would drown it)

    def _host_is_loopback(self):
        host = (self.headers.get("Host") or "").rsplit(":", 1)[0].strip("[]")
        return host in ("127.0.0.1", "localhost", "::1")

    def _authorised(self):
        sent = self.headers.get("X-MK8DX-Token") or ""
        return secrets.compare_digest(sent, self.server.token)

    def _send(self, status, body=b"", content_type="text/plain; charset=utf-8", extra=None):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        # The page is only ever ours and only ever talks to us: no outside code, no framing, no referrers.
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        for name, value in (extra or {}).items():
            self.send_header(name, value)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, status, payload):
        self._send(status, json.dumps(payload), "application/json; charset=utf-8")

    # ---- routes ----

    def do_OPTIONS(self):       # noqa: N802
        # No CORS answer, ever: a cross-origin page asking permission to send our token header is told nothing,
        # so the browser refuses the call it was preparing.
        self._send(HTTPStatus.FORBIDDEN, "No.")

    def do_HEAD(self):          # noqa: N802
        self.do_GET()

    def do_GET(self):           # noqa: N802
        if not self._host_is_loopback():
            self._send(HTTPStatus.FORBIDDEN, "This app only answers on 127.0.0.1.")
            return
        path, _, query = self.path.partition("?")
        if path in ("/", "/index.html"):
            self._serve_page(query)
            return
        self._serve_static(path)

    def do_POST(self):          # noqa: N802
        # The body is read FIRST, whatever the answer turns out to be. This connection is kept alive between
        # requests, so a body left unread would still be sitting in it when the next request is parsed, and that
        # request would be read as nonsense.
        body = self._read_body()
        if body is None:
            return
        if not self._host_is_loopback():
            self._send(HTTPStatus.FORBIDDEN, "This app only answers on 127.0.0.1.")
            return
        path = self.path.partition("?")[0]
        if not self._authorised():
            self._json(HTTPStatus.FORBIDDEN, {"error": "This page is not this app's page."})
            return
        if path == "/alive":
            self.server.lifecycle.heard_from_page()
            self._json(HTTPStatus.OK, {"ok": True})
        elif path == "/closing":
            self.server.lifecycle.page_closing()
            self._json(HTTPStatus.OK, {"ok": True})
        elif path == "/quit":
            self.server.lifecycle.quit_now("the page asked to quit")
            self._json(HTTPStatus.OK, {"ok": True})
        elif path.startswith("/api/"):
            self._call_api(path[len("/api/"):], body)
        else:
            self._send(HTTPStatus.NOT_FOUND, "Not found.")

    def _read_body(self):
        """The request's body, or None when it couldn't be read (an answer has been sent, and the connection closed
        so that whatever is left of the body cannot be mistaken for the next request)."""
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = -1
        if not 0 <= length <= MAX_BODY:
            self.close_connection = True
            self._send(HTTPStatus.BAD_REQUEST, "Bad request body.")
            return None
        try:
            return self.rfile.read(length)
        except OSError as e:
            self.close_connection = True
            diag.log("browser-mode", f"couldn't read a request body: {type(e).__name__}: {e}")
            return None

    def _serve_page(self, query):
        """index.html, with the token and the method names put in - but only for a browser that came with the
        token in the link the app printed. Everything else gets a page saying so, never the token."""
        token = ""
        for part in query.split("&"):
            name, _, value = part.partition("=")
            if name == "t":
                token = value
        if not secrets.compare_digest(token, self.server.token):
            self._send(HTTPStatus.FORBIDDEN,
                       "<h1>Mario Kart 8 Mod Manager</h1><p>This link is missing the one-time key this run of the "
                       "app made. Open the link the app printed in its terminal window.</p>",
                       "text/html; charset=utf-8")
            return
        try:
            html = (self.server.ui_dir / "index.html").read_text(encoding="utf-8")
        except OSError as e:
            self._send(HTTPStatus.INTERNAL_SERVER_ERROR, f"The app's page is missing: {e}")
            return
        prelude = _PRELUDE % (self.server.token, json.dumps(sorted(self.server.methods)), HEARTBEAT_SECONDS)
        self.server.lifecycle.heard_from_page()
        self._send(HTTPStatus.OK, html.replace("</head>", prelude + "</head>", 1), "text/html; charset=utf-8")

    def _serve_static(self, path):
        """A file of src/ui. No token: these are the app's own markup, styles and scripts, and hold nothing of the
        user's. Nothing outside src/ui can be reached, whatever the request says."""
        ui_dir = self.server.ui_dir
        wanted = (ui_dir / path.lstrip("/")).resolve()
        if not wanted.is_file() or ui_dir not in wanted.parents:
            self._send(HTTPStatus.NOT_FOUND, "Not found.")
            return
        try:
            body = wanted.read_bytes()
        except OSError as e:
            self._send(HTTPStatus.INTERNAL_SERVER_ERROR, f"Couldn't read {path}: {e}")
            return
        self._send(HTTPStatus.OK, body, CONTENT_TYPES.get(wanted.suffix.lower(), "application/octet-stream"),
                   {"Last-Modified": formatdate(wanted.stat().st_mtime, usegmt=True)})

    def _call_api(self, method, body):
        """POST /api/<method> with {"args": [...]} -> {"result": ...} or {"error": "..."} (the bridge turns the
        second into a rejected promise, which is what the page already expects of a pywebview call that failed)."""
        if method not in self.server.methods:
            self._json(HTTPStatus.NOT_FOUND, {"error": f"No such method: {method}"})
            return
        try:
            args = json.loads(body or b"{}").get("args", [])
        except (ValueError, AttributeError) as e:
            self._json(HTTPStatus.BAD_REQUEST, {"error": f"Couldn't read the arguments: {e}"})
            return
        if not isinstance(args, list):
            self._json(HTTPStatus.BAD_REQUEST, {"error": "Arguments must be a list."})
            return

        with self.server.lifecycle.answering():
            try:
                result = getattr(self.server.api, method)(*args)
                # allow_nan=False on purpose. Python writes NaN and Infinity happily, but neither is JSON and the
                # browser's JSON.parse refuses the whole answer - so the call would fail with a parse error nowhere
                # near the method that produced the number. Refusing it here names the method instead, in the log and
                # in what the page is told. tests/test_api_json.py keeps the Api's own answers clean.
                body = json.dumps({"result": result}, allow_nan=False)
            except Exception as e:      # noqa: BLE001 - the page gets every failure as a rejected promise, as under pywebview
                diag.log("api", f"{method}() failed: {type(e).__name__}: {e}")
                self._json(HTTPStatus.OK, {"error": f"{type(e).__name__}: {e}"})
                return
        self._send(HTTPStatus.OK, body, "application/json; charset=utf-8")


class _Lifecycle:
    """When to stop. The page checks in; the app quits once it has gone and stayed gone - but never in the middle
    of answering a call, so closing the tab during a merge or a download cannot cut it short."""

    def __init__(self, on_quit, idle_timeout=IDLE_TIMEOUT, closing_grace=CLOSING_GRACE,
                 first_load_timeout=FIRST_LOAD_TIMEOUT, clock=time.monotonic):
        self._on_quit = on_quit
        self._idle_timeout = idle_timeout
        self._closing_grace = closing_grace
        self._first_load_timeout = first_load_timeout
        self._clock = clock
        self._lock = threading.Lock()
        self._last_seen = clock()
        self._ever_loaded = False   # until the page has been opened once, waiting on a person, not on a heartbeat
        self._deadline = None       # set when the page says it is going away
        self._in_flight = 0
        self._stopped = False

    def heard_from_page(self):
        with self._lock:
            self._last_seen = self._clock()
            self._ever_loaded = True
            self._deadline = None       # a reload brought it back

    def page_closing(self):
        with self._lock:
            self._deadline = self._clock() + self._closing_grace

    def answering(self):
        lifecycle = self

        class _Busy:
            def __enter__(self):
                with lifecycle._lock:
                    lifecycle._in_flight += 1
                    lifecycle._last_seen = lifecycle._clock()

            def __exit__(self, *exc):
                with lifecycle._lock:
                    lifecycle._in_flight -= 1
                    lifecycle._last_seen = lifecycle._clock()
                return False

        return _Busy()

    def should_quit(self):
        """True when the page has gone for good and nothing is being answered."""
        with self._lock:
            if self._in_flight:
                return None
            now = self._clock()
            if self._deadline is not None and now >= self._deadline:
                return "the page was closed"
            if not self._ever_loaded:
                if now - self._last_seen >= self._first_load_timeout:
                    return f"the link was never opened ({self._first_load_timeout // 60} minutes)"
                return None
            if now - self._last_seen >= self._idle_timeout:
                return f"nothing from the page for {self._idle_timeout} seconds"
            return None

    def quit_now(self, why):
        with self._lock:
            if self._stopped:
                return
            self._stopped = True
        diag.log("browser-mode", f"stopping: {why}")
        self._on_quit()

    def watch(self, interval=1.0):
        """Runs until it is time to stop (a daemon thread)."""
        while True:
            time.sleep(interval)
            with self._lock:
                if self._stopped:
                    return
            why = self.should_quit()
            if why:
                self.quit_now(why)
                return


def _free_port(host, wanted):
    """Opens the listening socket. `wanted` of 0 means "any free port"."""
    server = _Server((host, wanted), _Handler)
    return server


def _announce(text):
    """Says something to whoever started the app. Flushed every time: the link is the one thing the user may
    have to read and act on, and stdout is a file (the log) in a packaged build, so it would otherwise sit in
    a buffer until the app stopped."""
    print(text, flush=True)


def serve(api, ui_dir, host="127.0.0.1", port=0, open_browser=True, announce=_announce):
    """Serves the page until the browser goes away. Returns the port it used (after it has stopped).

    `api` is the same object a pywebview window would get as its `js_api`; `ui_dir` is the folder holding
    index.html. MK8DX_PORT asks for a particular port, MK8DX_NO_BROWSER=1 leaves the browser alone (for tests
    and for running the app over SSH)."""
    ui_dir = Path(ui_dir).resolve()
    port = int(os.environ.get("MK8DX_PORT") or port)
    if os.environ.get("MK8DX_NO_BROWSER") == "1":
        open_browser = False
    try:
        httpd = _free_port(host, port)
    except OSError as e:
        raise RuntimeError(f"Couldn't listen on {host}:{port or '(any free port)'}: {e}") from e

    httpd.api = api
    httpd.ui_dir = ui_dir
    httpd.token = secrets.token_urlsafe(32)
    httpd.methods = frozenset(api_methods(api))
    httpd.lifecycle = _Lifecycle(on_quit=lambda: threading.Thread(target=httpd.shutdown, daemon=True).start())

    chosen = httpd.socket.getsockname()[1]
    url = f"http://{host}:{chosen}/?t={httpd.token}"
    diag.log("browser-mode", f"serving {len(httpd.methods)} methods on {host}:{chosen}")
    announce("\n  Mario Kart 8 Mod Manager is running. Open this in your browser:\n"
             f"\n      {url}\n"
             "\n  (the key in the link is new every time the app starts)"
             "\n  Closing the page quits the app; Ctrl-C here does too.\n")
    if open_browser and not host_tools.open_browser(url):
        announce("  Couldn't open a browser by itself - open the link above.\n")

    threading.Thread(target=httpd.lifecycle.watch, daemon=True).start()
    try:
        httpd.serve_forever(poll_interval=0.2)
    except KeyboardInterrupt:
        diag.log("browser-mode", "stopping: Ctrl-C")
    finally:
        httpd.server_close()
    return chosen


def self_test_socket():
    """True when a loopback socket can be opened at all (the self-check asks, so a machine that cannot serve
    the page says so there rather than at start-up)."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            return True
    except OSError:
        return False


if __name__ == "__main__":      # pragma: no cover - a hand check: python src/web_server.py
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import mod_manager
    serve(mod_manager.Api(mod_manager.load_master_dir_pointer() or mod_manager.default_master_dir()),
          Path(__file__).resolve().parent / "ui")
