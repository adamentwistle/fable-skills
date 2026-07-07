---
name: numerical-care
description: Handle numbers like they bite — float equality, currency arithmetic, rounding, division by zero, overflow, unit mismatches. Use when writing any arithmetic beyond a counter: money, percentages, averages, coordinates, durations, aggregations, or comparisons of computed values.
---

# numerical-care

Numeric bugs pass every casual test and then misprice an order. The standing hazards:

1. **Never compare floats with `==`.** `0.1 + 0.2 != 0.3`. Compare within an epsilon appropriate to the scale, or restructure to avoid the comparison. Same for testing: assert-almost-equal, not equal.
2. **Money is integers (cents) or Decimal — never binary floats.** Accumulating float currency drifts; a million small additions of drift is an accounting incident. Check what the codebase already uses (see search-existing-patterns) and match it; if it uses floats for money, flag that, don't extend it.
3. **Rounding is a policy decision, not a default:** round-half-up, banker's rounding, floor for "don't overcharge" — pick deliberately, and round once at the boundary (display/storage), not repeatedly mid-calculation where errors compound.
4. **Division needs a zero plan.** Averages of empty lists, percentages of zero totals, rates over zero-duration windows — every `/` gets the "what if the denominator is 0" question (see edge-case-sweep), and integer division vs true division checked in languages where they differ.
5. **Mind the representation limits:** 32-bit overflow in languages that wrap silently, JavaScript's single number type corrupting int64 IDs beyond 2^53 (keep big IDs as strings), precision loss casting between types.
6. **Units and scales travel with the value in your head:** ms vs s, cents vs dollars, bytes vs MB, degrees vs radians, UTC offset vs duration. A wrong-unit bug is invisible in the code (`timeout = 30` — of what?) — name variables with units (`timeout_ms`) when ambiguity exists.
7. **Aggregations over floats depend on order and method** — summing a million floats naively loses precision; use the platform's compensated sum (`math.fsum`) when it matters.

Test: for each arithmetic line, "what value makes this wrong — zero, negative, huge, or 0.1?" If one does and isn't handled, it's not done.
