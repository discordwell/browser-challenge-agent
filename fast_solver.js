/**
 * FAST BROWSER CHALLENGE SOLVER — shared solver core.
 *
 * Handles all known challenge patterns:
 * 1. Scroll-reveal (500px+)
 * 2. Click-to-reveal ("Reveal Code" button)
 * 3. Timer-delayed (poll until the code appears)
 * 4. Hidden DOM attribute (data-challenge-code)
 * 5. Radio selection modals (pick the "Correct" option, not "Incorrect")
 * 6. Popup modals (Dismiss/Decline/Close/icon-only ×)
 * 7. Codes shown inline ("Code: ABC123" / "code is ABC123") or as a
 *    standalone 6-character line (digit-bearing lines win over all-letter
 *    distractors; a labelled code wins over a loose standalone token)
 * 8. Submit gated behind an "I agree" / "I'm human" checkbox (checked only
 *    while the submit button is actually disabled)
 *
 * Two ways to run it:
 *   - Console: start the challenge, then paste this whole file into the
 *     browser console. It auto-runs solveAllSteps() and logs RESULTS.
 *   - Embedded: agent.py declares `var __SOLVER_EMBEDDED__ = true` and
 *     includes this source inside the same function scope, then drives
 *     solveStepLoop() one step at a time so it can track metrics. The gate
 *     is a scoped variable (checked via typeof), never a page global, so
 *     embedding leaves no trace and a later console paste still auto-runs.
 *
 * Only `function` declarations at the top level (no const/let) so the file
 * can be pasted into the same console twice without redeclaration errors.
 */

function getCurrentStep() {
    var m = location.pathname.match(/step(\d+)/);
    return m ? parseInt(m[1], 10) : 0;
}

function solverWait(ms) {
    return new Promise(function (r) { setTimeout(r, ms); });
}

function looksFinished() {
    // Deliberately specific: lobby copy like "Complete 30 challenges in under
    // 5 minutes" must NOT match, so plain /complete/ is out.
    return /congrat|well done|you did it|challenge complete|all (\d+ )?(challenges?|steps?) (complete|done|solved)/i
        .test(document.body.innerText || '');
}

/**
 * The page's main submit control: a real submit button, else the first button
 * whose text starts with "submit" ("Submit Code" included — that IS the code
 * button). The modal-confirm pass has its own scan that deliberately avoids
 * "Submit Code", so it never collides with this.
 */
function findSubmitButton() {
    return document.querySelector('button[type="submit"]') ||
        Array.prototype.find.call(
            document.querySelectorAll('button'),
            function (b) { return /^submit/i.test((b.textContent || '').trim()); }
        ) || null;
}

/**
 * One DOM pass: dismiss modals, trigger reveals, satisfy submit gates, pick
 * radios, hunt for the code, then type + submit it. `state` persists across
 * passes within a step so the same code isn't re-submitted every few ms.
 */
