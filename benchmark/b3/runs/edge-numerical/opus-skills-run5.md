1. Binary float for money — `float("0.1")*3` gives 0.30000000000000004 and drift compounds over thousands of rows; parse price with `Decimal` and keep an integer-cents or Decimal total.
2. Accumulating floats in a loop is order-dependent and loses low bits; use `Decimal` (or `math.fsum` if floats are mandatory).
3. No rounding policy — the result carries junk digits past the cent; round once at the end with a named policy (`ROUND_HALF_UP` or `ROUND_HALF_EVEN`), never per row.
4. `float("nan")` parses silently and poisons the whole total to `nan`, which then fails every `==` check downstream; reject non-finite values with `Decimal.is_finite()` or `math.isfinite`.
5. `float("inf")` / `"1e400"` likewise parses to infinity; same finiteness check.
6. Missing `'price'` or `'qty'` key raises a bare `KeyError` with no row context; check keys explicitly and raise naming the row index and column.
7. `None` value (empty CSV cell mapped to None by `DictReader` restval) raises `TypeError: float() argument must be...`; treat None distinctly from `""` and reject with the field name.
8. Empty string `""` raises `ValueError: could not convert string to float: ''`; decide explicitly whether empty means 0 or is an error, and say which in the message.
9. `int("3.0")` raises even though 3.0 is a valid quantity — quantities exported as floats break every row; parse via `Decimal` then verify integrality.
10. `int("1e3")` also raises despite being a legal number; same fix.
11. Thousands separators and currency symbols (`"$1,234.56"`, `"1 234,56"`) raise `ValueError`; strip/normalize at the parse boundary or document that only plain decimal is accepted.
12. European decimal comma (`"12,50"`) parses as garbage or raises depending on grouping; pin the expected locale/format and reject the rest.
13. Underscores parse silently — `float("1_000")` is 1000.0, a typo becoming a 1000× error; reject with a strict regex before converting.
14. Non-ASCII digits (Arabic-Indic, fullwidth) are accepted by `int()`/`float()`, so `"٣"` becomes 3; strict-regex the input if that's not wanted.
15. Leading/trailing whitespace and `"+5"` are silently accepted while `"5 "` inside quotes may not be; normalize with `.strip()` deliberately rather than relying on the parser.
16. Negative price or qty (refunds, or malformed data) is summed without comment; decide whether negatives are legal and reject or flag them explicitly.
17. Any bad row aborts the whole run mid-loop with a partial total discarded and no indication of which row; wrap the per-row parse and report row index, field, and offending value.
18. The exception message never names the file, line number, or column, so a 50k-row CSV gives no starting point; include row number and raw value in the raised error.
19. Empty `rows` returns integer `0`, a different type from every other return; return the same type (`Decimal("0.00")`) in all cases.
20. `rows=None` or a non-iterable raises `TypeError: 'NoneType' object is not iterable` from inside the function; validate the argument up front with a message naming the parameter.
21. Passing a generator works once and silently yields 0 on a second call; document that it consumes the iterable, or materialize it.
22. Totals above 2^53 cents lose precision in float; `Decimal` removes the ceiling.
23. Units are unstated — nothing enforces that `price` is dollars, not cents; name the boundary (`price_minor_units`) and convert once at parse time.
24. Duplicate rows are summed as-is; confirm that's intended, since a re-uploaded CSV silently doubles revenue.
25. No log line at any decision point, so a total that looks wrong is unauditable; log the row count parsed, the count rejected, and the final total at info level.