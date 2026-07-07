---
name: estimation-and-scoping
description: Honest sizing and scope — probe before promising, surface 10x discoveries immediately (never silently absorb or shrink), vertical slices, calibrate finish quality to the ask. Use when sizing work, when scope balloons mid-task, or when a "quick fix" reveals architectural change.
---

# Estimation and Scoping

Scope failures are trust failures: promising small and delivering huge, silently shrinking the task to fit, or gold-plating past what was asked. The countermeasures are probing early and renegotiating loudly.

## Size by probing, not by vibes

Before sizing anything non-trivial, spend a few minutes measuring the actual surface:
- Count the touch points: grep the symbols/patterns involved — 3 call sites and 40 call sites are different projects.
- Find the precedent: how big was the last similar change here (`git log`, its diff stat)?
- Probe the riskiest assumption first — the API you hope exists, the layer you hope is decoupled. Ten minutes of probing regularly converts "small tweak" into "restructuring" BEFORE you've promised anything.

Report size as: what's certain + what's contingent ("mechanical across 12 files; contingent on whether X handles Y — checking that first").

## The 10x-discovery rule

The moment evidence shows the task is a multiple of what was understood — hidden coupling, a needed migration, a load-bearing hack where you expected clean seams — STOP and surface it. State: what you found, the honest new shape, 2–3 options with costs (full fix / narrow workaround / defer), and your recommendation. Then let the user choose.

What is NOT allowed: silently absorbing the blowup (user waits 5x longer than told), or silently shrinking the deliverable to fit the estimate (user gets less than agreed and finds out later). Both are worse than the awkward message.

## Slice for shippable increments

When work is big, cut it so each slice is independently verifiable and leaves the system working:
- Vertical slices (one thin end-to-end path) over horizontal layers (all models, then all handlers…) — vertical proves the architecture early, where the risk lives.
- Sequence: riskiest-assumption slice first, then value order.
- Each slice ends at a real checkpoint: gates green, behavior demonstrable. "80% done" on an unshippable heap is 0% shipped.

## Calibrate finish quality to the request

Match effort to intent — and when they diverge, say so rather than silently choosing:
- "Quick check / prototype / does this work?" → answer the question; don't refactor the neighborhood or build the test suite.
- "Fix the bug" → fix + regression test + gates. Not a rewrite of the module (note rewrite-worthy findings in the report instead).
- "Production-ready" → error paths, edge cases, tests, docs — the full bar.

Gold-plating (unrequested abstractions, config for imagined futures, extra features) is scope creep in a flattering costume. YAGNI applies to agents too: build what was asked; list what you'd consider next.

## The definition-of-done handshake

For any multi-step task, restate scope as a checklist before diving deep: in-scope items, explicitly-out items ("not touching the mobile layout"), and the verification bar. Ambiguity discovered at review time was scope debt incurred at kickoff. If the task came with no spec at all, your restated checklist IS the spec — put it where the user will see it.
