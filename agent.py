#!/usr/bin/env python3
"""
Browser Challenge Agent

Drives the shared in-page solver (fast_solver.js) with Playwright to complete
30 browser navigation challenges, tracking per-step metrics along the way.

Challenge types handled (see fast_solver.js for the in-page logic):
1. Scroll-revealed codes (scroll 500px+ to reveal)
2. Timer-delayed codes (polled until they appear)
3. Hidden DOM codes (data-challenge-code attribute)
4. Direct / labelled code display ("Code: ABC123"); standalone codes prefer
   a digit-bearing line over 6-letter distractor words
5. Modal dismissal (Dismiss / Decline / Close / icon-only ×)
6. Quiz modals — radio buttons or a <select> dropdown (pick "Correct", not
   "Incorrect")
7. "I agree" / "I'm human" gates (check the gate-like box to enable a disabled
   submit, leaving decoy checkboxes alone)
"""

import argparse
import asyncio
import functools
import json
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

from playwright.async_api import async_playwright

DEFAULT_URL = "https://serene-frangipane-7fd25b.netlify.app"
SOLVER_PATH = Path(__file__).resolve().parent / "fast_solver.js"

# Raised by Playwright when the page navigates away mid-evaluate. For this
# site that usually means the solver submitted a correct code and a full
# navigation (rather than a pushState) followed.
CONTEXT_DESTROYED = "execution context was destroyed"


def parse_step(url: str) -> int:
    """Step number embedded in a challenge URL, or 0 if there is none
    (lobby or completion page)."""
    match = re.search(r"/step(\d+)", url)
    return int(match.group(1)) if match else 0


@functools.lru_cache(maxsize=1)
def solver_source() -> str:
    return SOLVER_PATH.read_text(encoding="utf-8")


def _embed_solver(body: str) -> str:
    """Wrap the shared solver source in a function scope with the auto-run
    gate disabled, then run `body` with the solver's functions in scope.

    The gate is a scoped `var`, not a page global, so embedding leaves no
    trace behind: pasting fast_solver.js into the console later still
    auto-runs.
    """
    return (
        "async () => {\n"
        "var __SOLVER_EMBEDDED__ = true;\n"
        f"{solver_source()}\n"
        f"{body}\n"
        "}"
    )


def build_solver_script(step_timeout_ms: int, poll_ms: int = 40, max_steps: int = 30) -> str:
    """One evaluate() of this script solves (at most) one step."""
    opts = json.dumps({"maxMs": step_timeout_ms, "pollMs": poll_ms, "maxSteps": max_steps})
    return _embed_solver(f"return await solveStepLoop({opts});")


@functools.lru_cache(maxsize=1)
def build_finished_probe() -> str:
    """Script that reports whether the page looks like the completion page,
    using the same looksFinished() the in-page solver uses."""
    return _embed_solver("return looksFinished();")


@dataclass
class Metrics:
    """Track performance metrics"""
    start_time: float = 0
    end_time: float = 0
    steps_completed: int = 0
    finished: bool = False
    step_times: list = field(default_factory=list)
    errors: list = field(default_factory=list)

    def start(self):
        self.start_time = time.time()

    def step_complete(self, step_num: int, attempts: int = 0, code: str = None):
        self.steps_completed = max(self.steps_completed, step_num)
        elapsed = time.time() - self.start_time
        self.step_times.append({
            "step": step_num,
            "elapsed": round(elapsed, 2),
            "attempts": attempts,
            "code": code,
        })
        print(f"  ✓ Step {step_num} completed at {elapsed:.1f}s ({attempts} passes)")

    def log_error(self, step: int, error: str):
        self.errors.append({"step": step, "error": error})

    def finish(self):
        self.end_time = time.time()

    @property
    def total_time(self) -> float:
        return self.end_time - self.start_time

    def to_dict(self) -> dict:
        return {
            "total_time_seconds": round(self.total_time, 2),
            "steps_completed": self.steps_completed,
            "finished": self.finished,
            "average_step_time": round(self.total_time / max(self.steps_completed, 1), 2),
            "under_5_minutes": self.finished and self.total_time < 300,
            "step_times": self.step_times,
            "errors": self.errors,
        }


