# Claudepad

## Session Summaries

### 2026-06-18T22:35Z — Decoy-safe code-field detection (input-side hardening)
- Capability/safety gap: the submit side is heavily decoy-hardened (form-scoped,
  real-control preference, decoy-form avoidance) but the INPUT side was naive —
  `input[placeholder*="code" i]` then the FIRST `input[type="text"]` in DOM
  order, with zero decoy awareness. A decoy text input listed first (a newsletter
  "email" box) whose real code field isn't placeholder-labelled → the code is
  typed into the decoy and the step stalls. Audited all 24 fixtures: every code
  field uses `placeholder="Enter code"` (or is the only input), so this case was
  entirely unguarded AND untested. Confirmed RED with `decoy_text_input.html`.
- Fix: extracted `findCodeInput()` (top-level, re-paste-safe `function`). Prefers
  a text-like input whose placeholder/name/id/aria-label/`<label>` contains
  "code" (`\bcode\b`, so "postcode"/"barcode" excluded — same boundary rule as
  the labelled-code scan; non-text inputs skipped so a "code of conduct" checkbox
  isn't chosen) wherever it sits in the DOM. Falls back to the BYTE-IDENTICAL old
  chain (`text → search → bare input`) when nothing is code-associated, so every
  existing fixture resolves to the same element → zero regression.
- Adversarial review (1 finder) flagged one real MINOR: broadening past the
  placeholder is itself a distractor surface — a "Promo code"/"Area code"/"QR
  code" decoy TEXT input would now be preferred. Since distractor-safety is the
  whole point, hardened with a tight `decoyCode` denylist
  (`promo|discount|coupon|voucher|gift|referral|area|zip|postal|country|bar|qr`
  `[-\s]+code`); rejected mentions fall through to the DOM-order fallback (the
  old behaviour), so it only NARROWS the broadened set — can't regress. This also
  fixes a latent flaw the OLD placeholder-substring match had ("Promo code"
  placeholder matched before).
- 2 fixtures + tests, each teeth-verified: `decoy_text_input` (RED vs committed
  solver), `decoy_qualified_code_input` (RED vs the naive no-denylist version —
  confirmed by temporarily dropping the denylist). `\bcode\b`/`decoyCode`
  classification also validated by a standalone Node battery (15 challenge-code
  phrasings accept / 26 decoys+boundary-traps reject). Suite: 56 passing (was 54:
  +2). `node --check` clean. Docs synced (README design-choice + distractor
  bullet, ARCHITECTURE submit/input-targeting bullet + component diagram,
  fast_solver.js header).

### 2026-06-18T11:53Z — aria-disabled submit gates (weak-signal, consent-filtered)
- Capability gap: the agree-gate handler only treated a submit button as gated
  when its NATIVE `.disabled` was set. React/accessible UIs commonly express a
  gated control with `aria-disabled="true"` instead (stays focusable, click is
  a no-op until satisfied). Such a gate was never satisfied — the code was typed
  but submit kept no-opping and the step stalled. Confirmed RED with a new
  `aria_disabled_gate.html` fixture against the committed solver.
- First cut (just OR-ing `aria-disabled` into the existing condition) was caught
  by adversarial review as a distractor-safety REGRESSION: the gate-like-label
  logic is a SORT key, not a filter, so once the gate fired it ticked the
  first-sorted unchecked box even on a non-gate page. Native `.disabled` is a
  strong "real gate" signal so that's fine; `aria-disabled` is weak (advisory,
  can be left stale), so a stale `aria-disabled` + an unchecked "Remember me"
  box → wrongly ticked.
- Fix: split signal strength. Native-disabled keeps the old behaviour (any
  unchecked box, ranked by loose `gateLike`, DOM-order tiebreak). aria-only is
  weak → tick a box ONLY when its label passes a new, tight `looksLikeGateConsent`
  filter (affirmative consent: "I agree", "I accept the terms", "I consent",
  "I'm (not a) human/robot/bot"). A second review caught that reusing the LOOSE
  `gateLike` as the filter still over-matches benign copy ("new conditions",
  "continue receiving"), hence the dedicated tight regex.
