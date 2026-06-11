import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))  # make `import agent` work from anywhere

FIXTURES = Path(__file__).resolve().parent / "fixtures"

# All fixture pages are served from this fake origin so the solver's
# /step(\d+) URL parsing has something realistic to chew on.
ORIGIN = "https://challenge.test"


def fixture_html(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


@pytest.fixture(scope="session")
def browser():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(headless=True)
        except Exception as exc:  # browsers not installed
            pytest.skip(f"chromium unavailable: {exc}")
        yield browser
        browser.close()


@pytest.fixture()
def challenge_page(browser):
    """Yield open(name, path='/step1') -> Page serving a fixture at ORIGIN.

    The same HTML answers every path on the origin; fixtures that span
    multiple steps re-render themselves SPA-style via pushState, which is
    how the real challenge site behaves.
    """
    context = browser.new_context()

    def _open(name: str, path: str = "/step1"):
        page = context.new_page()
        html = fixture_html(name)
        page.route(
            f"{ORIGIN}/**",
            lambda route: route.fulfill(status=200, content_type="text/html", body=html),
        )
        page.goto(f"{ORIGIN}{path}")
        return page

    yield _open
    context.close()
