1. `KeyError` if a row lacks `price` or `qty` — use `r.get(...)` with a default or validate the header set up front.
2. `TypeError` if a value is `None` (empty CSV cell parsed as null) — coerce `None` to `"0"` or skip the row explicitly.
3. `ValueError` on non-numeric text like `"N/A"`, `""`, or `"1,234"` — wrap the conversion and route bad rows to an error list.
4. `int("3.0")` raises even though the value is a valid quantity — parse with `int(Decimal(s))` or `int(float(s))` after a range check.
5. Currency symbols and thousands separators (`"$1,299.00"`) fail conversion — strip `$,` and whitespace before parsing.
6. Leading/trailing whitespace or a UTF-8 BOM on the first field silently breaks parsing — `.strip()` the value and open the CSV with `encoding="utf-8-sig"`.
7. Binary floating point loses cents; `0.1 + 0.2` style drift compounds over many rows — use `decimal.Decimal` for money and quantize at the end.
8. Summation error grows with row count even with clean floats — use `math.fsum` if you stay on floats, or Decimal to avoid it entirely.
9. `float("nan")` and `float("inf")` are accepted and poison the total irrecoverably — reject with `math.isfinite` before adding.
10. `float("1e400")` overflows to `inf`, and huge `int` quantities make the product `inf` — bound magnitudes per row.
11. Negative prices or quantities pass silently and can zero out a total — validate sign unless refunds are intended, then track them separately.
12. Unicode digits (`"١٢٣"`, `"１２３"`) convert successfully but are almost certainly bad data — restrict input to ASCII digits with a regex.
13. `int()` accepts underscores (`"1_000"`) — same regex guard rejects it.
14. `rows` being `None` or a one-shot generator makes the function crash or silently return `0` on a second call — accept only a materialized sequence, or document single-pass use.
15. A row that isn't a dict (a stray list from a ragged CSV line) raises `TypeError` — check the row shape before indexing.
16. Empty input returns `0` (an `int`), not `0.0` or `Decimal("0.00")` — return a consistent type for all paths.
17. Extra columns from ragged rows are ignored, so a shifted line computes a wrong-but-plausible total — assert the field count per row.
18. Failures are all-or-nothing: one bad row kills the whole aggregate with no indication of which — collect per-row errors with their index and report them.
19. Duplicate-keyed dicts or repeated CSV lines are double-counted — dedupe on an order/line ID if the data has one.
20. No mixed-currency guard — the total is meaningless if rows span currencies, so group by a currency column or assert it's uniform.