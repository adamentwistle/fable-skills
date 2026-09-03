1. Missing key (`'price'`/`'qty'` absent) → `KeyError`: use `r.get('price')`/`.get('qty')` with validation.
2. Non-numeric string (`"abc"`) → `ValueError`: wrap conversion in try/except and skip or log bad rows.
3. Empty string (`""`) → `ValueError` on both `float`/`int`: treat blank as 0 or reject row explicitly.
4. Whitespace/currency symbols (`" $12.50 "`) → `ValueError`: strip and sanitize before parsing.
5. Negative price or qty (refunds vs. bad data indistinguishable) → clamp or explicitly allow/reject negatives per business rule.
6. Fractional qty (`"2.5"`) → `int()` raises `ValueError`: decide if qty can be decimal, use `float`/`Decimal` instead.
7. `float` binary rounding error accumulates over many rows → use `Decimal` for money instead of `float`.
8. Very large qty/price (overflow-free in Python but can produce absurd totals from corrupted data) → add sanity bounds/range check.
9. `None` values in dict (CSV empty cell parsed as `None` by some loaders) → `TypeError` on `float(None)`: guard for `None`.
10. Locale-formatted numbers (`"1,234.56"`) → `ValueError`: strip thousands separators before parsing.
11. NaN/Inf strings (`"nan"`, `"inf"`) parse successfully via `float()` and silently poison the sum → explicitly reject non-finite values.
12. Scientific notation or hex-like strings accepted by `float`/`int` unexpectedly → validate format strictly if unwanted.
13. One bad row aborts the entire aggregation (no partial result/error report) → collect per-row errors and continue, or report which row failed.
14. Silent total from an empty `rows` list (returns 0 indistinguishable from "computed") → make ambiguity explicit if callers need to know "no data" vs "zero revenue".