"""Browser-test helpers (Playwright, Chromium).

How the browser is found:
- SCW_CHROMIUM_PATH set: launch that executable (used in the sandbox, where
  Chromium is preinstalled and `playwright install` must not be run).
- Otherwise: Playwright's own Chromium (installed in CI with
  `python -m playwright install --with-deps chromium`).

Skip rule: if Playwright or the browser is unavailable, the test is skipped with
a clear message, UNLESS SCW_REQUIRE_BROWSER is set (CI sets it to 1), in which
case it fails loudly. A skipped browser test is never reported as a pass of the
page; it is reported as skipped.
"""
import functools
import http.server
import os
import threading
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = ROOT / 'test-output' / 'browser'   # gitignored


def require_browser():
    return bool(os.environ.get('SCW_REQUIRE_BROWSER'))


class _Handler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):  # keep test output quiet
        pass

    def do_GET(self):
        if self.path == '/favicon.ico':   # avoid a spurious console 404
            self.send_response(204)
            self.end_headers()
            return
        super().do_GET()


class StaticServer:
    """Serve a directory on 127.0.0.1 on a free port (no network access needed)."""

    def __init__(self, directory):
        handler = functools.partial(_Handler, directory=str(directory))
        self._httpd = http.server.ThreadingHTTPServer(('127.0.0.1', 0), handler)
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)

    @property
    def base_url(self):
        return f'http://127.0.0.1:{self._httpd.server_address[1]}'

    def __enter__(self):
        self._thread.start()
        return self

    def __exit__(self, *exc):
        self._httpd.shutdown()
        self._httpd.server_close()


class BrowserTestCase(unittest.TestCase):
    """Base class: starts one Chromium for the class, gives each test a fresh page
    that records console errors and uncaught page errors in `self.errors`."""
    _pw = None
    _browser = None
    _server = None

    @classmethod
    def serve_directory(cls):
        return ROOT / 'evidence'

    @classmethod
    def setUpClass(cls):
        def unavailable(why):
            if require_browser():
                raise RuntimeError(f'browser tests are REQUIRED (SCW_REQUIRE_BROWSER set) but {why}')
            raise unittest.SkipTest(
                f'browser tests skipped: {why}. Install with `pip install -e ".[test]"` and '
                '`python -m playwright install chromium`, or set SCW_CHROMIUM_PATH to a Chromium '
                'executable. Set SCW_REQUIRE_BROWSER=1 to make this a failure.')
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            unavailable('the Python package `playwright` is not installed')
        cls._pw = sync_playwright().start()
        try:
            exe = os.environ.get('SCW_CHROMIUM_PATH')
            cls._browser = cls._pw.chromium.launch(executable_path=exe) if exe else cls._pw.chromium.launch()
        except Exception as exc:  # noqa: BLE001
            cls._pw.stop()
            cls._pw = None
            unavailable('Chromium could not be launched (' + str(exc).strip().splitlines()[0] + ')')
        cls._server = StaticServer(cls.serve_directory()).__enter__()
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    @classmethod
    def tearDownClass(cls):
        if cls._browser:
            cls._browser.close()
        if cls._pw:
            cls._pw.stop()
        if cls._server:
            cls._server.__exit__(None, None, None)

    def setUp(self):
        self.errors = []
        self.page = self._browser.new_page(viewport={'width': 1400, 'height': 900})
        self.page.on('console', lambda m: self.errors.append(f'console.{m.type}: {m.text}') if m.type == 'error' else None)
        self.page.on('pageerror', lambda e: self.errors.append(f'pageerror: {e}'))
        self.page.on('requestfailed', lambda r: self.errors.append(f'requestfailed: {r.url}'))
        self.addCleanup(self.page.close)

    def open(self, relative_path):
        """Open a page under the served directory; fail on a bad HTTP status."""
        response = self.page.goto(f'{self._server.base_url}/{relative_path}')
        self.assertTrue(response and response.ok, f'{relative_path} did not load: {response and response.status}')

    def screenshot(self, name, full_page=True):
        """Save a REAL screenshot (full page by default) and return its path (never synthesized)."""
        path = OUTPUT_DIR / f'{name}.png'
        self.page.screenshot(path=str(path), full_page=full_page)
        self.assertGreater(path.stat().st_size, 1000, 'screenshot looks empty')
        return path

    def assert_no_console_errors(self):
        self.assertEqual(self.errors, [], 'browser reported errors')
