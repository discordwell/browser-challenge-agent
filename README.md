# Browser Challenge Agent

[![CI](https://github.com/discordwell/browser-challenge-agent/actions/workflows/ci.yml/badge.svg)](https://github.com/discordwell/browser-challenge-agent/actions/workflows/ci.yml)

An automated browser agent for the [Browser Navigation Challenge](https://serene-frangipane-7fd25b.netlify.app) — 30 UI challenges (modals, forms, hidden codes, distractors) to complete in under 5 minutes.

The solver is deterministic DOM logic — no LLM calls, no screenshots, zero token cost. One shared in-page script (`fast_solver.js`) holds all the challenge heuristics; the Python agent (`agent.py`) drives it with Playwright and records metrics.

## Challenge patterns handled

- Scroll-revealed codes (revealed past ~500px)
- Timer-delayed codes (polled until they appear)
- Click-to-reveal — "Reveal Code", and other wordings of the same control
  ("Show Code" / "Unlock Code" / "Display the code"); generic buttons that don't
  mention the code are left alone
- Hidden DOM codes (`data-challenge-code` attribute)
- Inline labelled codes ("Code: ABC123" / "code is ABC123")
- Standalone codes — prefers a digit-bearing line, so 6-letter distractor words ("PUZZLE", "REVEAL") aren't mistaken for a code
- Popup modals — Dismiss / Decline / Close / icon-only ×, including fake-close decoys
- Quiz modals — radio buttons or a `<select>` dropdown; picks "Correct", not "**In**correct" (substring traps)
- "I agree" / "I'm human" gates — checks the gate-like box only while it's keeping the submit button disabled, one box per poll, so a decoy "sign me up" checkbox is left unchecked. Both native `disabled` and the accessible/React `aria-disabled="true"` idiom count as gated; because `aria-disabled` is a weaker, sometimes-stale hint, a box is ticked on its account only when its label is an affirmative consent phrase ("I agree" / "I'm human"), never benign copy that merely mentions a keyword
- Distractor avoidance — exact-text matching so "Accept All" / "Close Account" style buttons are never clicked; the code is typed into the real code field (matched by meaning) even when a decoy text input — a newsletter "email" or "Promo code" box — is listed first

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
- **Decoy-safe code field** — the input is picked by *meaning*, not DOM order:
  a field whose placeholder, `name`, `id`, `aria-label`, or `<label>` mentions
  "code" wins wherever it sits, so a decoy text input listed first (a newsletter
  "email" box) isn't typed into. A "code" with a non-challenge qualifier (a
  "Promo code" / "Area code" box) is rejected, so widening the match past the
  placeholder doesn't open a new distractor. Only when nothing is
  code-associated does it fall back to the first text-like input — `text`,
  `search`, or a bare `<input>` (no `type`, which defaults to text).
- **Form-scoped submit** — the code is submitted through the code field's own
  `<form>`, so a real submit control wins whatever its label ("Verify Code",
  "Continue") and a decoy form's button (a newsletter "Subscribe" above the
  real form) is never clicked. Both `<button type="submit">` and
  `<input type="submit">` count.
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

GitHub Actions (`.github/workflows/ci.yml`) runs `node --check fast_solver.js`
and the full `pytest` suite (with Playwright Chromium) on every push and pull
request. Browser-backed tests skip themselves if Chromium can't be installed,
so the pure-Python tests still gate the build.

## License

MIT