async function solveOnePass(state) {
    state.actions = state.actions || [];
    var act = function (a) { if (state.actions.length < 200) state.actions.push(a); };

    // Scroll-reveal challenges unlock past ~500px.
    window.scrollTo(0, 600);

    // Close modals/popups. Exact text matches only, so "Close Account"-style
    // distractors don't trigger; empty text catches icon-only × buttons.
    document.querySelectorAll('button').forEach(function (btn) {
        var t = (btn.textContent || '').toLowerCase().trim();
        if (t === 'dismiss' || t === 'decline' || t === 'close' || t === '' || t === '×') {
            try { btn.click(); act('close:' + (t || 'icon')); } catch (e) {}
        }
    });

    // Click-to-reveal challenges.
    var revealBtn = Array.prototype.find.call(
        document.querySelectorAll('button'),
        function (b) { return (b.textContent || '').toLowerCase().indexOf('reveal') !== -1; }
    );
    if (revealBtn) {
        try { revealBtn.click(); act('reveal'); } catch (e) {}
    }

    // Submit gates: some steps keep the submit button disabled behind an
    // "I agree" / "I'm human" checkbox. Only act while the button is actually
    // disabled, so ordinary pages are untouched and stray checkboxes (e.g. a
    // newsletter opt-in) are never toggled when they aren't blocking us.
    var gateBtn = findSubmitButton();
    if (gateBtn && gateBtn.disabled) {
        document.querySelectorAll('input[type="checkbox"]').forEach(function (cb) {
            if (!cb.checked) {
                try { cb.click(); act('check:gate'); } catch (e) {}
            }
        });
    }

    // Radio modals: pick the option labelled "correct" — "incorrect" has a
    // letter before the match, so it is rejected.
    var isCorrectLabel = function (text) { return /(?:^|[^a-z])correct/i.test(text || ''); };
    var radioClicked = false;
    document.querySelectorAll('[role="radio"], input[type="radio"]').forEach(function (r) {
        if (radioClicked) return;
        var text = r.textContent ||
            (r.labels && r.labels[0] && r.labels[0].textContent) ||
            r.getAttribute('aria-label') || '';
        if (isCorrectLabel(text)) {
            try { r.click(); radioClicked = true; act('radio:' + text.trim().slice(0, 30)); } catch (e) {}
        }
    });
    if (radioClicked) {
        await solverWait(20);
        document.querySelectorAll('button').forEach(function (btn) {
            var t = (btn.textContent || '').trim();
            // The modal's confirm button — never the main "Submit Code" button.
            if (t === 'Submit' || t.indexOf('Submit &') === 0) {
                try { btn.click(); act('modal-submit'); } catch (e) {}
            }
        });
        await solverWait(20);
    }

    // Hunt for the 6-character code. Gather a candidate from each source, then
    // pick the most trustworthy. Every real code mixes letters and digits, so
    // a digit-bearing value is preferred — that stops both a 6-letter word
    // after "code" ("the code is HIDDEN") and a standalone distractor word
    // ("PUZZLE") from winning over the real code.
    var code = null, source = null;
    var text = document.body.innerText || '';
    var hasDigit = function (s) { return /[0-9]/.test(s); };

    // (a) Explicit hidden attribute — unambiguous.
    var codeEl = document.querySelector('[data-challenge-code]');
    var attrCode = codeEl && codeEl.getAttribute('data-challenge-code');

    // (b) Labelled inline code ("Code: ABC123" / "CODE: ABC123" / "code is
    //     ABC123"). The value must sit on the SAME line as the keyword ([^\S\n]
    //     is whitespace but not newlines) so the "Code" in a "Submit Code"
    //     button can't reach a token below it. \b keeps "barcode"/"decode" out.
    var labelledMatch = text.match(/\b(?:CODE|[Cc]ode)[^\S\n]*(?:is|:)?[^\S\n]*([A-Z0-9]{6})(?![A-Z0-9])/);
    var labelledCode = labelledMatch && labelledMatch[1];

    // (c) A standalone 6-char line, digit-bearing preferred.
    var standaloneCode = null, firstStandalone = null;
    var lines = text.split('\n');
    for (var i = 0; i < lines.length; i++) {
        var line = lines[i].trim();
        if (!/^[A-Z0-9]{6}$/.test(line)) continue;
        if (firstStandalone === null) firstStandalone = line;
        if (hasDigit(line)) { standaloneCode = line; break; }
    }

    // Preference: explicit attribute, then a digit-bearing labelled code (the
    // most pointed-to), then a digit-bearing standalone line, then any
    // standalone line, and only as a last resort an all-letter labelled value.
    if (attrCode) { code = attrCode; source = 'data-attr'; }
    else if (labelledCode && hasDigit(labelledCode)) { code = labelledCode; source = 'labelled'; }
    else if (standaloneCode) { code = standaloneCode; source = 'standalone-line'; }
    else if (firstStandalone) { code = firstStandalone; source = 'standalone-line'; }
    else if (labelledCode) { code = labelledCode; source = 'labelled'; }
    if (code) act('code-source:' + source);

    // Type + submit. Don't hammer: if this code were right the step would
    // have advanced already, so only re-submit the same code occasionally in
    // case an event was dropped mid-render. (Time-based, so the interval
    // doesn't drift with the caller's poll rate.)
    if (code) {
        state.code = code;
        var recentlySubmitted = state.lastSubmitted === code &&
            (Date.now() - state.lastSubmitTime) < 800;
        if (!recentlySubmitted) {
            var input = document.querySelector('input[placeholder*="code" i]') ||
                document.querySelector('input[type="text"]');
            var submit = findSubmitButton();
            if (input && submit) {
                // Native setter so React's value tracking sees the change.
                var setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
                setter.call(input, code);
                input.dispatchEvent(new Event('input', { bubbles: true }));
                input.dispatchEvent(new Event('change', { bubbles: true }));
                try { submit.click(); act('submit:' + code); } catch (e) {}
                state.lastSubmitted = code;
                state.lastSubmitTime = Date.now();
            }
        }
    }
    return state;
}

