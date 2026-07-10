<!-- RECOVERED VERBATIM from session ec152094-e614-4e0c-a8d5-c098728fc4af (2026-07-07). Agent run: edge-skills-1. Content below the line is the agent's final output, unmodified. -->

---

1. Empty `rows` returns `int 0`, not the `Decimal`/money type every other path yields — seed `total = Decimal('0')` for a consistent return type.
2. Missing `'price'`/`'qty'` key raises bare `KeyError` — check membership and raise naming the row index and field.
3. Present-but-`None` value (`float(None)`/`int(None)`) raises `TypeError`, distinct from empty string — validate for `None` explicitly before parsing.
4. Empty string `''` raises `ValueError` on both `float('')` and `int('')` — treat as a named parse error, not a crash.
5. Non-numeric string (`'abc'`, `'$5'`, currency symbols) raises bare `ValueError` — wrap parse in try/except that reports row/field/value.
6. `int('3.0')` raises `ValueError` — a decimal-looking qty string dies; parse qty via `Decimal` then check it's integral.
7. Thousands separators / locale commas (`'1,000'`, `'1.000,50'`) misparse or raise — normalize/reject with a clear message.
8. `float('nan')` and `float('inf')`/`'-inf'` parse silently and poison the total — reject non-finite values explicitly.
9. Scientific notation (`'1e3'`) is silently accepted by `float` — reject if unintended.
10. Negative `price` or `qty` silently reduces revenue — validate non-negativity unless refunds are intended.
11. Huge magnitudes lose precision or overflow to `inf` in `float` — parse as `Decimal` and bound-check.
12. `float` for money accumulates binary rounding drift — compute in integer cents or `Decimal` throughout.
13. No rounding policy on fractional cents — define and apply per-line quantization (e.g. `ROUND_HALF_UP` to cents).
14. Whitespace like `' 5 '` parses, but non-breaking/unicode spaces or full-width/unicode digits parse inconsistently — strip/normalize and reject ambiguous input.
15. `rows` itself being `None` or not iterable raises `TypeError` before the loop — guard the input type.
16. Duplicate rows are summed twice with no dedup key — dedupe on a row identifier if double-counting is a business hazard.
17. Failures give no row context (which of 10k rows) — include the row index/field/offending value in every raised error.

---
Model suitability: this is a small, self-contained static code-review task with a fixed 17-item output. Opus 4.8 (1M context) with extended thinking is heavier than needed — the 1M context window is unused (no large codebase) and deep reasoning adds little here. Sonnet (or even Haiku) with thinking off would have been the appropriate, more cost-efficient choice.
