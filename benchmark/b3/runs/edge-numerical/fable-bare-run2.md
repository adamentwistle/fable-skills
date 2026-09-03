1. Float accumulation drifts (0.1+0.2 style); parse to `Decimal` and sum in `Decimal`, or integer cents.
2. Totals past 2^53 silently lose cents; same fix.
3. `float()` accepts `'nan'`, `'inf'`, `'-inf'`, `'1e999'` and poisons the total (NaN even passes `==` tests); reject non-finite after parsing, and note `Decimal('NaN')`/`Decimal('Infinity')` parse too, so check `is_finite()`.
4. `'1e-400'` underflows to 0.0 silently; bound exponent/scale.
5. Huge price×qty overflows float to `inf`; Decimal/int cents plus a plausibility cap.
6. Negative price or qty silently subtracts; reject negatives or handle refunds via an explicit column.
7. `'1_000'`, `'+5'`, `' 3 '` are accepted by `float`/`int`; validate with a strict ASCII regex.
8. Non-ASCII digits (Arabic-Indic, full-width) parse successfully; same regex.
9. Prices with >2 decimals or exponent form (`'12.999'`, `'1.2e1'`); enforce scale and quantize with an explicit rounding mode.
10. Per-line vs end-of-sum rounding gives different answers; pick one (usually per line, HALF_UP or per finance policy) and document it.
11. Thousands separators, currency symbols, decimal commas (`'1,234.56'`, `'$9.99'`, `'9,99'`) raise or mis-parse; normalize or reject at ingest.
12. Empty string, whitespace-only, or `None` cell raises `ValueError`/`TypeError`; decide skip-vs-fail explicitly and log skips.
13. Missing or misnamed key (`'Price'`, BOM `'\ufeffprice'`, trailing space) raises `KeyError`; normalize and validate headers up front.
14. Repeated header row from concatenated CSVs puts `'price'` in the data; detect and skip.
15. Fractional qty (`'2.5'`) fails `int()`; decide whether fractional quantities are legal and parse accordingly.
16. Absurdly long digit strings hit Python's int-string limit (ValueError in 3.11+); cap field length.
17. One bad row aborts everything with no row context; wrap parse errors with row index and raw values, or collect-and-report.
18. Row not a dict (from `csv.reader`) or `rows` is `None`; type-check input.
19. Empty input returns `int` 0, non-empty returns float; return a consistent `Decimal('0.00')`.
20. Mixed currencies summed blindly; require a single currency or group by it.
21. Cancelled/refunded/test rows counted as revenue; filter on a status column if one exists.
22. Duplicate rows double-count; dedupe on an order/line id if available.
23. Zero-qty rows are harmless but usually signal bad data; count and log them.
24. If floats remain, summation is order-dependent; use `math.fsum`.
25. Generator input is consumed once so retries see nothing; materialize or document.