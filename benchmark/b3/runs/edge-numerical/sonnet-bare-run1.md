1. Missing key (`r['price']`/`r['qty']` KeyError) — use `.get()` with default or validate schema upfront.
2. Missing/empty string value ('' fails `float()`/`int()`) — skip or default to 0 on empty.
3. Non-numeric garbage (`"N/A"`, `"$5"`, currency symbols/commas) — sanitize/strip before cast or catch `ValueError` per row.
4. Whitespace-padded values (`" 5 "`) — `.strip()` before cast (usually handled by float/int, but combined with symbols it isn't).
5. Negative price or qty (refunds vs. bad data indistinguishable) — decide policy and validate sign explicitly.
6. Qty as float string (`"2.5"`) — `int()` raises; use `int(float(x))` or reject non-integer quantities deliberately.
7. Price/qty as `None` (null in CSV) — guard against `NoneType` before cast.
8. Scientific notation or `inf`/`nan` strings (`float("nan")`, `float("inf")` succeed silently) — explicitly reject non-finite floats.
9. Float precision drift accumulating over many rows — use `Decimal` for currency instead of `float`.
10. Extremely large qty/price (overflow into unreasonable totals, DoS via huge exponent string) — cap/sanity-check magnitude.
11. Locale-formatted numbers (`"1.234,56"` European decimal) — normalize locale before parsing or fail loudly.
12. One bad row aborts the entire aggregation (no partial result, no visibility into which row) — wrap per-row parse in try/except, collect errors, continue.
13. Silent data loss if rows are dropped upstream — return count of skipped/failed rows alongside total.
14. No row-level currency check (mixed currencies summed as if same) — validate a currency column exists/matches if present in source data.