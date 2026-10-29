"""Browser mode: the page server (src/web_server.py) and the system programs it leans on (src/host_tools.py).

These run a real server on a real loopback socket and talk to it over real HTTP, because the things that
break here are the seams - a value that won't turn into JSON, a path that escapes src/ui, a token check that
isn't there - and none of those show up when the handler is called directly.
"""
import json
import sys
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import host_tools        # noqa: E402
import web_server        # noqa: E402

UI_DIR = Path(__file__).resolve().parent.parent / "src" / "ui"


class FakeApi:
    """Stands in for Api: the same shape (public methods are callable, private ones are not exposed)."""

    def __init__(self):
        self.calls = []
        self.mod_root = Path("/not/a/real/folder")      # a public attribute that is NOT callable

    def get_app_version(self):
        return "9.9.9"

    def add(self, a, b):
        self.calls.append(("add", a, b))
        return {"sum": a + b}

    def explodes(self):
        raise ValueError("no good")

    def returns_a_set(self):
        return {1, 2, 3}        # not JSON: the page must get an error, not a dead connection

    def _private(self):
        return "should never be reachable"


class ServerTestCase(unittest.TestCase):
    """A real server on a free port, stopped again at the end of the test."""

    def setUp(self):
        self.api = FakeApi()
        self.port = None
        started = threading.Event()
        self.lines = []

        def announce(text):
            self.lines.append(text)
            for word in text.split():
                if word.startswith("http://"):
                    self.url = word
                    self.port = int(word.split(":")[2].split("/")[0])
                    self.token = word.partition("?t=")[2]
            started.set()

        self.thread = threading.Thread(
            target=lambda: web_server.serve(self.api, UI_DIR, port=0, open_browser=False, announce=announce),
            daemon=True)
        self.thread.start()
        self.assertTrue(started.wait(10), "the server never said it had started")

    def tearDown(self):
        try:
            self.post("/quit")
        except Exception:       # noqa: BLE001 - already gone is fine
            pass
        self.thread.join(timeout=10)

    # ---- talking to it ----

    def request(self, path, method="GET", token=None, body=None, headers=None):
        url = f"http://127.0.0.1:{self.port}{path}"
        data = json.dumps(body).encode() if body is not None else (b"" if method == "POST" else None)
        req = urllib.request.Request(url, data=data, method=method)
        if token:
            req.add_header("X-MK8DX-Token", token)
        for name, value in (headers or {}).items():
            req.add_header(name, value)
        try:
            with urllib.request.urlopen(req, timeout=10) as response:
                return response.status, response.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()

    def post(self, path, body=None, token=None):
        """`token=None` sends this run's real one; "" sends none at all."""
        return self.request(path, "POST", self.token if token is None else token, body)

    def call(self, method, *args, token=None):
        status, body = self.post(f"/api/{method}", {"args": list(args)}, token=token)
        return status, json.loads(body)


class TestApiCalls(ServerTestCase):

    def test_a_call_returns_its_result(self):
        self.assertEqual(self.call("get_app_version"), (200, {"result": "9.9.9"}))

    def test_arguments_arrive_in_order(self):
        status, payload = self.call("add", 2, 40)
        self.assertEqual((status, payload), (200, {"result": {"sum": 42}}))
        self.assertEqual(self.api.calls, [("add", 2, 40)])

    def test_a_method_that_raises_answers_with_an_error_not_a_dead_connection(self):
        status, payload = self.call("explodes")
        self.assertEqual(status, 200)
        self.assertIn("no good", payload["error"])

    def test_a_result_that_is_not_json_is_an_error_not_a_dead_connection(self):
        # The whole page would hang on a half-written answer, so this must come back as a failed call.
        status, payload = self.call("returns_a_set")
        self.assertEqual(status, 200)
        self.assertIn("error", payload)

    def test_private_methods_are_not_exposed(self):
        status, payload = self.call("_private")
        self.assertEqual(status, 404)
        self.assertIn("No such method", payload["error"])

    def test_unknown_methods_are_not_exposed(self):
        self.assertEqual(self.call("rm_rf")[0], 404)

    def test_public_attributes_that_are_not_methods_are_not_exposed(self):
        self.assertNotIn("mod_root", web_server.api_methods(self.api))

    def test_api_methods_lists_the_public_methods(self):
        self.assertEqual(web_server.api_methods(self.api),
                         ["add", "explodes", "get_app_version", "returns_a_set"])


