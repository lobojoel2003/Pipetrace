"""Browser tests of an exported static site (the demo that ships to GitHub Pages).

Run after exporting, e.g.:

    python manage.py load_demo
    python manage.py export_static site --base-url /Pipetrace/
    PIPETRACE_E2E_SITE=site pytest -m e2e

Set PIPETRACE_E2E_CHROMIUM to use a specific Chromium binary.
"""

from __future__ import annotations

import functools
import http.server
import os
import socketserver
import threading
from pathlib import Path

import pytest

pytestmark = pytest.mark.e2e

SITE = os.environ.get("PIPETRACE_E2E_SITE")
BASE = os.environ.get("PIPETRACE_E2E_BASE", "/Pipetrace/")

if not SITE:
    pytest.skip("PIPETRACE_E2E_SITE is not set", allow_module_level=True)
sync_api = pytest.importorskip("playwright.sync_api")


class _Handler(http.server.SimpleHTTPRequestHandler):
    """Serves the exported site under BASE, like a GitHub Pages project site."""

    def translate_path(self, path):
        if path.startswith(BASE):
            path = "/" + path[len(BASE) :]
        return super().translate_path(path)

    def log_message(self, *args):
        pass


@pytest.fixture(scope="module")
def server():
    handler = functools.partial(_Handler, directory=str(Path(SITE).resolve()))
    with socketserver.ThreadingTCPServer(("127.0.0.1", 0), handler) as httpd:
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        yield f"http://127.0.0.1:{httpd.server_address[1]}{BASE}"
        httpd.shutdown()


@pytest.fixture(scope="module")
def browser():
    with sync_api.sync_playwright() as p:
        options = {"args": ["--use-gl=swiftshader", "--enable-unsafe-swiftshader"]}
        if os.environ.get("PIPETRACE_E2E_CHROMIUM"):
            options["executable_path"] = os.environ["PIPETRACE_E2E_CHROMIUM"]
        browser = p.chromium.launch(**options)
        yield browser
        browser.close()


@pytest.fixture
def page(browser):
    page = browser.new_page(viewport={"width": 1200, "height": 900})
    page.errors = []
    page.on("pageerror", lambda exc: page.errors.append(str(exc)))
    page.on("console", lambda msg: msg.type == "error" and page.errors.append(msg.text))
    yield page
    page.close()


def test_root_picks_a_language(page, server):
    page.goto(server)
    page.wait_for_url(f"{server}en/")
    assert "lead" in page.title().lower()


def test_search_suggests_and_opens_the_line(page, server):
    page.goto(f"{server}en/")
    page.fill("#q", "305 cent")
    option = page.locator("#q-list [role=option]").first
    option.wait_for()
    assert "305 Center Ave" in option.inner_text()
    page.keyboard.press("ArrowDown")
    page.keyboard.press("Enter")
    page.wait_for_url("**/en/line/**")
    assert "305 Center Ave" in page.locator("h1").inner_text()
    assert not page.errors


def test_search_page_lists_results(page, server):
    page.goto(f"{server}en/search/?q=maple")
    page.locator("[data-search-results] .result-list li").first.wait_for()
    assert page.locator("[data-search-results] .result-list li").count() > 5


def test_spanish_home_and_map(page, server):
    page.goto(f"{server}es/")
    assert page.locator("html").get_attribute("lang") == "es"
    page.locator("canvas.maplibregl-canvas").wait_for(timeout=15000)
    page.wait_for_timeout(1500)
    assert not page.errors, page.errors


def test_pipe_helper(page, server):
    page.goto(f"{server}en/check-your-pipe/?line=305-center-ave-ff2e63")
    page.check("input[name=scratch][value=silver]")
    page.check("input[name=magnet][value=no_stick]")
    result = page.locator("[data-result]")
    assert "This looks like lead." in result.inner_text()
    link = page.locator("[data-result-link]").get_attribute("href")
    assert "scratch=silver" in link and "line=305-center-ave-ff2e63" in link


def test_photo_form_is_prefilled(page, server):
    page.goto(
        f"{server}en/check-your-pipe/send-photo/?line=305-center-ave-ff2e63"
        "&scratch=silver&magnet=no_stick"
    )
    page.wait_for_function("document.querySelector('#id_address').value !== ''")
    assert page.input_value("#id_address").startswith("305 Center Ave")
    assert page.is_checked("input[name=scratch][value=silver]")
