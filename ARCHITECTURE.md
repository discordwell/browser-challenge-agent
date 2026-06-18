# Architecture

## Components

```
┌────────────────────────────────────────────────────────────┐
│ agent.py — Playwright driver (Python, async)               │
│   BrowserChallengeAgent                                    │
│     setup/teardown          browser lifecycle              │
│     start_challenge()       goto + START button            │
│     _solve_loop()           step loop, retries, completion │
│     _solve_step_js()        one evaluate() per step        │
│   Metrics                   per-step times/attempts/codes  │
│   parse_step(url)           /stepN → N (pure)              │
│   build_solver_script()     wraps fast_solver.js source    │
│   build_finished_probe()    wraps looksFinished()          │
└────────────────────────────────────────────────────────────┘
                          │ embeds (single source of truth)
                          ▼
┌────────────────────────────────────────────────────────────┐
│ fast_solver.js — in-page solver core (vanilla JS)          │
│   solveOnePass(state)   scroll, close modals, reveal,      │
│                         submit gates, quiz modals          │
│                         (radio / select), find code, submit│
│   findSubmitButton()    the page's main submit control     │
│   solveStepLoop(opts)   poll one step until URL advances,  │
│                         completion, reset, or timeout      │
│   solveAllSteps(opts)   loop all steps (console usage)     │
│   looksFinished()       completion-page text heuristic     │
│   auto-run gate         runs solveAllSteps() when pasted   │
│                         into a console; agent.py disables  │
│                         it via __SOLVER_EMBEDDED__         │
└────────────────────────────────────────────────────────────┘
```

## Key decisions

- **One copy of the solving heuristics.** `fast_solver.js` is both the
  console-paste tool and the script `agent.py` injects. The Python side wraps
  the file in `async () => { ... }` so its function declarations stay scoped,
  and declares `var __SOLVER_EMBEDDED__ = true` in that scope so the console
  auto-run stays off. The gate is checked with `typeof`, never set on the
  page's globals — embedding leaves no trace, so pasting the file into the
  console later still auto-runs.

- **Progress = URL.** The site exposes the current step as `/stepN`. The
  in-page loop polls it; the Python loop re-checks it after every evaluate and
  trusts the URL over the in-page verdict (a navigation can land between the
  solver's last poll and its return). If the page hard-navigates mid-evaluate
  ("execution context destroyed"), the driver treats it as a probable advance
  and re-derives state from the URL.

- **Completion detection.** After the final step the URL loses its step
  token. That alone counts as completion only when the last step was ≥
  `max_steps`; otherwise the page text must match `looksFinished()` — a
  deliberately specific regex ("congrat…", "challenge complete", …) so lobby
  copy like "Complete 30 challenges in under 5 minutes" can never
  false-positive. The Python side additionally requires at least one
  completed step before accepting a text match.

- **Safety against distractors.** Modal buttons are matched on exact text
  (`dismiss`/`decline`/`close`/empty/`×`); quiz answers (radio buttons or a
  `<select>` dropdown) must contain the word "correct" not preceded by a letter
  (rejects "Incorrect"); and the modal-confirm pass clicks `Submit`/`Submit & …`
  but never `Submit Code`. A `<select>` is driven through the native value
  setter + `change` event, the same React-aware path the code input uses.
  Click-to-reveal buttons (`isRevealButton`) match anything containing
  "reveal", plus other reveal verbs (show/unlock/display/view/see/get/generate)
  only when the text also mentions the *code* — so "Show menu" or the
  "Submit Code" control is never mistaken for a reveal.

- **Code detection — gather candidates, prefer digits.** A candidate is
  collected from each source: the `data-challenge-code` attribute, a *labelled*
  code (`Code: ABC123`) whose value must sit on the same line as the keyword
  (so the "Code" in a "Submit Code" button can't reach a token on the next
  line), and a *standalone* `^[A-Z0-9]{6}$` line. The pick order is: explicit
  attribute → digit-bearing labelled code → digit-bearing standalone line → any
  standalone line → all-letter labelled value (last resort). Because every real
  code mixes letters and digits, that digit preference is what stops a 6-letter
  word *after* "code" (`the code is HIDDEN`) **and** a standalone distractor
  word (`PUZZLE`/`REVEAL`/`SUBMIT`) from beating the real, digit-bearing code —
  while an all-letter code is still found when nothing better exists.

- **Submit gates.** Some steps disable the submit button until an "I agree" /
  "I'm human" checkbox is ticked. The solver acts only while the submit button
  is actually `disabled`, and ticks just **one** box per pass — the most
  gate-like unchecked one (label matching `agree|consent|terms|human|robot|…`),
  letting the next poll observe whether submit unlocked. So ordinary pages are
  untouched, and a decoy box (a newsletter opt-in listed alongside the real
  gate) is never ticked once the real box has already enabled the button. This
  also gives a React re-render a tick to land between checking and re-reading
  `disabled`.

- **Throttled submission.** A found code is typed via the native value setter
  (React compatibility) and submitted once; the same code is only re-submitted
  after 800ms (time-based, so the interval doesn't drift with the poll rate)
  in case an event was dropped — wrong guesses can't hammer the form. A newly
  discovered different code is submitted immediately.

## Tests (`tests/`)

- `test_unit.py` — pure functions (`parse_step`, `Metrics`, script builders).
- `test_solver_browser.py` — the real solver JS against `tests/fixtures/*.html`,
  one fixture per challenge pattern, served from memory via `page.route` on a
  fake `https://challenge.test` origin (no network). Includes console-paste
  auto-run mode.
- `test_agent_loop.py` — `_solve_loop` driven by a scripted FakePage: retries,
  context-destroyed navigation races, text-detected completion, lobby
  false-positive guard.
- `test_agent_e2e.py` — full `BrowserChallengeAgent.run()` against
  `fixtures/spa_challenge.html`, a two-step miniature of the real site
  (lobby + START + pushState routing + completion page).