class TestWhoMayCall(ServerTestCase):

    def test_no_token_is_refused(self):
        self.assertEqual(self.call("get_app_version", token="")[0], 403)

    def test_a_wrong_token_is_refused(self):
        self.assertEqual(self.call("get_app_version", token="x" * 43)[0], 403)

    def test_the_page_needs_the_token(self):
        status, body = self.request("/")
        self.assertEqual(status, 403)
        self.assertNotIn(self.token.encode(), body)     # the refusal must not hand out what it asked for

    def test_the_page_with_the_token_carries_the_bridge(self):
        status, body = self.request(f"/?t={self.token}")
        page = body.decode()
        self.assertEqual(status, 200)
        self.assertIn("js/webserver-bridge.js", page)
        self.assertIn(f'token:"{self.token}"', page)
        self.assertIn('"get_app_version"', page)
        self.assertLess(page.index("__mk8dxServer"), page.index("</head>"), "the bridge must come before the page's scripts")

    def test_a_cross_origin_preflight_is_refused(self):
        # No "Access-Control-Allow-*" answer means the browser never sends the call another page was preparing.
        status, _ = self.request("/api/get_app_version", "OPTIONS", headers={"Origin": "http://evil.test"})
        self.assertEqual(status, 403)

    def test_a_host_header_that_is_not_loopback_is_refused(self):
        status, _ = self.request("/js/bootstrap.js", headers={"Host": "mod-manager.evil.test"})
        self.assertEqual(status, 403)


class TestKeepAlive(ServerTestCase):
    """One connection, several requests. The server must read every request's body even when it refuses the
    request, or what is left of it is parsed as the start of the next one."""

    def _conn(self):
        import http.client
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        self.addCleanup(conn.close)
        return conn

    def _send(self, conn, path, token):
        headers = {"Content-Type": "application/json"}
        if token:
            headers["X-MK8DX-Token"] = token
        conn.request("POST", path, json.dumps({"args": [], "padding": "x" * 5000}), headers)
        response = conn.getresponse()
        return response.status, response.read()

    def test_a_refused_call_does_not_break_the_next_one_on_the_same_connection(self):
        conn = self._conn()
        self.assertEqual(self._send(conn, "/api/get_app_version", "wrong-token")[0], 403)
        status, body = self._send(conn, "/api/get_app_version", self.token)
        self.assertEqual((status, json.loads(body)), (200, {"result": "9.9.9"}))

    def test_an_unknown_method_does_not_break_the_next_call(self):
        conn = self._conn()
        self.assertEqual(self._send(conn, "/api/nope", self.token)[0], 404)
        status, body = self._send(conn, "/api/get_app_version", self.token)
        self.assertEqual((status, json.loads(body)), (200, {"result": "9.9.9"}))

    def test_many_calls_in_a_row_on_one_connection(self):
        conn = self._conn()
        for _ in range(10):
            status, body = self._send(conn, "/api/get_app_version", self.token)
            self.assertEqual((status, json.loads(body)), (200, {"result": "9.9.9"}))


class TestStaticFiles(ServerTestCase):

    def test_the_page_s_own_files_are_served(self):
        status, body = self.request("/js/bootstrap.js")
        self.assertEqual(status, 200)
        self.assertIn(b"SCRIPTS", body)

    def test_the_bridge_is_served(self):
        self.assertEqual(self.request("/js/webserver-bridge.js")[0], 200)

    def test_nothing_outside_src_ui_can_be_read(self):
        for path in ("/../mod_manager.py", "/../../app-config.json", "/..%2Fmod_manager.py",
                     "/js/../../mod_manager.py", "//etc/passwd"):
            with self.subTest(path=path):
                status, body = self.request(path)
                self.assertIn(status, (403, 404), f"{path} was served")
                self.assertNotIn(b"import webview", body)


