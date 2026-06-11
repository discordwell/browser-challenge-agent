"""End-to-end: the full Python agent (start button, solver injection, metrics,
completion detection) against the local SPA fixture — a miniature of the real
challenge site, served entirely from memory."""

import asyncio

import pytest

from agent import BrowserChallengeAgent
from conftest import ORIGIN, fixture_html


def test_full_agent_run_on_local_spa():
    asyncio.run(_run())


async def _run():
    # conftest's browser fixture is the sync API; the agent is async, so this
    # test owns its own (async) browser lifecycle.
    from playwright.async_api import async_playwright

    html = fixture_html("spa_challenge.html")

    async with async_playwright() as p:
        try:
            browser = await p.chromium.launch(headless=True)
        except Exception as exc:
            pytest.skip(f"chromium unavailable: {exc}")
        try:
            context = await browser.new_context()
            page = await context.new_page()

            async def serve(route):
                await route.fulfill(status=200, content_type="text/html", body=html)

            await page.route(f"{ORIGIN}/**", serve)

            agent = BrowserChallengeAgent(
                url=f"{ORIGIN}/",
                headless=True,
                max_steps=2,
                step_timeout=8.0,
                retries=2,
            )
            agent.page = page  # inject: the agent must not own the browser
            metrics = await agent.run(metrics_file="", print_json=False)

            assert metrics.finished is True
            assert metrics.steps_completed == 2
            assert metrics.errors == []
            assert metrics.to_dict()["under_5_minutes"] is True
            assert page.url == f"{ORIGIN}/complete"
        finally:
            await browser.close()