class BrowserChallengeAgent:
    """Agent to solve browser navigation challenges."""

    def __init__(self, url: str = DEFAULT_URL, headless: bool = False,
                 max_steps: int = 30, step_timeout: float = 15.0,
                 poll_ms: int = 40, retries: int = 3):
        self.url = url
        self.headless = headless
        self.max_steps = max_steps
        self.step_timeout = step_timeout
        self.poll_ms = poll_ms
        self.retries = retries
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None
        self.metrics = Metrics()
        self.solver_script = build_solver_script(
            step_timeout_ms=int(step_timeout * 1000),
            poll_ms=poll_ms,
            max_steps=max_steps,
        )

    async def setup(self):
        """Initialize browser"""
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(
            headless=self.headless,
            args=['--disable-blink-features=AutomationControlled']
        )
        self.context = await self.browser.new_context(
            viewport={"width": 1280, "height": 800}
        )
        self.page = await self.context.new_page()

    async def teardown(self):
        """Clean up browser"""
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
        self.playwright = self.browser = self.context = self.page = None

    async def start_challenge(self):
        """Navigate to the lobby and press START."""
        await self.page.goto(self.url)
        try:
            await self.page.wait_for_load_state('networkidle', timeout=10_000)
        except Exception:
            pass  # analytics beacons can keep the network busy forever

        start_btn = await self.page.query_selector('button:has-text("START")')
        if start_btn:
            await start_btn.click()
        try:
            await self.page.wait_for_url(re.compile(r"/step\d+"), timeout=5_000)
        except Exception:
            pass  # the loop re-checks the URL and retries the start

    async def _looks_finished(self) -> bool:
        try:
            return bool(await self.page.evaluate(build_finished_probe()))
        except Exception:
            return False

    async def _solve_step_js(self, step: int) -> dict:
        """Run the in-page solver for one step, tolerating full navigations."""
        try:
            return await self.page.evaluate(self.solver_script)
        except Exception as exc:
            if CONTEXT_DESTROYED not in str(exc).lower():
                self.metrics.log_error(step, str(exc))
            try:
                await self.page.wait_for_load_state('domcontentloaded', timeout=5_000)
            except Exception:
                pass
            # Let the caller re-derive progress from the URL.
            return {"advanced": False, "attempts": 0, "code": None}

    async def _solve_loop(self) -> bool:
        """Solve steps until completion, a reset, or retry exhaustion.

        Returns True when the whole challenge finished.
        """
        # Lobby restarts and stuck steps are different failure modes; each
        # gets its own budget so one can't starve the other.
        start_retries = 0
        step_retries = 0
        last_step = None
        while True:
            step = parse_step(self.page.url)
            if step != last_step:
                # A late advance can land during the retry sleep; a new step
                # number always means a fresh retry budget.
                step_retries = 0
                last_step = step

            if step == 0:
                # The steps_completed guard keeps lobby copy like "Complete 30
                # challenges" from reading as a completion page before we start.
                if self.metrics.steps_completed >= self.max_steps or (
                    self.metrics.steps_completed > 0 and await self._looks_finished()
                ):
                    return True
                start_retries += 1
                if start_retries >= self.retries:
                    print("Failed to reach a challenge step — is the START button there?")
                    return False
                print("  ⚠ No step in URL — trying to (re)start the challenge")
                try:
                    await self.start_challenge()
                except Exception as exc:
                    self.metrics.log_error(0, f"restart failed: {exc}")
                    await asyncio.sleep(1)
                continue

            if step > self.max_steps:
                return True

            print(f"\n[Step {step}/{self.max_steps}]")
            result = await self._solve_step_js(step)

            # Trust the URL over the in-page verdict: a navigation can land
            # between the solver's last poll and its return.
            new_step = parse_step(self.page.url)
            advanced = bool(result.get("advanced")) or new_step > step
            finished = bool(result.get("finished")) or new_step > self.max_steps or (
                new_step == 0 and (step >= self.max_steps or await self._looks_finished())
            )

            if advanced or finished:
                self.metrics.step_complete(step, result.get("attempts", 0), result.get("code"))
                step_retries = 0
                if finished:
                    return True
                continue

            step_retries += 1
            reason = "reset" if result.get("reset") else "timeout" if result.get("timeout") else "stuck"
            print(f"  ⚠ Step {step} {reason} — retry {step_retries}/{self.retries}")
            if step_retries >= self.retries:
                self.metrics.log_error(step, f"Gave up after {self.retries} retries ({reason})")
                return False
            await asyncio.sleep(1)

    def _report(self, metrics_file: str, print_json: bool):
        results = self.metrics.to_dict()
        print("\n" + "=" * 60)
        print("RESULTS")
        print("=" * 60)
        print(f"Total Time: {results['total_time_seconds']}s")
        print(f"Steps Completed: {results['steps_completed']}/{self.max_steps}")
        print(f"Average Step Time: {results['average_step_time']}s")
        print(f"Finished: {'✓ YES' if results['finished'] else '✗ NO'}")
        print(f"Under 5 Minutes: {'✓ YES' if results['under_5_minutes'] else '✗ NO'}")

        if results['errors']:
            print(f"\nErrors: {len(results['errors'])}")
            for err in results['errors']:
                print(f"  - Step {err['step']}: {err['error']}")

        if metrics_file:
            with open(metrics_file, "w") as f:
                json.dump(results, f, indent=2)
            print(f"\nMetrics saved to {metrics_file}")

        if print_json:
            print(json.dumps(results, indent=2))

    async def run(self, metrics_file: str = "metrics.json", print_json: bool = False) -> Metrics:
        """Main entry point: returns the collected Metrics."""
        print("=" * 60)
        print("BROWSER CHALLENGE AGENT")
        print("=" * 60)
        print(f"Target: {self.url}")
        print(f"Goal: Complete {self.max_steps} challenges in under 5 minutes")
        print("-" * 60)

        owns_browser = self.page is None
        try:
            if owns_browser:
                await self.setup()
            await self.start_challenge()
            self.metrics.start()
            print(f"\nStarted at: {time.strftime('%H:%M:%S')}")
            print("-" * 60)
            try:
                self.metrics.finished = await self._solve_loop()
                if self.metrics.finished:
                    print(f"\n🎉 ALL {self.max_steps} CHALLENGES COMPLETED!")
            finally:
                self.metrics.finish()
                self._report(metrics_file, print_json)
        finally:
            if owns_browser:
                await self.teardown()

        return self.metrics


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Solve the browser navigation challenge and report metrics."
    )
    parser.add_argument("--url", default=DEFAULT_URL, help="challenge URL")
    parser.add_argument("--headless", action="store_true",
                        help="run the browser headless (default: headed)")
    parser.add_argument("--max-steps", type=int, default=30,
                        help="number of steps in the challenge")
    parser.add_argument("--step-timeout", type=float, default=15.0,
                        help="seconds to spend on a step before retrying")
    parser.add_argument("--poll-ms", type=int, default=40,
                        help="in-page poll interval in milliseconds")
    parser.add_argument("--retries", type=int, default=3,
                        help="retries per step before giving up")
    parser.add_argument("--metrics", action="store_true",
                        help="print the full metrics JSON to stdout")
    parser.add_argument("--metrics-file", default="metrics.json",
                        help="where to write metrics JSON ('' to skip)")
    return parser.parse_args(argv)


async def main(argv=None) -> int:
    args = parse_args(argv)
    agent = BrowserChallengeAgent(
        url=args.url,
        headless=args.headless,
        max_steps=args.max_steps,
        step_timeout=args.step_timeout,
        poll_ms=args.poll_ms,
        retries=args.retries,
    )
    metrics = await agent.run(metrics_file=args.metrics_file, print_json=args.metrics)
    return 0 if metrics.finished else 1


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except KeyboardInterrupt:
        print("\nInterrupted.")
        sys.exit(130)