class TestLifecycle(unittest.TestCase):
    """When the app decides the page has gone. A fake clock, so no test waits on real time."""

    def setUp(self):
        self.now = 1000.0
        self.quit_reasons = []
        self.life = web_server._Lifecycle(on_quit=lambda: self.quit_reasons.append("quit"),
                                          idle_timeout=180, closing_grace=6, first_load_timeout=1800,
                                          clock=lambda: self.now)

    def test_it_waits_a_long_time_for_a_page_that_has_never_loaded(self):
        # The user may need minutes to find the link and paste it - 3 idle minutes must not kill the app first.
        self.now += 200
        self.assertIsNone(self.life.should_quit())
        self.now += 1700
        self.assertIsNotNone(self.life.should_quit())

    def test_a_loaded_page_that_goes_quiet_is_gone(self):
        self.life.heard_from_page()
        self.now += 100
        self.assertIsNone(self.life.should_quit())
        self.now += 100
        self.assertIsNotNone(self.life.should_quit())

    def test_a_heartbeat_keeps_it_alive(self):
        self.life.heard_from_page()
        for _ in range(20):
            self.now += 20
            self.life.heard_from_page()
        self.assertIsNone(self.life.should_quit())

    def test_closing_the_page_stops_the_app_after_the_grace_period(self):
        self.life.heard_from_page()
        self.life.page_closing()
        self.assertIsNone(self.life.should_quit())
        self.now += 7
        self.assertEqual(self.life.should_quit(), "the page was closed")

    def test_a_reload_within_the_grace_period_cancels_it(self):
        self.life.heard_from_page()
        self.life.page_closing()
        self.now += 3
        self.life.heard_from_page()         # the page came back
        self.now += 10
        self.assertIsNone(self.life.should_quit())

    def test_it_never_quits_while_a_call_is_being_answered(self):
        # Closing the tab during a merge must not cut the merge off part-way.
        self.life.heard_from_page()
        with self.life.answering():
            self.life.page_closing()
            self.now += 10_000
            self.assertIsNone(self.life.should_quit())
        self.assertIsNotNone(self.life.should_quit())

    def test_quit_runs_once(self):
        self.life.quit_now("first")
        self.life.quit_now("second")
        self.assertEqual(self.quit_reasons, ["quit"])


class TestHostToolsEnvironment(unittest.TestCase):
    """A program we start must get the system's library path, not the bundle's (see host_tools)."""

    def test_a_frozen_build_puts_back_what_pyinstaller_saved(self):
        env = host_tools.original_environ(
            {"LD_LIBRARY_PATH": "/tmp/_MEI123", "LD_LIBRARY_PATH_ORIG": "/usr/local/lib", "PATH": "/usr/bin"},
            frozen=True)
        self.assertEqual(env["LD_LIBRARY_PATH"], "/usr/local/lib")
        self.assertNotIn("LD_LIBRARY_PATH_ORIG", env)
        self.assertEqual(env["PATH"], "/usr/bin")

    def test_a_frozen_build_removes_what_pyinstaller_invented(self):
        # No _ORIG means the variable was unset before the bundle set it, so it must go again.
        env = host_tools.original_environ({"LD_LIBRARY_PATH": "/tmp/_MEI123"}, frozen=True)
        self.assertNotIn("LD_LIBRARY_PATH", env)

    def test_running_from_source_changes_nothing(self):
        before = {"LD_LIBRARY_PATH": "/opt/mine", "PATH": "/usr/bin"}
        self.assertEqual(host_tools.original_environ(before, frozen=False), before)

    def test_macos_variables_are_handled_too(self):
        env = host_tools.original_environ({"DYLD_LIBRARY_PATH": "/tmp/_MEI", "DYLD_FRAMEWORK_PATH": "/tmp/_MEI"},
                                          frozen=True)
        self.assertNotIn("DYLD_LIBRARY_PATH", env)
        self.assertNotIn("DYLD_FRAMEWORK_PATH", env)

    def test_system_env_puts_the_environment_back_afterwards(self):
        import os
        before = dict(os.environ)
        with host_tools.system_env():
            os.environ["MK8DX_TEST_ONLY"] = "1"
        self.assertEqual(dict(os.environ), before)


class TestBridgeFile(unittest.TestCase):
    """The page's side of the bridge: the one file that is NOT in bootstrap.js's SCRIPTS."""

    def setUp(self):
        self.source = (UI_DIR / "js" / "webserver-bridge.js").read_text(encoding="utf-8")

    def test_it_does_nothing_without_the_server_s_prelude(self):
        self.assertIn("if (!config) return;", self.source)

    def test_it_sends_the_token_on_every_call(self):
        self.assertIn('"X-MK8DX-Token": TOKEN', self.source)

    def test_it_fires_the_event_the_page_waits_for(self):
        self.assertIn("pywebviewready", self.source)

    def test_it_is_not_in_bootstrap_s_script_list(self):
        # It must load BEFORE them (the server puts it in <head>), so listing it here would load it twice.
        bootstrap = (UI_DIR / "js" / "bootstrap.js").read_text(encoding="utf-8")
        self.assertNotIn("webserver-bridge", bootstrap)

    def test_index_html_has_the_marker_the_server_injects_before(self):
        self.assertIn("</head>", (UI_DIR / "index.html").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