- 3 fixtures + tests, each teeth-verified by temporarily reverting:
  `aria_disabled_gate` (RED vs committed solver), `aria_disabled_decoy`
  ("Remember me" — RED vs the naive no-filter widening), and
  `aria_disabled_decoy_keyword` ("…new conditions…" — RED vs the loose-filter
  version). `looksLikeGateConsent` also validated by a standalone Node battery
  (11 gate phrasings match / 9 benign+distractor reject, incl. "Accept all
  cookies"). Native-disabled fixtures (`agree_gate`, `agree_gate_distractor`,
  `decoy_disabled_submit`) unchanged. Suite: 54 passing (was 51: +3). `node
  --check` clean. Docs synced (README, ARCHITECTURE strong/weak-signal split,
  fast_solver.js header, agent.py docstring).

### 2026-06-18T05:53Z — Submit/input targeting robustness (decoy-safe)
- Three real interaction-layer gaps where the agent would silently get stuck on
  a plausible real-site DOM shape (code never typed/submitted, retries exhaust):
  1. Code field only found via `input[placeholder*="code"]` or `input[type="text"]`
     — a `type="search"` or bare `<input>` (no type) was missed.
  2. `findSubmitButton` scanned `<button>` only — an `<input type="submit">` was
     never found, so the code was never submitted.
  3. Submit was a document-wide "first `button[type="submit"]`" search, so a
     decoy form's submit (newsletter "Subscribe" listed before the real form)
     got clicked instead — against the project's distractor theme.
- Fixes in `fast_solver.js`: input selector falls back through
  `text → search → bare input:not([type])`; `findSubmitButton(scope)` takes an
  optional scope and also matches `input[type="submit"]`; the code-submit path
  scopes to the code field's own `<form>` first (so a real submit wins whatever
  its label — "Verify Code"/"Continue" — and a decoy form's submit is never
  clicked), falling back to the document-wide search only for form-less inputs.
- 3 fixtures + tests (`search_input`, `input_submit`, `multi_form_submit`),
  each confirmed RED against the pre-change solver, GREEN after.
- Code review (1 adversarial finder, empirically verified both ways) found 2 REAL
  regressions from a grouped `querySelector('button[type="submit"], input[type=
  "submit"]')`: it returns the first match in DOM ORDER, so a decoy
  `<input type="submit">` before the real button shadowed it. Hit the two
  *unscoped* call sites — the global fallback (form-less code input → wrong click)
  and the agree-gate's `.disabled` check (a disabled decoy input tripped the gate
  and ticked a decoy box). Fixed by querying `button[type="submit"]` FIRST, then
  `input[type="submit"]` (separate queries, buttons preferred). Locked in with 2
  more RED→GREEN regression fixtures (`decoy_input_submit`, `decoy_disabled_submit`).
- Suite: 51 passing (was 46: +5). `node --check` clean. Docs synced (README
  design-choices bullet, ARCHITECTURE "Submit/input targeting" incl. the
  grouped-selector DOM-order pitfall).

### 2026-06-17T19:15Z — Reveal-verb variants + looksFinished invariant tests
- Capability gap: click-to-reveal only matched the literal substring `reveal`,
  so a "Show Code" / "Unlock Code" / "Display the code" button (same UI pattern,
  different wording) was never clicked and the step couldn't be solved.
  Confirmed RED with a new `show_code_button.html` fixture against the old
  solver (never advances).
- Fixed with a top-level `isRevealButton(text)` helper (re-paste-safe
  `function`): any text containing "reveal" qualifies; other reveal verbs
  (`show|unlock|display|view|see|get|generate`, word-boundary) qualify only when
  the text ALSO mentions "code". So "Submit Code", "Show menu", "Get started",
  modal buttons, and START are all left alone — same distractor-safety stance as
  the modal-close matcher. Strictly a superset of the old matches among the
  fixtures (verified: no existing button is newly matched), so no regression;
  `reveal_button` ("Reveal Code") still passes.
