"""Run the real in-page solver (fast_solver.js) against local HTML fixtures
that replicate each known challenge pattern. No network access: every page is
served from memory via request interception."""

import pytest

from agent import build_finished_probe, build_solver_script, solver_source


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


def test_show_code_button_is_clicked(challenge_page):
    # Same click-to-reveal pattern, worded "Show Code" rather than "Reveal
    # Code": the reveal verb must be recognised by meaning, not just the
    # literal word "reveal".
    page = challenge_page("show_code_button.html")
    result = run_solver(page)
    assert result["advanced"] is True
    assert result["code"] == "SH6W2K"
    assert "reveal" in result["actions"]
    assert page.evaluate("window.__submitted") == "SH6W2K"


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


def test_distractor_words_skipped_for_digit_bearing_code(challenge_page):
    page = challenge_page("distractor_word_code.html")
    result = run_solver(page)
    assert result["advanced"] is True
    # "FINALE"/"RESULT"/"PUZZLE" are all 6 uppercase letters and come first;
    # only the digit-bearing line is the real code.
    assert result["code"] == "ZX8W4Q"
    assert page.evaluate("window.__submitted") == "ZX8W4Q"


def test_labelled_code_beats_standalone_distractor(challenge_page):
    page = challenge_page("labelled_beats_distractor.html")
    result = run_solver(page)
    assert result["advanced"] is True
    # The standalone "XJ47PD" decoy appears first and even has digits; the
    # explicitly labelled "Code: GD3K8M" must win.
    assert result["code"] == "GD3K8M"
    assert "code-source:labelled" in result["actions"]
    assert page.evaluate("window.__submitted") == "GD3K8M"


def test_labelled_prose_word_loses_to_digit_bearing_code(challenge_page):
    page = challenge_page("labelled_prose_distractor.html")
    result = run_solver(page)
    assert result["advanced"] is True
    # "The code is HIDDEN" must NOT submit the prose word "HIDDEN"; the real
    # code is the digit-bearing line.
    assert result["code"] == "ZX8W4Q"
    assert page.evaluate("window.__submitted") == "ZX8W4Q"


def test_agree_gate_checkbox_enables_submit(challenge_page):
    page = challenge_page("agree_gate.html")
    result = run_solver(page)
    assert result["advanced"] is True
    assert result["code"] == "GT5R9K"
    # The solver had to check the "I am human" box to enable the submit button.
    assert "check:gate" in result["actions"]
    assert page.evaluate("document.getElementById('agree').checked") is True
    assert page.evaluate("window.__submitted") == "GT5R9K"


def test_agree_gate_skips_distractor_checkbox(challenge_page):
    page = challenge_page("agree_gate_distractor.html")
    result = run_solver(page)
    assert result["advanced"] is True
    assert result["code"] == "DT8R3K"
    # The gate-like "I am human" box must be checked; the newsletter decoy
    # (listed first in the DOM) must be left alone once submit is unlocked.
    assert page.evaluate("document.getElementById('agree').checked") is True
    assert page.evaluate("document.getElementById('spam').checked") is False
    assert page.evaluate("window.__submitted") == "DT8R3K"


def test_select_dropdown_quiz_picks_correct_option(challenge_page):
    page = challenge_page("select_quiz.html")
    result = run_solver(page)
    assert result["advanced"] is True
    assert result["code"] == "SL7K2D"
    # "Incorrect option" is listed first; a substring match would pick it.
    assert page.evaluate("window.__wrongSelect") is False
    assert page.evaluate("window.__submitted") == "SL7K2D"


@pytest.mark.parametrize("body_text", [
    "Congratulations! You completed the challenge.",
    "Challenge complete!",
    "Well done, that's everything.",
    "You did it!",
    "All 30 challenges solved",
    "All steps complete",
])
def test_looks_finished_matches_completion_copy(challenge_page, body_text):
    page = challenge_page("data_attr.html", path="/complete")
    page.evaluate("(t) => { document.body.innerText = t; }", body_text)
    assert page.evaluate(build_finished_probe()) is True


@pytest.mark.parametrize("body_text", [
    # The lobby copy is the dangerous false positive: it talks about completing
    # challenges but is NOT the completion page.
    "Complete 30 challenges in under 5 minutes",
    "Ready to start? Complete all the challenges!",
    "Step 5 of 30 — keep going",
    "Almost there, a few left to complete",
])
def test_looks_finished_rejects_lobby_and_progress_copy(challenge_page, body_text):
    page = challenge_page("data_attr.html", path="/complete")
    page.evaluate("(t) => { document.body.innerText = t; }", body_text)
    assert page.evaluate(build_finished_probe()) is False


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
