1. `rows` is None or a non-iterable → TypeError; validate it is an iterable of mappings before the loop.
2. Rows are lists (csv.reader, not DictReader) → TypeError on `r['price']`; require mappings or take explicit column indexes.
3. Missing `price`/`qty` key from header typo, case, trailing space, or a UTF-8 BOM (`\ufeffprice`) → KeyError; normalize headers once and open with `utf-8-sig`.
4. Value is None (DictReader pads short rows) or a list (restkey overflow) → TypeError; treat None as missing and reject ragged rows.
5. Empty or whitespace-only field → ValueError; strip, then choose explicitly: skip, zero, or fail with row number.
6. Repeated header line from concatenated files (`price`,`qty` as values) → ValueError; detect and skip header-shaped rows.
7. Currency symbols, thousands separators, stray quotes (`$1,234.50`) → ValueError; strip a known set or reject, never guess.
8. Locale decimal comma (`1,50`) fails while `1.234` may silently mean 1234; parse against one documented number format.
9. `float()` accepts `nan`, `inf`, `-infinity` → total silently becomes NaN/inf and all comparisons lie; reject with `math.isfinite`.
10. `float()`/`int()` accept underscores (`1_000`), Unicode digits (`١٢`), `+5`, and exponents (`1e3`) → junk passes; validate with a strict regex or `Decimal` and forbid exponents.
11. `int()` rejects `2.0`, `1e3`, `3.5` for qty → ValueError; decide if fractional quantities are legal, and never "fix" with `int(float(x))`, which truncates 1.7 to 1.
12. Negative price or qty silently subtracts → refunds and data errors are indistinguishable; reject negatives or make refund handling an explicit policy.
13. Binary float accumulation (`0.1 + 0.2`) drifts by cents and grows with row count; use `Decimal` or integer minor units and quantize to cents.
14. Left-to-right summation suffers catastrophic cancellation when large positives and negatives mix; use `math.fsum` if you must stay in float.
15. Products above 2^53 (~9e15) lose integer exactness; another reason for Decimal or int cents.
16. `float * int` with qty above ~1.8e308 → OverflowError; bound qty to a sane maximum.
17. `float()` of an overlong digit string silently returns `inf`, while `int()` on >4300 digits raises ValueError (Python 3.11+); cap field length before parsing.
18. Prices with more than two decimals (`1.005`) round unpredictably in binary; quantize per row with an explicit rounding mode, since HALF_UP vs HALF_EVEN is a business decision.
19. Rounding per line versus rounding the total gives different answers; pick one, document it, test it.
20. Returns `int` 0 for empty input but `float` otherwise → type-dependent bugs downstream; initialize to `Decimal("0.00")` and always return that type.
21. Empty input silently returns 0, indistinguishable from "every row was skipped"; return a row count alongside the total or fail on empty.
22. First bad row raises a bare ValueError/KeyError/TypeError with no row number or field → undebuggable on a large file; re-raise with row index, field name, and raw value.
23. Fail-fast discards all work on a huge file; offer strict (abort) and lenient (skip and log) modes instead of one implicit behavior.
24. Peeking at the first row to validate headers consumes a one-shot iterator; validate inside the loop on first iteration or use `itertools.tee`.
25. Mixed currencies summed as one number → meaningless total; require a single currency or group by a currency column.
26. Duplicate rows from re-exported batches double-count; dedupe on a transaction ID or document that the caller must.
27. Callers printing the float get `1234.5000000000002`; format from the quantized Decimal, never `str(float)`.