/**
 * FAST BROWSER CHALLENGE SOLVER — shared solver core.
 *
 * Handles all known challenge patterns:
 * 1. Scroll-reveal (500px+)
 * 2. Click-to-reveal ("Reveal Code" / "Show Code" / "Unlock Code" button)
 * 3. Timer-delayed (poll until the code appears)
 * 4. Hidden DOM attribute (data-challenge-code)
 * 5. Quiz modals — radio buttons or a <select> dropdown (pick the "Correct"
 *    option, not "Incorrect")
 * 6. Popup modals (Dismiss/Decline/Close/icon-only ×)
 * 7. Codes shown inline ("Code: ABC123" / "code is ABC123") or as a
 *    standalone 6-character line (digit-bearing lines win over all-letter
 *    distractors; a labelled code wins over a loose standalone token)
 * 8. Submit gated behind an "I agree" / "I'm human" checkbox (only while the
 *    submit button is disabled — native `disabled` or `aria-disabled="true"` —
 *    one gate-like box per pass, so decoy boxes such as a newsletter opt-in are
 *    left alone once submit unlocks)
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
 * The page's main submit control: a real submit control (button OR
 * <input type="submit">, whatever its label), else the first button whose text
 * starts with "submit" ("Submit Code" included — that IS the code button). Pass
 * a `scope` (e.g. the code field's <form>) to search within it first, so the
 * right submit wins even when its label isn't "Submit" and a decoy form's
 * submit sits elsewhere on the page. The modal-confirm pass has its own scan
 * that deliberately avoids "Submit Code", so it never collides with this.
 *
 * A real <button type="submit"> is preferred over an <input type="submit">
 * (queried separately, buttons first) rather than via one grouped selector —
 * grouped querySelector returns the first match in DOM order, so a decoy
 * <input type="submit"> placed before the real button would otherwise shadow it.
 */
function findSubmitButton(scope) {
    scope = scope || document;
    return scope.querySelector('button[type="submit"]') ||
        scope.querySelector('input[type="submit"]') ||
        Array.prototype.find.call(
            scope.querySelectorAll('button'),
            function (b) { return /^submit/i.test((b.textContent || '').trim()); }
        ) || null;
}

/**
 * Does this button text read like a "reveal the code" control? Any text
 * containing "reveal" qualifies (e.g. "Reveal", "Reveal Code"). Other
 * phrasings ("Show Code", "Unlock Code", "Display the code") qualify only when
 * they also mention the code, so generic buttons ("Show menu", "Get started")
 * and the "Submit Code" control are left alone — same distractor-safety stance
 * as the modal-close matcher.
 */
function isRevealButton(text) {
    var t = (text || '').toLowerCase();
    if (t.indexOf('reveal') !== -1) return true;
    if (t.indexOf('code') === -1) return false;
    return /\b(show|unlock|display|view|see|get|generate)\b/.test(t);
}

/**
 * Set an <input> or <select> value the way React expects: through the element's
 * native value setter (read off its own prototype, so it's correct for both
 * element types), then fire input + change so a controlled component re-renders.
 * Plain `el.value = x` leaves React's value tracker stale and the change is lost.
 */
function setNativeValue(el, value) {
    var setter = Object.getOwnPropertyDescriptor(Object.getPrototypeOf(el), 'value').set;
    setter.call(el, value);
    el.dispatchEvent(new Event('input', { bubbles: true }));
    el.dispatchEvent(new Event('change', { bubbles: true }));
}

/**
 * Does this checkbox label read like an affirmative "I agree / I'm human"
 * consent gate, as opposed to a marketing opt-in? Deliberately tighter than the
 * loose `gateLike` ranking heuristic used for natively-disabled gates: this is
 * a FILTER for the weak `aria-disabled` signal, where ticking the wrong box is
 * a distractor mis-click. So it requires an affirmative gate phrase ("I agree",
 * "I accept the terms", "I consent", "I'm (not a) human/robot/bot") and will
 * NOT match benign copy that merely contains a keyword ("new conditions",
 * "continue receiving updates", "remember me", "I confirm my email").
 */