/**
 * Solve the current step: poll solveOnePass until the URL's step number
 * advances, the completion page appears, or `maxMs` elapses.
 *
 * Returns {advanced, finished, step, newStep, code, attempts, ms, actions}
 * plus `timeout: true` or `reset: true` when those apply.
 */
async function solveStepLoop(opts) {
    opts = opts || {};
    var pollMs = opts.pollMs || 40;
    var maxMs = opts.maxMs || 15000;
    var maxSteps = opts.maxSteps || 30;
    var start = Date.now();
    var startStep = getCurrentStep();
    var state = { pass: 0, code: null, lastSubmitted: null, lastSubmitTime: 0 };

    var result = function (extra) {
        return Object.assign({
            advanced: false,
            finished: false,
            step: startStep,
            newStep: getCurrentStep(),
            code: state.code,
            attempts: state.pass,
            ms: Date.now() - start,
            actions: Array.from(new Set(state.actions || []))
        }, extra);
    };

    if (startStep === 0) {
        return result({ actions: ['no-step-in-url'] });
    }

    while (true) {
        state.pass++;
        await solveOnePass(state);
        await solverWait(pollMs);

        var now = getCurrentStep();
        if (now > startStep) {
            return result({ advanced: true, finished: now > maxSteps });
        }
        if (now === 0) {
            // The step token vanished from the URL: either we reached the
            // completion page or the site reset us. Page text tells us which.
            var fin = startStep >= maxSteps || looksFinished();
            return result({ advanced: fin, finished: fin, reset: !fin });
        }
        if (now < startStep) {
            return result({ reset: true });
        }
        if (Date.now() - start > maxMs) {
            return result({ timeout: true });
        }
    }
}

/** Console entry point: solve every step from wherever we currently are. */
async function solveAllSteps(opts) {
    opts = opts || {};
    var startTime = Date.now();
    var results = [];

    while (true) {
        var step = getCurrentStep();
        if (step === 0 || step > (opts.maxSteps || 30)) break;
        var r = await solveStepLoop(opts);
        results.push(r);
        if (!r.advanced || r.finished) break;
    }

    return {
        totalTime: Date.now() - startTime,
        stepsCompleted: results.filter(function (r) { return r.advanced; }).length,
        finished: results.length > 0 && results[results.length - 1].finished,
        results: results
    };
}

// Auto-run only when pasted into a console. agent.py declares
// `var __SOLVER_EMBEDDED__ = true` in the scope it embeds this source into;
// the typeof check makes the bare identifier safe when it was never declared.
if (typeof __SOLVER_EMBEDDED__ === 'undefined' || !__SOLVER_EMBEDDED__) {
    solveAllSteps().then(function (r) {
        console.log('RESULTS:', JSON.stringify(r, null, 2));
    });
}
