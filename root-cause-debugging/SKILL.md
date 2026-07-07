---
name: root-cause-debugging
description: Systematic debugging — reproduce, bisect, prove the cause with a falsifiable hypothesis, fix minimally, re-verify against the original repro. Use for any bug, test failure, regression, or flaky behavior, before proposing a fix — and whenever a first fix didn't work.
---

# Root-Cause Debugging

Weak debugging looks like: read the error → pattern-match to a familiar cause → apply a plausible fix → declare victory. Strong debugging proves the cause before touching the fix. Follow this sequence and do not skip stages.

## Stage 1 — Reproduce before anything else

Get the failure happening on demand, in the smallest command you can run repeatedly (a single test, a curl, a node one-liner). If you cannot reproduce it, your job is to instrument until you can — not to fix blind.

Write down (mentally or in a scratch file) the exact reproduction command and the exact observed-vs-expected output. This is the acceptance test for your fix.

## Stage 2 — Locate by bisection, not intuition

Find where reality diverges from expectation by cutting the search space in half repeatedly:

- Trace the data: pick one concrete value that ends up wrong and follow it backward from the symptom to where it was last correct.
- Log/inspect at the midpoint of the suspected path; then midpoint again.
- Use git: `git log --oneline -- <file>`, `git bisect`, or diff against the last-known-good commit when it's a regression.
- Distrust the error site. The line that throws is where the bad state was *noticed*, rarely where it was *created*.

## Stage 3 — State the cause as a falsifiable sentence

Before fixing, complete this sentence with specifics: "The failure happens because **[specific code]** does **[specific wrong thing]** when **[specific condition]**."

Then try to falsify it: if this were true, what ELSE would be broken? Check that. If the hypothesis predicts things that aren't happening, it's wrong — go back to stage 2. A hypothesis you haven't tried to break is a guess.

## Stage 4 — Fix the cause, minimally

- Fix where the bad state is created, not where it's detected.
- Prefer the smallest diff that makes the falsifiable sentence false.
- If the real fix is large and you must ship a symptom-level guard, say so explicitly in your report — never present a mitigation as a root-cause fix.

## Stage 5 — Verify with the original reproduction

Run the exact stage-1 reproduction. Then run the surrounding test suite to check for collateral damage. A fix verified only by "the code looks right now" is not verified.

## When a fix attempt fails

Do not stack a second guess on the first. Revert your mental model to stage 3: the failed fix is *evidence* — it falsified your hypothesis. Ask what the failure of the fix tells you about where the real cause is.

## Flaky / intermittent failures

Don't average over the noise. Find the varying input: timing (race), ordering (test pollution, map iteration), environment (env var, port, clock), or data (random seed). Run the reproduction in a loop (`for i in $(seq 20); do ...; done`) to measure the failure rate before and after the fix — "passed once" is not evidence for a flake fix.
