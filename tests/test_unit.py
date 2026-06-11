"""Pure-Python unit tests — no browser required."""

import time

from agent import Metrics, build_finished_probe, build_solver_script, parse_step


class TestParseStep:
    def test_lobby_url(self):
        assert parse_step("https://serene-frangipane-7fd25b.netlify.app/") == 0

    def test_step_urls(self):
        assert parse_step("https://x.netlify.app/step1") == 1
        assert parse_step("https://x.netlify.app/step12") == 12
        assert parse_step("https://x.netlify.app/step3?utm=1") == 3

    def test_non_step_urls(self):
        assert parse_step("about:blank") == 0
        assert parse_step("https://x.netlify.app/complete") == 0


class TestMetrics:
    def test_step_complete_tracks_progress(self):
        m = Metrics()
        m.start()
        m.step_complete(1, attempts=2, code="AB12CD")
        m.finish()
        d = m.to_dict()
        assert d["steps_completed"] == 1
        assert d["step_times"][0]["step"] == 1
        assert d["step_times"][0]["attempts"] == 2
        assert d["step_times"][0]["code"] == "AB12CD"

    def test_steps_completed_never_regresses(self):
        m = Metrics()
        m.start()
        m.step_complete(3)
        m.step_complete(2)  # e.g. the site reset us and we re-solved step 2
        assert m.steps_completed == 3

    def test_under_5_minutes_requires_finishing(self):
        m = Metrics()
        m.start()
        m.finish()
        assert m.total_time < 300
        assert m.to_dict()["under_5_minutes"] is False  # fast but not finished
        m.finished = True
        assert m.to_dict()["under_5_minutes"] is True

    def test_errors_logged(self):
        m = Metrics()
        m.log_error(4, "boom")
        assert m.to_dict()["errors"] == [{"step": 4, "error": "boom"}]


class TestSolverScripts:
    def test_solver_script_embeds_source_and_options(self):
        script = build_solver_script(step_timeout_ms=5000, poll_ms=25, max_steps=7)
        assert script.startswith("async () =>")
        assert "__SOLVER_EMBEDDED__ = true" in script
        assert "solveOnePass" in script  # the shared source is embedded
        assert '"maxMs": 5000' in script
        assert '"pollMs": 25' in script
        assert '"maxSteps": 7' in script

    def test_finished_probe_uses_shared_looks_finished(self):
        probe = build_finished_probe()
        assert "__SOLVER_EMBEDDED__ = true" in probe
        assert "return looksFinished();" in probe
