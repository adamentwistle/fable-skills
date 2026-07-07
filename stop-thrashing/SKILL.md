---
name: stop-thrashing
description: Detect when you're iterating without converging — third failed attempt at the same problem — and force a zoom-out instead of a fourth variation. Use when consecutive fixes to the same failure haven't worked, when you're re-editing the same lines, or when each attempt is a guess rather than a deduction.
---

# stop-thrashing

Thrashing is trying variations faster instead of understanding harder. Each desperate iteration adds noise to the diff and anchors you deeper in a wrong frame.

1. **Count your attempts honestly.** Two failed fixes for the same failure is the alarm. The third attempt may proceed only if it's derived from *new evidence* — a log you hadn't read, a value you hadn't inspected — not from "maybe it's this instead" (see root-cause-debug: one hypothesis, one test).
2. **On the alarm, stop editing and zoom out.** Re-read the original error top to bottom, re-read the failing code fresh, re-state the problem in one sentence. Ask the frame-breaking questions: am I editing the file that's actually being run (see environment-first)? Is my mental model of what this code does verified or assumed (see ground-before-edit)? Is the bug even where I've been looking?
3. **Revert the debris before attempt N+1.** Failed fixes stack: by attempt four the code has three speculative changes interacting, and you're debugging your attempts instead of the bug. `git checkout` back to the last known state and apply only what evidence supports.
4. **Change the method, not just the guess:** add instrumentation and actually look at runtime values; bisect the input or the commit history; write the minimal reproduction from scratch; explain the problem line-by-line to an imagined reviewer (rubber-ducking works on models too).
5. **Budget the persistence.** Autonomous retrying is right for mechanical obstacles (flaky network, transient lock); it's wrong when each retry costs a rewrite. If genuine investigation has failed repeatedly and you're out of distinct evidence-backed approaches, report the state honestly — what you tried, what each attempt showed, current best hypothesis — rather than burning the session on variation five (see honest-report).
6. **Notice the sunk-cost pull.** "I've come this far with approach A" is not evidence for approach A. The willingness to discard an hour of work when the frame is wrong is exactly the behavior that separates converging from thrashing.

Test: can you state what *new* fact attempt N+1 is based on? No new fact, no new attempt — go get the fact first.
