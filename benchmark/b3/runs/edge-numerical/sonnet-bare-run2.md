1. `r['price']` missing/None key → KeyError: use `r.get('price', '0')` or validate schema upfront.
2. `r['price']` empty string or non-numeric (`"N/A"`, `""`) → ValueError from `float()`: wrap parse in try/except, skip or flag row.
3. `r['qty']` non-integer string (`"3.0"`, `""`) → ValueError from `int()`: parse defensively, reject or coerce via `int(float(x))` with validation.
4. Negative price or qty (refunds/returns encoded oddly, or data corruption) → silently distorts total: decide policy (allow, clamp, or reject) explicitly.
5. NaN/Inf strings (`"nan"`, `"inf"`) parse successfully via `float()` and poison the sum → explicitly reject non-finite values with `math.isfinite`.
6. Float accumulation of money → rounding drift over many rows: use `Decimal` (from strings, not floats) instead of `float`.
7. Thousands separators or currency symbols (`"$1,200.50"`) → ValueError: strip/normalize before parsing.
8. Leading/trailing whitespace in fields → usually fine for `float`/`int` but fails on locale decimal commas (`"1,50"`): normalize decimal separator explicitly or reject.
9. Extremely large qty/price (overflow-adjacent or data error, e.g. qty in the billions) → produces bogus totals with no error: add sanity bounds/row-level validation.
10. `rows` itself None or not iterable → TypeError: guard input type at function entry.
11. A row that isn't a dict (e.g. a list from a malformed CSV parse) → TypeError on `r['price']`: validate row shape.
12. Boolean-like or scientific-notation strings (`"1e10"`, `"True"`) parse unexpectedly → `float("1e10")` succeeds silently: add explicit format validation if unexpected magnitudes matter.
13. No per-row error reporting → one bad row kills the whole aggregation with no indication which row: catch per-row, collect errors/skipped rows for the caller.
14. Empty `rows` list → returns 0 silently, which may be indistinguishable from "no data" vs "all rows failed": consider distinguishing skipped-row count from true zero-revenue.