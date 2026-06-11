"""Tests for BrowserChallengeAgent._solve_loop using a scripted fake page —
covers driver behaviour (retries, navigation races, completion detection)
without launching a browser."""

import asyncio

from agent import BrowserChallengeAgent


class FakePage:
    """Stand-in for a Playwright page. Each scripted step is a callable that
    may mutate the fake's URL, return a solver result dict, or raise."""

    def __init__(self, url, steps=(), finished_text=False):
        self.url = url
        self.steps = list(steps)
        self.finished_text = finished_text

    async def evaluate(self, script):
        if "return looksFinished();" in script:
            return self.finished_text
        action = self.steps.pop(0)
        return action(self)

    async def wait_for_load_state(self, *args, **kwargs):
        return None

    # start_challenge() support, for tests that reach the restart path.
    async def goto(self, url):
        self.url = url

    async def wait_for_url(self, *args, **kwargs):
        return None

    async def query_selector(self, selector):
        return None


def make_agent(page, **kwargs):
    agent = BrowserChallengeAgent(headless=True, **kwargs)
    agent.page = page
    agent.metrics.start()
    return agent


def test_solve_loop_completes_when_js_reports_finished():
    def s1(p):
        p.url = "https://x/step2"
        return {"advanced": True, "finished": False, "attempts": 3, "code": "AB12CD"}

    def s2(p):
        p.url = "https://x/complete"
        return {"advanced": True, "finished": True, "attempts": 1, "code": "EF34GH"}

    page = FakePage("https://x/step1", [s1, s2])
    agent = make_agent(page, max_steps=2)
    assert asyncio.run(agent._solve_loop()) is True
    assert agent.metrics.steps_completed == 2
    assert len(agent.metrics.step_times) == 2
    assert agent.metrics.errors == []


def test_solve_loop_survives_context_destroyed_navigation():
    def s1(p):
        p.url = "https://x/step2"
        raise Exception(
            "Execution context was destroyed, most likely because of a navigation"
        )

    def s2(p):
        p.url = "https://x/step3"
        return {"advanced": True, "finished": False, "attempts": 2, "code": "EF34GH"}

    page = FakePage("https://x/step1", [s1, s2])
    agent = make_agent(page, max_steps=2)
    assert asyncio.run(agent._solve_loop()) is True
    assert agent.metrics.steps_completed == 2
    # A navigation race is normal operation, not an error.
    assert agent.metrics.errors == []


def test_solve_loop_gives_up_after_retries():
    def stuck(p):
        return {"advanced": False, "timeout": True, "attempts": 50, "code": None}

    page = FakePage("https://x/step1", [stuck])
    agent = make_agent(page, max_steps=30, retries=1)
    assert asyncio.run(agent._solve_loop()) is False
    assert agent.metrics.errors
    assert agent.metrics.steps_completed == 0


class SteppingURLPage(FakePage):
    """FakePage whose URL follows a scripted sequence of reads, so the URL can
    'change' between loop iterations (e.g. during the retry sleep)."""

    def __init__(self, url_sequence, steps, **kwargs):
        super().__init__(url_sequence[0], steps, **kwargs)
        self._seq = list(url_sequence)

    @property
    def url(self):
        if len(self._seq) > 1:
            return self._seq.pop(0)
        return self._seq[0]

    @url.setter
    def url(self, value):
        self._seq = [value]


def test_retry_budget_resets_when_step_advances_during_retry_sleep():
    # Step 1 times out, but the submission lands server-side during the retry
    # sleep and the URL moves on. Step 2 must get a full retry budget, not
    # inherit step 1's spent retries.
    def fail(p):
        return {"advanced": False, "timeout": True, "attempts": 50, "code": None}

    def succeed(p):
        return {"advanced": True, "finished": True, "attempts": 1, "code": "EF34GH"}

    urls = ["https://x/step1", "https://x/step1", "https://x/step2"]
    page = SteppingURLPage(urls, [fail, fail, succeed])
    agent = make_agent(page, max_steps=2, retries=2)
    assert asyncio.run(agent._solve_loop()) is True


def test_solve_loop_accepts_text_detected_completion():
    def s(p):
        p.url = "https://x/done"
        return {"advanced": False, "reset": True, "attempts": 9, "code": None}

    page = FakePage("https://x/step5", [s], finished_text=True)
    agent = make_agent(page, max_steps=30)
    assert asyncio.run(agent._solve_loop()) is True
    assert agent.metrics.steps_completed == 5


def test_lobby_text_does_not_count_as_completion_before_any_step():
    # Lobby copy can match completion-ish phrases; with zero steps completed
    # the loop must not declare victory, it should try to (re)start instead.
    page = FakePage("https://x/", finished_text=True)
    agent = make_agent(page, max_steps=30, retries=0)
    agent.url = "https://x/"
    assert asyncio.run(agent._solve_loop()) is False


def test_step_count_completion_when_url_loses_step_token():
    page = FakePage("https://x/", finished_text=False)
    agent = make_agent(page, max_steps=30)
    agent.metrics.steps_completed = 30
    assert asyncio.run(agent._solve_loop()) is True
