# Claudepad

## Session Summaries

### 2026-06-17T08:10Z — Code-detection hardening + submit-gate handling
- Hardened `fast_solver.js` code detection against distractors (the project's
  stated theme). Now gathers a candidate from each source (data-attr, labelled
  "Code:", standalone line) and picks by confidence: explicit attr →
  digit-bearing labelled → digit-bearing standalone → any standalone →
  all-letter labelled (last resort). Every real code mixes letters and digits,
  so that preference stops both a standalone distractor word ("PUZZLE") and a
  6-letter word after "code" ("the code is HIDDEN") from being submitted, while
  still finding an all-letter code if that's all there is.
- Tightened the labelled regex to same-line only (`[^\S\n]` instead of `\s`) so
  "Code" in a "Submit Code" button can't reach a token on the next line.
- New pattern: submit gated behind an "I agree"/"I'm human" checkbox. The
  solver checks unticked boxes only while the submit button is actually
  `disabled`, so normal pages / unrelated checkboxes are untouched.
- Extracted `findSubmitButton()` (used by the new gate check and the existing
  code-submit path; modal-confirm keeps its own "never Submit Code" scan).
- IMPORTANT review catch: an interim version reordered labelled before
  standalone but let an all-letter labelled value win, so "the code is HIDDEN"
  submitted "HIDDEN" and beat the digit-bearing code. Fixed by the digit
  preference above; added `labelled_prose_distractor` regression test.
- 4 new fixtures + tests (distractor words, labelled-beats-standalone,
  labelled-prose, agree-gate); verified each FAILS against the buggy/pre-change
  solver. Suite: 33 passing (was 29). `node --check` clean.

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
- `^[A-Z0-9]{6}$` matches any 6-letter uppercase word (PUZZLE/REVEAL/SUBMIT),
  which is exactly the distractor shape this challenge uses. All real codes
  seen so far mix letters and digits, so the standalone scan prefers a
  digit-bearing line; explicit sources (data-attr, labelled "Code:") are tried
  first so a loose token can't beat a pointed-to code.
- `innerText` is newline-joined across elements, so a label regex with `\s*`
  will span element boundaries — "Submit Code\n<token>" looked like a labelled
  code. Constrain label→value matches to the same line (`[^\S\n]`).
