1. Binary float drift: `float("0.10")` isn't 0.10 and cents accumulate error over many rows; parse with `Decimal(str)` directly from the string, never via float.
2. Silent NaN/inf: `float("nan")`, `"inf"`, `"-Infinity"` (any case) parse fine and poison the total; reject non-finite values with `math.isfinite` (or `Decimal.is_finite()`).
3. Overflow: `"1e400"` becomes inf silently, and a huge `int(qty)` times a float raises OverflowError; bound-check magnitudes before multiplying.
4. Cancellation: mixing large positives with refunds (negatives) destroys float precision; use Decimal, or at least `math.fsum` if staying float.
5. Order-dependent sum: float addition isn't associative, so re-sorted CSVs give different totals; Decimal fixes this too.
6. Sub-cent prices like `"0.005"` and per-line vs end-of-sum rounding policy are undefined; quantize with an explicit rounding mode at the agreed point.
7. Currency formatting: `"$1,234.56"`, `"(12.00)"`, `"1 234"`, trailing `"USD"` all raise ValueError; strip/normalize with a strict regex and reject anything unrecognized.
8. Locale decimal comma: `"12,50"` fails (or misparses as thousands after stripping commas); fix the expected locale explicitly.
9. Quantity as `"3.0"`, `"1e3"`, `"3,000"` raises in `int()`; parse via Decimal and require it to be integral.
10. Empty, whitespace-only, `None`, `"N/A"`, `"NULL"` cells raise ValueError/TypeError; define null handling (skip, zero, or fail) explicitly rather than by accident.
11. `DictReader` fills short rows with `None` and long rows into a `None` key; validate column count per row.
12. Missing or misnamed columns (`"Price "`, `"PRICE"`, BOM-prefixed `"\ufeffprice"`) raise KeyError; normalize headers (strip, casefold, strip BOM) once up front.
13. Header row parsed as data (plain `csv.reader`) or non-dict rows raise TypeError; assert row type on entry.
14. Negative price or qty silently shrinks revenue and can hide corruption; enforce a sign policy (allow refunds only where flagged).
15. Zero qty with garbage price still validates as 0 revenue, masking bad data; validate price even when qty is 0.
16. Lenient parsers accept underscores (`"1_000"`), Unicode digits (`"٣"`), leading `+`, surrounding whitespace; decide whether that leniency is wanted and whitelist if not.
17. Decimal raises `InvalidOperation` not ValueError, and `Decimal("NaN")`/`"Infinity"` parse successfully; catch both exception types and check finiteness.
18. Decimal default context is 28 digits and thread-global; use `localcontext()` with precision sized for the largest plausible total.
19. Mixed currencies across rows sum silently; require a currency column and refuse or group by it.
20. Swapped columns (price/qty) produce a plausible wrong number; sanity-check ranges (qty integral and small, price bounded).
21. One bad row aborts the whole run with no row index or value in the traceback; wrap per-row errors with row number and raw cell content.
22. Return type varies: `0` (int) for empty input, `float` otherwise; return a consistent `Decimal("0.00")`.
23. `rows=None` raises TypeError, and a dict iterates its keys; type-check input or require an iterable of mappings.
24. Materialized list for large files is memory-heavy; accept any iterable and stream from the reader.
25. Duplicate rows aren't detectable; dedupe on a row ID if one exists, or at least count rows processed.
26. No observability: no count of rows summed, skipped, or rejected; return or log those counts alongside the total.
27. Silent partial success if callers later add try/except around the loop; make skip vs fail an explicit parameter, default fail.