- Added direct invariant tests for `looksFinished()` (previously only covered
  indirectly): 6 completion-copy strings that must match + 4 lobby/progress
  strings that must NOT — pins the documented "lobby copy like 'Complete 30
  challenges…' must never read as completion" guarantee. Drive it via
  `build_finished_probe()` (sets `__SOLVER_EMBEDDED__`, no auto-run) over
  `document.body.innerText`.
- Suite: 46 passing (was 35: +1 reveal, +10 looksFinished params). `node --check`
  clean. Docs synced (README, ARCHITECTURE, agent.py docstring — the latter had
  omitted click-to-reveal entirely).
- Code review (2 parallel finders: reveal-matcher correctness + test-vacuity):
  no findings. Confirmed "Submit Code" can't be mistaken for a reveal (word
  boundary stops "submit"), compound words (showcase/overview/forget) don't
  trip the verbs, and the looksFinished tests aren't vacuous (innerText setter
  round-trips in headless Chromium).

### 2026-06-17T12:00Z — Select-dropdown quizzes + decoy-safe checkbox gates
- New pattern: `<select>` dropdown quizzes. `solveOnePass` now picks the option
  whose text reads "correct" (reusing the radio's `isCorrectLabel`, so
  "Incorrect" is still rejected) and drives it via the native
  `HTMLSelectElement` value setter + `change` event (React-aware, same as the
  code input). Radio + select share one `quizAnswered` flag and the existing
  modal-confirm pass (`Submit`/`Submit & …`, never `Submit Code`).
- Hardened the submit-gate handler against decoy checkboxes (the project's
  distractor theme). Was: check ALL unticked boxes whenever submit is disabled —
  which also ticks a "sign me up" decoy. Now: tick ONE box per pass, the most
  gate-like one (label matches `agree|consent|terms|condition|human|robot|
  confirm|continue|proceed`), then let the next ~40ms poll see if submit
  unlocked. Strictly ⊆ the old set of boxes touched, and on React it avoids the
  decoy entirely (the gate box's re-render lands before the next box is tried).
- 2 fixtures + tests (`select_quiz`, `agree_gate_distractor`); confirmed both
  FAIL against the pre-change solver (select → never advances; distractor box →
  gets ticked) and pass after. Suite: 35 passing (was 33). `node --check` clean.
- Code review (2 parallel finders, correctness + cleanup): no correctness bugs.
  Acted on the one shared finding — the native value-setter dance was duplicated
  across the code input and the new select. Extracted `setNativeValue(el, value)`
  (reads the setter off `Object.getPrototypeOf(el)`, so it's right for both
  element types) as a top-level `function` (re-paste-safe). The input path is
  covered by nearly every fixture, so the suite is a strong regression net.
- Considered a `pyproject.toml` to silence the `pytest-asyncio` "unset config
  option" deprecation, but that warning fires at plugin-import time (before
  `filterwarnings`/`-W` apply) and the plugin isn't even a declared dep
  (requirements-dev pins only pytest). Dropped it rather than ship a config that
  can't do what its comment claims.

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
- A grouped `querySelector('a, b')` returns the first element matching EITHER
  selector in DOM ORDER — NOT "all of selector a, then selector b". So adding a
  second alternative can let a decoy that appears earlier shadow the preferred
  match. When priority matters (prefer `<button type=submit>` over
  `<input type=submit>`), query them as SEPARATE `querySelector` calls in
  preference order. This is the distractor-safe shape `findSubmitButton` uses.
- The code field is often NOT inside a `<form>` on this site (React divs), so
  `input.form` can be null — the submit search must fall back to document-wide
  when it is, but prefer the input's own form when present (decoy-form safety).
- Distractor-safety must cover the INPUT side too, not just buttons/forms.
  Picking "the first `input[type=text]`" is DOM-order-fragile the same way the
  grouped submit selector was: a decoy text input (newsletter "email" box) listed
  first captures the code. `findCodeInput` picks by meaning — placeholder / name /
  id / aria-label / `<label>` containing `\bcode\b` — and only falls back to
  DOM order when nothing is code-associated. Broadening the signal past the
  placeholder reintroduces distractors at one remove ("Promo code" / "Area code"
  boxes), so a small qualifier denylist guards it; the same `\bcode\b` boundary
  that excludes "barcode"/"postcode" is reused for consistency.
