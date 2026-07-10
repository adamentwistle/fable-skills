<!-- RECOVERED VERBATIM from session ec152094-e614-4e0c-a8d5-c098728fc4af (2026-07-07). Agent run: edge-bare-1. Content below the line is the agent's final output, unmodified. -->

---

1. `KeyError` if any row lacks `'price'` or `'qty'` — use `r.get(k)` with validation/default.
2. `ValueError` on non-numeric/garbage strings (`"N/A"`, `""`) aborts the whole run — wrap per-row in try/except and skip-or-log.
3. `int(r['qty'])` rejects decimal-formatted quantities like `"3.0"` or `"1e2"` — parse via `float` then validate integrality, or `Decimal`.
4. `None` value (missing CSV cell) raises `TypeError` in `float()`/`int()` — coerce/validate before converting.
5. Binary float is wrong for money (`0.1*3 != 0.3`, rounding drift) — use `Decimal(str(...))` and quantize to cents.
6. Formatted numbers (`"$1,299.00"`, thousands commas, trailing `%`) fail `float()` — strip currency/grouping symbols first.
7. `float("nan")`/`float("inf")` parse silently and poison `total` irrecoverably — reject with `math.isfinite()`.
8. Negative price or qty (refunds, corrupt data) pass unchecked — assert/validate sign against expected domain.
9. Leading/trailing whitespace is tolerated by `float` but `"1 000"` (space-grouped) is not — normalize/`strip()` explicitly.
10. Underscores (`"1_000"`) and unary `+` are silently accepted by `int()`/`float()`, masking malformed input — validate against a strict numeric pattern.
11. Locale decimal comma (`"1,50"` = 1.5 in EU) misparses or errors — normalize separators to a known locale before converting.
12. Non-ASCII/full-width or other Unicode digits are accepted unexpectedly — restrict to ASCII digits.
13. Booleans slip through (`True→1.0`) if upstream typing is loose — enforce string/str-checking on inputs.
14. Huge magnitudes overflow `float` to `inf` without error — cap/validate or use `Decimal`.
15. `total` starts as `int 0` then becomes `float`, and empty/None `rows` fails iteration or returns bare `0` with no unit/currency context — guard input and return a typed money value.
16. `r` not being a dict (malformed parse, header row leaking in) raises `TypeError` — validate row shape before indexing.
17. No overflow/precision on aggregation across millions of rows (float error accumulates) — sum with `Decimal` / `math.fsum`.
18. No dedup or idempotency — repeated/duplicate rows are double-counted silently; dedupe on a key if source can repeat.

---
Model suitability: this is a bounded, well-specified code-review enumeration. Opus 4.8 is somewhat heavier than needed; Sonnet 4.5 would handle it at lower cost with comparable quality, and extended thinking is unnecessary for a task this scoped.
