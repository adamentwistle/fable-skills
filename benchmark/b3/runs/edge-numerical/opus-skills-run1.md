1. Money in binary float — `float(price)` can't represent 0.10, and errors compound across rows; parse to `Decimal(str)` or integer minor units.
2. Sum drift over many rows — naive float `+=` loses low bits; use `Decimal` accumulation, or `math.fsum` if floats stay.
3. Return type varies — `0` (int) for empty input, float otherwise; initialize to the same type you return (`Decimal("0")`).
4. No rounding policy — sub-cent fractions leak to the caller; round once at the boundary with a named policy (half-up for display, or keep exact Decimal).
5. `float("nan")` / `"inf"` / `"1e400"` parse silently and poison the whole total to NaN or inf; reject non-finite values explicitly.
6. Missing `price`/`qty` key raises bare `KeyError: 'price'` with no row identity; catch and re-raise naming the row number and available keys.
7. `None` value (DictReader `restval` on a short row) raises `TypeError: float() argument must be...`; check for None separately from empty string.
8. Empty string `""` raises `ValueError: could not convert string to float: ''` with no row context; validate and report row + column + raw value.
9. Formatted numbers fail — `"$12.50"`, `"1,234.00"`, `"12,50"`, `"(5.00)"` for negatives all raise `ValueError`; strip/normalize at the parse boundary or reject with the offending literal.
10. `int("3.0")` raises even though it's a legitimate CSV quantity; decide whether decimal quantities are accepted, then parse accordingly.
11. `int()` silently accepts `"1_000"` and non-ASCII digits (`"٣"`), giving a wrong-but-plausible quantity; restrict with a regex or `str.isascii()` check.
12. Negative price or qty is accepted silently; either allow deliberately (refunds) or reject with a message naming the value.
13. Huge `qty` overflows on multiply — `int` is unbounded but `float * huge_int` raises `OverflowError: int too large to convert to float`; cap qty at a documented maximum.
14. Total beyond 2^53 loses integer precision in float; another reason for Decimal/int cents.
15. One bad row aborts the whole file, discarding every prior row's work and returning nothing; decide skip-and-collect vs fail-fast, and if skipping, return the errors alongside the total.
16. No `rows` guard — `None` raises `TypeError: 'NoneType' is not iterable`; a generator is consumed on first call, so a second call silently returns 0.
17. Non-dict rows (from `csv.reader` rather than `DictReader`) raise `TypeError: list indices must be integers`; validate the row shape once, not per field.
18. UTF-8 BOM makes the first header `"\ufeffprice"`, so `KeyError: 'price'` on every row; open with `encoding="utf-8-sig"`.
19. Header case and whitespace (`"Price"`, `" qty"`) cause the same KeyError; normalize header keys once.
20. Duplicate `price` columns — DictReader keeps only the last; detect and reject duplicate headers.
21. No currency field, so mixed-currency rows sum into a meaningless number; group by currency or assert a single one.
22. Units are unstated — pounds or pence, unit price or line total; encode it in the name (`price_minor_units`) and document it.
23. Nothing is logged, so a rejected file gives no clue which row was bad; log row number, column, and raw value at the point of rejection.

Static review only — nothing run.