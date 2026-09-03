1. `KeyError` if a row lacks `price` or `qty` — validate keys per row and report the row index.
2. `float(None)`/`int(None)` `TypeError` when `csv.DictReader` short-fills a row with `None` — treat missing as an explicit error or a configured default.
3. Empty or blank string (`""`, `"-"`, `"N/A"`) raises `ValueError` with no row context — wrap per row and re-raise with the line number.
4. Formatted money (`"$1,299.00"`, `"1 299"`, `"(50.00)"` for negative) raises `ValueError` — normalize/strip currency and separators before parsing.
5. Locale decimal comma (`"1,50"`) parses as `ValueError` or, once commas are stripped, silently becomes 150 — decide the locale explicitly rather than stripping blindly.
6. `int("3.0")` raises even though Excel/pandas exports emit it constantly — parse quantity via `Decimal` then check it's integral.
7. `float("nan")`/`"inf"`/`"1e400"` parse fine and poison the whole total silently — reject non-finite values after parsing.
8. Binary floating point makes cent totals wrong (`0.1+0.2`) and order-dependent — accumulate in `decimal.Decimal`, not `float`.
9. Precision loss grows with row count and mixed magnitudes — Decimal fixes this too; quantize once at the end to the currency's minor unit.
10. Rounding policy is undefined (per line vs. per total, half-up vs. banker's) — pick one and state it, since `float` gives you banker's-ish by accident.
11. Negative price or qty is accepted as legitimate revenue — validate sign, allowing negatives only if refunds are genuinely in scope.
12. Huge quantity raises `OverflowError` at `float * int` — bound `qty` to a sane maximum.
13. A numeric string over 4300 digits raises `ValueError` in Python 3.11+ (int digit limit), an easy DoS from untrusted CSV — cap field length before parsing.
14. Underscores (`"1_000"`) parse silently as 1000 — reject with a strict regex or `Decimal`, which refuses them.
15. Non-ASCII digits (`int("٣")` → 3) parse silently — same strict validation.
16. A UTF-8 BOM on the first header makes the key `"\ufeffprice"`, so lookup fails on file one of every import — open with `encoding="utf-8-sig"`.
17. One bad row aborts the entire run and discards all prior work — collect errors and either fail with the full list or skip-and-report.
18. Empty input returns `int` `0` while non-empty returns `float` — return one type always (`Decimal("0.00")`).
19. `rows` as a generator is consumed on first pass and can't be retried or counted — accept a sequence, or materialize deliberately.
20. No currency field is checked, so mixed-currency rows sum into a meaningless number — group by currency or assert a single one.
21. Non-dict rows (from `csv.reader` instead of `DictReader`) fail with an opaque `TypeError` — validate the row shape up front.