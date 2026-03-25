/**
 * FAST BROWSER CHALLENGE SOLVER
 *
 * Handles all known challenge patterns:
 * 1. Scroll-reveal (500px+)
 * 2. Click-to-reveal ("Reveal Code" button)
 * 3. Timer-delayed (poll for code appearance)
 * 4. Hidden DOM attribute (data-challenge-code)
 * 5. Radio selection modals (find "Correct" option)
 * 6. Various popup modals (Dismiss/Decline/Close)
 *
 * Strategy: Do everything in parallel, poll rapidly until step changes
 */

async function solveAllSteps() {
    const wait = ms => new Promise(r => setTimeout(r, ms));
    const startTime = Date.now();
    const results = [];

    while (true) {
        const stepMatch = location.pathname.match(/step(\d+)/);
        const currentStep = stepMatch ? parseInt(stepMatch[1]) : 0;

        if (currentStep === 0 || currentStep > 30) break;

        const stepStart = Date.now();
        let solved = false;
        let attempts = 0;

        while (!solved && attempts < 100) {
            attempts++;

            // 1. SCROLL - always scroll to trigger scroll-reveal
            window.scrollTo(0, 600);

            // 2. CLOSE MODALS - aggressively close all popups
            document.querySelectorAll('button').forEach(btn => {
                const t = (btn.textContent || '').toLowerCase().trim();
                if (['dismiss', 'decline', 'close'].includes(t) || t === '' || t === '×') {
                    try { btn.click(); } catch(e) {}
                }
            });

            // 3. CLICK REVEAL - if there's a reveal button, click it
            const revealBtn = Array.from(document.querySelectorAll('button'))
                .find(b => b.textContent.toLowerCase().includes('reveal'));
            if (revealBtn) revealBtn.click();

            // 4. HANDLE RADIO SELECTION
            let radioClicked = false;
            document.querySelectorAll('[role="radio"], input[type="radio"]').forEach(r => {
                if (radioClicked) return;
                const text = (r.textContent || r.labels?.[0]?.textContent || '').toLowerCase();
                if (text.includes('correct')) {
                    r.click();
                    radioClicked = true;
                }
            });

            // Click modal submit if radio was clicked
            if (radioClicked) {
                await wait(20);
                document.querySelectorAll('button').forEach(btn => {
                    const t = btn.textContent.trim();
                    if (t === 'Submit' || t.includes('Submit &')) {
                        try { btn.click(); } catch(e) {}
                    }
                });
                await wait(20);
            }

            // 5. FIND CODE - check all sources
            let code = null;

            // Source A: data attribute
            const codeEl = document.querySelector('[data-challenge-code]');
            if (codeEl) code = codeEl.getAttribute('data-challenge-code');

            // Source B: standalone 6-char code in text
            if (!code) {
                const text = document.body.innerText;
                const lines = text.split('\n').map(l => l.trim());
                const codeLine = lines.find(l => /^[A-Z0-9]{6}$/.test(l));
                if (codeLine) code = codeLine;
            }

            // 6. SUBMIT CODE
            if (code) {
                const input = document.querySelector('input[placeholder*="code"]');
                const submit = document.querySelector('button[type="submit"]');
                if (input && submit) {
                    // Use native setter for React compatibility
                    const setter = Object.getOwnPropertyDescriptor(
                        HTMLInputElement.prototype, 'value'
                    ).set;
                    setter.call(input, code);
                    input.dispatchEvent(new Event('input', {bubbles: true}));
                    submit.click();
                }
            }

            // Check if step changed
            await wait(30);
            const newStep = location.pathname.match(/step(\d+)/)?.[1];
            if (newStep && parseInt(newStep) > currentStep) {
                solved = true;
                results.push({
                    step: currentStep,
                    code,
                    time: Date.now() - stepStart,
                    attempts
                });
            }
        }

        if (!solved) {
            results.push({step: currentStep, error: 'Max attempts', attempts});
            break;
        }
    }

    return {
        totalTime: Date.now() - startTime,
        stepsCompleted: results.length,
        results
    };
}

// Run the solver
solveAllSteps().then(r => console.log('RESULTS:', JSON.stringify(r, null, 2)));
