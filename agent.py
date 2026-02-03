#!/usr/bin/env python3
"""
Browser Challenge Agent
Solves 30 browser navigation challenges using DOM parsing and systematic modal handling.

Challenge Types Identified:
1. Scroll-revealed codes (scroll 500px+ to reveal)
2. Timer-delayed codes (wait 4+ seconds)
3. Hidden DOM codes (data-challenge-code attribute)
4. Direct code display

Modal Types:
- Cookie Consent (click Decline for privacy)
- Warning with fake close (use Dismiss button)
- Alert/Prize/Newsletter (use Close or X button)
- Radio selection modal (select option with "correct", then Submit)
- Overlay Notice (click Close)
"""

import asyncio
import time
import json
import re
from dataclasses import dataclass, field
from playwright.async_api import async_playwright, Page

CHALLENGE_URL = "https://serene-frangipane-7fd25b.netlify.app"


@dataclass
class Metrics:
    """Track performance metrics"""
    start_time: float = 0
    end_time: float = 0
    steps_completed: int = 0
    step_times: list = field(default_factory=list)
    errors: list = field(default_factory=list)

    def start(self):
        self.start_time = time.time()

    def step_complete(self, step_num: int):
        self.steps_completed = step_num
        elapsed = time.time() - self.start_time
        self.step_times.append({"step": step_num, "elapsed": round(elapsed, 2)})
        print(f"  ✓ Step {step_num} completed at {elapsed:.1f}s")

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
            "average_step_time": round(self.total_time / max(self.steps_completed, 1), 2),
            "under_5_minutes": self.total_time < 300,
            "step_times": self.step_times,
            "errors": self.errors
        }


