# Claudepad

## Session Summaries

### 2026-06-11 — Solver unification, driver rewrite, first test suite
- Made `fast_solver.js` the single source of truth: `solveOnePass` /
  `solveStepLoop` / `solveAllSteps` + `looksFinished`, with a scope-local
  auto-run gate (`typeof __SOLVER_EMBEDDED__` — no page-global pollution) so
  it still works as a console paste while `agent.py` embeds the same file.
- Rewrote `agent.py`: per-step in-page polling (~40ms) replaces the fixed
  4.5s/step sleep; codes typed via native value setter (React fix the old
  Python JS lacked); completion after step 30 detected (URL loses the step
  token); argparse CLI (`--headless`, `--url`, `--metrics`, `--metrics-file`,
  `--max-steps`, `--step-timeout`, `--retries`); try/finally teardown; exit
  code 0/1; survives "execution context destroyed" navigation races; restarts
  from the lobby if the site resets.
- Fixed radio-quiz bug present in both old copies: `includes('correct')`
  also matched "Incorrect" — now requires "correct" not preceded by a letter.
- Added throttled code submission (same code re-submitted only after 800ms)
  and a tightened completion regex so lobby copy ("Complete 30 challenges…")
  can't read as the completion page.
- Max-effort code review (9 finder angles) ran over the diff; confirmed fixes
  applied: `CODE:` uppercase label support + `\b` anchor (no "barcode" match),
  scope-local embed gate, Object.assign over for-in, time-based resubmit,
  setup() inside try/finally (no Playwright subprocess leak on launch
  failure), teardown resets handles (agent reusable), split lobby/step retry
  budgets, cached finished-probe, `wait_for_url` instead of a sleep poll,
  `--poll-ms` flag.
- New pytest suite: 27 tests, all passing in ~4s. Real solver JS runs against
  local HTML fixtures (one per challenge pattern) served from memory on a fake
  origin; FakePage tests for the driver loop; full e2e agent run on a
  miniature SPA of the challenge site. `pip install -r requirements-dev.txt
  && pytest`.
- Housekeeping: `.gitignore` (metrics.json etc.), dropped unused
  `anthropic`/`rich` deps, README rewritten to match reality, ARCHITECTURE.md
  added.

## Key Findings

- The challenge site is a React SPA with pushState routing; progress is
  readable from the URL (`/stepN`). Plain `input.value = x` does NOT register
  with React — must use the native `HTMLInputElement` value setter + `input`
  event (this was why the original `agent.py` JS could fail to submit).
- Playwright `page.evaluate()` with a multi-statement string runs it
  expression-style via indirect eval — `fast_solver.js` relies on this for
  console-identical behaviour; the embedded path wraps it in `async () => {}`
  instead (verified by `test_console_paste_mode_autoruns_to_completion`).
- `text.includes('correct')` matches "Incorrect" — substring traps are a
  challenge-site distractor pattern; match with `/(?:^|[^a-z])correct/i`.
- `innerText` ignores `display:none` but NOT z-index occlusion: codes "behind"
  overlays are already readable; modals matter because they block the submit
  flow, not the text.
- Local fixture testing works great: `page.route` on a fake
  `https://challenge.test` origin + pushState fixtures = full solver coverage
  with zero network.