function looksLikeGateConsent(text) {
    var t = (text || '').toLowerCase().replace(/[’']/g, "'");
    return /\bi (?:agree|consent|accept)\b/.test(t) ||
        /\b(?:agree|consent) to\b/.test(t) ||
        /\baccept (?:the )?terms\b/.test(t) ||
        /\bi(?:'m| am) (?:not a )?(?:human|robot|bot)\b/.test(t) ||
        /\bnot a (?:robot|bot)\b/.test(t);
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

    // Click-to-reveal challenges ("Reveal Code", "Show Code", "Unlock Code", …).
    var revealBtn = Array.prototype.find.call(
        document.querySelectorAll('button'),
        function (b) { return isRevealButton(b.textContent); }
    );
    if (revealBtn) {
        try { revealBtn.click(); act('reveal'); } catch (e) {}
    }

    // Submit gates: some steps keep the submit button disabled behind an
    // "I agree" / "I'm human" checkbox. Only act while the button is gated, so
    // ordinary pages and unrelated checkboxes (e.g. a newsletter opt-in) are
    // left alone. Check ONE box per pass — then let the next poll see whether
    // submit unlocked — so a decoy box isn't toggled once the real box has
    // already enabled the button, and a React re-render has a tick to land.
    //
    // Two strengths of "gated":
    //   - native `disabled` is a strong signal — a disabled submit almost
    //     always IS a real gate — so tick the best-guess box: gate-like label
    //     preferred, DOM order as the tiebreak when none look gate-like.
    //   - aria-disabled="true" is only an ARIA hint (it doesn't block clicks or
    //     submission and can be left stale on a non-gate control), so treat it
    //     as a weak signal: act ONLY on a box whose label is an affirmative
    //     consent phrase (looksLikeGateConsent), never on a bare DOM-order
    //     fallback and never on the loose ranking keyword. That keeps a decoy
    //     "Remember me" box — or benign copy that merely contains a keyword
    //     ("new conditions", "continue receiving") — from being ticked when a
    //     non-gated submit just carries aria-disabled. Genuine accessible gates
    //     still say "I agree" / "I'm human", so they match.
    var gateBtn = findSubmitButton();
    var nativelyDisabled = !!(gateBtn && gateBtn.disabled);
    var ariaDisabled = !!(gateBtn && gateBtn.getAttribute('aria-disabled') === 'true');
    if (nativelyDisabled || ariaDisabled) {
        var gateLike = /agree|consent|terms|condition|human|robot|confirm|continue|proceed/;
        var checkboxText = function (cb) {
            var label = cb.closest && cb.closest('label');
            return ((label && label.textContent) ||
                (cb.labels && cb.labels[0] && cb.labels[0].textContent) ||
                cb.getAttribute('aria-label') || '').toLowerCase();
        };
        var unchecked = Array.prototype.filter.call(
            document.querySelectorAll('input[type="checkbox"]'),
            function (cb) { return !cb.checked; }
        );
        // Strong (native-disabled) signal: any unchecked box is a candidate.
        // Weak (aria-only) signal: only an affirmative consent label qualifies.
        var candidates = nativelyDisabled ? unchecked :
            unchecked.filter(function (cb) { return looksLikeGateConsent(checkboxText(cb)); });
        // Gate-like labels first; the sort is stable, so DOM order breaks ties.
        candidates.sort(function (a, b) {
            return (gateLike.test(checkboxText(b)) ? 1 : 0) -
                (gateLike.test(checkboxText(a)) ? 1 : 0);
        });
        if (candidates.length) {
            try { candidates[0].click(); act('check:gate'); } catch (e) {}
        }
    }

    // Quiz modals: choose the option labelled "correct" — "incorrect" has a
    // letter before the match, so it is rejected. Both radio buttons and a
    // <select> dropdown are handled; whichever fires triggers the confirm pass.
    var isCorrectLabel = function (text) { return /(?:^|[^a-z])correct/i.test(text || ''); };
    var quizAnswered = false;
    document.querySelectorAll('[role="radio"], input[type="radio"]').forEach(function (r) {
        if (quizAnswered) return;
        var text = r.textContent ||
            (r.labels && r.labels[0] && r.labels[0].textContent) ||
            r.getAttribute('aria-label') || '';
        if (isCorrectLabel(text)) {
            try { r.click(); quizAnswered = true; act('radio:' + text.trim().slice(0, 30)); } catch (e) {}
        }
    });
    // Dropdown quizzes: select the "correct" option. Use the native value
    // setter + change event so React-controlled selects register it, the same
    // way the code input is driven below.
    document.querySelectorAll('select').forEach(function (sel) {
        if (quizAnswered) return;
        var match = Array.prototype.find.call(sel.options || [], function (o) {
            return isCorrectLabel(o.textContent);
        });
        if (!match) return;
        if (sel.value !== match.value) {
            try {
                setNativeValue(sel, match.value);
                act('select:' + (match.textContent || '').trim().slice(0, 30));
            } catch (e) {}
        }
        quizAnswered = true;  // confirm even if the right option was already set
    });
    if (quizAnswered) {
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
            // The code field: prefer one whose placeholder mentions "code", else
            // the first text-like input — text, search, or a bare <input> with no
            // type (which defaults to text). The extra types matter because a real
            // form may never spell out type="text".
            var input = document.querySelector('input[placeholder*="code" i]') ||
                document.querySelector('input[type="text"]') ||
                document.querySelector('input[type="search"]') ||
                document.querySelector('input:not([type])');
            // Submit through the code field's OWN form when it has one, so the
            // real submit control wins regardless of its label ("Verify Code",
            // "Continue", …) and a decoy form's submit (e.g. a newsletter
            // "Subscribe" listed first) is never clicked. Fall back to a
            // document-wide search for an input that sits outside any form.
            var submit = (input && input.form && findSubmitButton(input.form)) ||
                findSubmitButton();
            if (input && submit) {
                setNativeValue(input, code);  // React-aware; see helper above
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