class BrowserChallengeAgent:
    """Agent to solve browser navigation challenges"""

    # JavaScript to solve a step - handles all known patterns
    SOLVE_STEP_JS = """
    async function solveStep() {
        const results = {actions: [], code: null, error: null};

        // Helper to wait
        const wait = (ms) => new Promise(r => setTimeout(r, ms));

        // 1. Scroll down to reveal scroll-based codes
        window.scrollTo(0, 600);
        results.actions.push('scrolled');
        await wait(100);

        // 2. Close all modals - multiple passes
        for (let pass = 0; pass < 3; pass++) {
            document.querySelectorAll('button').forEach(btn => {
                const text = btn.textContent.toLowerCase().trim();
                // Priority: Dismiss (for fake-close), Decline (cookies), Close
                if (text === 'dismiss' || text === 'decline' || text === 'close') {
                    try { btn.click(); results.actions.push('closed:' + text); } catch(e) {}
                }
            });
            // Also click X buttons (buttons with no text or just X)
            document.querySelectorAll('button').forEach(btn => {
                if (btn.textContent.trim() === '' || btn.textContent.trim() === '×') {
                    try { btn.click(); results.actions.push('closed:X'); } catch(e) {}
                }
            });
            await wait(50);
        }

        // 3. Handle radio selection modals
        let radioSelected = false;
        document.querySelectorAll('input[type="radio"]').forEach(radio => {
            if (radioSelected) return;
            const label = radio.labels?.[0]?.textContent || radio.getAttribute('aria-label') || '';
            if (label.toLowerCase().includes('correct')) {
                radio.click();
                radioSelected = true;
                results.actions.push('radio:' + label.substring(0, 30));
            }
        });

        // Click Submit button in modal (not Submit Code)
        if (radioSelected) {
            await wait(50);
            document.querySelectorAll('button').forEach(btn => {
                const text = btn.textContent.trim();
                if ((text === 'Submit' || text.includes('Submit &')) && !text.includes('Code')) {
                    try { btn.click(); results.actions.push('modal-submit'); } catch(e) {}
                }
            });
            await wait(100);
        }

        // 4. Find the code - multiple strategies

        // Strategy A: Hidden in data attributes
        const codeEl = document.querySelector('[data-challenge-code]');
        if (codeEl) {
            results.code = codeEl.getAttribute('data-challenge-code');
            results.actions.push('code-source:data-attr');
        }

        // Strategy B: Look in page text for revealed codes
        if (!results.code) {
            const pageText = document.body.innerText;

            // Look for patterns like "Code: XXXXXX" or just standalone 6-char codes
            const patterns = [
                /(?:code|Code|CODE)[:\\s]+([A-Z0-9]{6})\\b/,
                /^([A-Z0-9]{6})$/m,
                /\\b(\\d{6})\\b/
            ];

            for (const pattern of patterns) {
                const match = pageText.match(pattern);
                if (match) {
                    results.code = match[1];
                    results.actions.push('code-source:text-pattern');
                    break;
                }
            }
        }

        // Strategy C: Look for specific code display elements
        if (!results.code) {
            // Codes often appear in elements near "code" text
            const allText = document.body.innerText;
            const lines = allText.split('\\n');
            for (const line of lines) {
                const trimmed = line.trim();
                if (/^[A-Z0-9]{6}$/.test(trimmed)) {
                    results.code = trimmed;
                    results.actions.push('code-source:standalone-line');
                    break;
                }
            }
        }

        // 5. Enter code and submit if found
        if (results.code) {
            const input = document.querySelector('input[placeholder*="code"], input[type="text"]');
            const submitBtn = document.querySelector('button[type="submit"]');

            if (input && submitBtn) {
                // Clear and set value with proper event dispatch
                input.value = '';
                input.value = results.code;
                input.dispatchEvent(new Event('input', {bubbles: true}));
                input.dispatchEvent(new Event('change', {bubbles: true}));

                await wait(50);
                submitBtn.click();
                results.actions.push('submitted');
            }
        }

        return results;
    }

    solveStep();
    """

    def __init__(self):
        self.page: Page = None
        self.metrics = Metrics()

    async def setup(self):
        """Initialize browser"""
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(
            headless=False,
            args=['--disable-blink-features=AutomationControlled']
        )
        self.context = await self.browser.new_context(
            viewport={"width": 1280, "height": 800}
        )
        self.page = await self.context.new_page()

    async def teardown(self):
        """Clean up browser"""
        await self.browser.close()
        await self.playwright.stop()

    async def get_current_step(self) -> int:
        """Get current step number from URL"""
        url = self.page.url
        match = re.search(r'/step(\d+)', url)
        return int(match.group(1)) if match else 0

    async def wait_for_dynamic_content(self):
        """Wait for timer-based and dynamic content"""
        # Some challenges have 4-second delays
        await asyncio.sleep(4.5)

    async def solve_step(self) -> bool:
        """Solve a single step"""
        current_step = await self.get_current_step()

        # Wait for dynamic content on first attempt
        await self.page.wait_for_load_state('networkidle')
        await self.wait_for_dynamic_content()

        # Execute the solve script
        try:
            result = await self.page.evaluate(self.SOLVE_STEP_JS)
            print(f"  Actions: {result.get('actions', [])}")
            print(f"  Code found: {result.get('code', 'None')}")
        except Exception as e:
            self.metrics.log_error(current_step, str(e))
            return False

        # Check if we advanced
        await asyncio.sleep(0.5)
        new_step = await self.get_current_step()

        if new_step > current_step:
            return True

        # If not advanced, try again with longer wait
        await asyncio.sleep(1)
        new_step = await self.get_current_step()
        return new_step > current_step

    async def run(self):
        """Main run loop"""
        print("=" * 60)
        print("BROWSER CHALLENGE AGENT")
        print("=" * 60)
        print(f"Target: {CHALLENGE_URL}")
        print(f"Goal: Complete 30 challenges in under 5 minutes")
        print("-" * 60)

        await self.setup()

        try:
            # Navigate and start
            await self.page.goto(CHALLENGE_URL)
            await self.page.wait_for_load_state('networkidle')

            # Click START
            start_btn = await self.page.query_selector('button:has-text("START")')
            if start_btn:
                await start_btn.click()
                await asyncio.sleep(1)

            self.metrics.start()
            print(f"\nStarted at: {time.strftime('%H:%M:%S')}")
            print("-" * 60)

            # Solve all 30 steps
            max_retries = 5
            retries = 0

            while True:
                current_step = await self.get_current_step()

                if current_step == 0:
                    retries += 1
                    if retries > max_retries:
                        print("Failed to start challenge")
                        break
                    await asyncio.sleep(1)
                    continue

                if current_step > 30:
                    print("\n🎉 ALL 30 CHALLENGES COMPLETED!")
                    break

                print(f"\n[Step {current_step}/30]")

                solved = await self.solve_step()

                if solved:
                    self.metrics.step_complete(current_step)
                    retries = 0
                else:
                    retries += 1
                    print(f"  ⚠ Retry {retries}/{max_retries}")
                    if retries >= max_retries:
                        print(f"  ✗ Failed after {max_retries} retries")
                        self.metrics.log_error(current_step, "Max retries exceeded")
                        break
                    await asyncio.sleep(2)

            self.metrics.finish()

        except Exception as e:
            print(f"\nFatal error: {e}")
            self.metrics.finish()

        # Print results
        print("\n" + "=" * 60)
        print("RESULTS")
        print("=" * 60)
        results = self.metrics.to_dict()
        print(f"Total Time: {results['total_time_seconds']}s")
        print(f"Steps Completed: {results['steps_completed']}/30")
        print(f"Average Step Time: {results['average_step_time']}s")
        print(f"Under 5 Minutes: {'✓ YES' if results['under_5_minutes'] else '✗ NO'}")

        if results['errors']:
            print(f"\nErrors: {len(results['errors'])}")
            for err in results['errors']:
                print(f"  - Step {err['step']}: {err['error']}")

        # Save metrics
        with open("metrics.json", "w") as f:
            json.dump(results, f, indent=2)
        print(f"\nMetrics saved to metrics.json")

        await self.teardown()
        return self.metrics


async def main():
    agent = BrowserChallengeAgent()
    await agent.run()


if __name__ == "__main__":
    asyncio.run(main())
