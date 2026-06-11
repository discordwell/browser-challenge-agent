"""Run the real in-page solver (fast_solver.js) against local HTML fixtures
that replicate each known challenge pattern. No network access: every page is
served from memory via request interception."""

from agent import build_solver_script, solver_source


def run_solver(page, timeout_ms=8000, poll_ms=25, max_steps=30):
    return page.evaluate(build_solver_script(timeout_ms, poll_ms, max_steps))


def test_scroll_revealed_code(challenge_page):
    page = challenge_page("scroll_reveal.html")
    result = run_solver(page)
    assert result["advanced"] is True
    assert result["code"] == "KX9T2M"
    assert page.evaluate("window.__submitted") == "KX9T2M"


def test_timer_delayed_code_is_polled_for(challenge_page):
    page = challenge_page("timer_reveal.html")
    result = run_solver(page)
    assert result["advanced"] is True
    assert result["code"] == "TM4R8Q"
    assert result["attempts"] > 1  # the code wasn't there on the first pass


def test_reveal_button_is_clicked(challenge_page):
    page = challenge_page("reveal_button.html")
    result = run_solver(page)
    assert result["advanced"] is True
    assert result["code"] == "RV5L9Q"
    assert "reveal" in result["actions"]


def test_hidden_data_attribute_code(challenge_page):
    page = challenge_page("data_attr.html")
    result = run_solver(page)
    assert result["advanced"] is True
    assert result["code"] == "HD7X3P"
    assert "code-source:data-attr" in result["actions"]


def test_cookie_overlay_declined_not_accepted(challenge_page):
    page = challenge_page("overlay_decline.html")
    result = run_solver(page)
    assert result["advanced"] is True
    assert result["code"] == "PR1V8C"
    # The "Accept All" distractor must never be clicked.
    assert page.evaluate("window.__accepted") is False
    assert page.evaluate("!!document.getElementById('overlay')") is False


def test_modal_with_fake_close_dismissed(challenge_page):
    page = challenge_page("modal_fake_close.html")
    result = run_solver(page)
    assert result["advanced"] is True
    assert result["code"] == "WRN3X7"
    assert page.evaluate("!!document.getElementById('overlay')") is False
    # Documented tolerance: the solver clicks inert "Close" decoys too — the
    # site's fake-close pattern is harmless — and Dismiss must still win.
    assert page.evaluate("window.__fakeCloseClicks") >= 1


def test_radio_modal_picks_correct_not_incorrect(challenge_page):
    page = challenge_page("radio_modal.html")
    result = run_solver(page)
    assert result["advanced"] is True
    assert result["code"] == "RD8K2F"
    # "Incorrect answer" is listed first; a substring match would pick it.
    assert page.evaluate("window.__wrongRadio") is False


def test_labelled_inline_code(challenge_page):
    page = challenge_page("labeled_code.html")
    result = run_solver(page)
    assert result["advanced"] is True
    assert result["code"] == "QW3RT9"
    assert "code-source:labelled" in result["actions"]


def test_uppercase_code_label_but_not_barcode(challenge_page):
    page = challenge_page("uppercase_code.html")
    result = run_solver(page)
    assert result["advanced"] is True
    # "CODE: UP9C4K" must match; "barcode AB1234" must not.
    assert result["code"] == "UP9C4K"
    assert page.evaluate("window.__submitted") == "UP9C4K"


def test_no_step_in_url_returns_without_solving(challenge_page):
    page = challenge_page("data_attr.html", path="/lobby")
    result = run_solver(page)
    assert result["advanced"] is False
    assert result["actions"] == ["no-step-in-url"]


def test_embedded_solver_walks_multiple_steps(challenge_page):
    page = challenge_page("spa_challenge.html", path="/step1")
    first = run_solver(page)
    assert first["advanced"] is True
    assert first["finished"] is False
    assert first["newStep"] == 2

    second = run_solver(page)
    assert second["advanced"] is True
    assert second["finished"] is True  # completion page detected by text
    assert page.evaluate("window.__submitted") == ["AB12CD", "EF34GH"]


def test_console_paste_mode_autoruns_to_completion(challenge_page):
    """Pasting fast_solver.js into a console must auto-run solveAllSteps."""
    page = challenge_page("spa_challenge.html", path="/")
    page.click("#start")
    page.evaluate(solver_source())  # the paste; resolves when solving stops
    assert page.url.endswith("/complete")
    assert page.evaluate("window.__submitted") == ["AB12CD", "EF34GH"]
