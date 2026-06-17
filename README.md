# Browser Challenge Agent

An automated browser agent for the [Browser Navigation Challenge](https://serene-frangipane-7fd25b.netlify.app) — 30 UI challenges (modals, forms, hidden codes, distractors) to complete in under 5 minutes.

The solver is deterministic DOM logic — no LLM calls, no screenshots, zero token cost. One shared in-page script (`fast_solver.js`) holds all the challenge heuristics; the Python agent (`agent.py`) drives it with Playwright and records metrics.

## Challenge patterns handled

- Scroll-revealed codes (revealed past ~500px)
- Timer-delayed codes (polled until they appear)
- Click-to-reveal ("Reveal Code" buttons)
- Hidden DOM codes (`data-challenge-code` attribute)
- Inline labelled codes ("Code: ABC123" / "code is ABC123")
- Standalone codes — prefers a digit-bearing line, so 6-letter distractor words ("PUZZLE", "REVEAL") aren't mistaken for a code
- Popup modals — Dismiss / Decline / Close / icon-only ×, including fake-close decoys
- Radio quiz modals — picks "Correct", not "**In**correct" (substring traps)
- "I agree" / "I'm human" gates — checks the box only when it's keeping the submit button disabled
- Distractor avoidance — exact-text matching so "Accept All" / "Close Account" style buttons are never clicked

## Setup

```bash
pip install -r requirements.txt
playwright install chromium
```

## Usage

```bash
# Run the agent (headed browser, writes metrics.json)
python agent.py

# Useful flags
python agent.py --headless            # no visible browser window
python agent.py --metrics             # also print the metrics JSON to stdout
python agent.py --step-timeout 20     # seconds per step before retrying
python agent.py --url https://...     # point at a different deployment
```

Exit code is `0` when all steps complete, `1` otherwise.

Alternatively, start the challenge in any browser and paste the whole of
`fast_solver.js` into the DevTools console — it auto-runs and logs a
`RESULTS:` summary when it stops.

## How it works

```
agent.py (Playwright driver)
  ├─ opens the site, clicks START
  ├─ per step: injects fast_solver.js and calls solveStepLoop()
  │     └─ polls every ~40ms: scroll → close modals → click reveals →
  │        satisfy submit gates → answer radio quizzes → hunt for the
  │        code → type + submit
  ├─ confirms progress from the URL (/stepN), tolerating full navigations
  └─ records metrics.json (per-step times, attempts, codes, errors)
```

Design choices that matter:

- **DOM-first, vision-free** — parsing the page is orders of magnitude faster
  than screenshot loops, which is what makes the 5-minute budget comfortable.
- **Poll, don't sleep** — timer-delayed codes are detected the moment they
  appear instead of waiting a fixed worst-case delay per step.
- **Native value setter** — codes are typed via the native `value` setter +
  `input` event so React-controlled inputs register the change.
- **Submission throttling** — a found code is submitted once, then only
  re-submitted occasionally, rather than hammering the form on every poll.

## Metrics

`metrics.json` (and `--metrics` stdout) reports total time, per-step elapsed
time / attempts / code, whether the run finished, whether it beat 5 minutes,
and any errors.

## Tests

```bash
pip install -r requirements-dev.txt
pytest
```

The suite runs the real solver script against local HTML fixtures
(`tests/fixtures/`) that replicate each challenge pattern — served from
memory via request interception, so no network is touched. It also covers the
Python driver loop (retries, navigation races, completion detection) and a
full agent run against a miniature SPA version of the challenge site.

## License

MIT
