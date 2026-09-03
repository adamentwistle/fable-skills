1. Binary float rounding (19.99 × 3 → 59.97000000000001) corrupts money — parse with `Decimal(str)` and quantize to cents once at the end.
2. Float accumulation error grows with row count and depends on row order — sum `Decimal`s, or `math.fsum` if floats are forced on you.
3. `float()` accepts "nan", "inf", "-Infinity" (any case, padded) and one NaN poisons the whole total — reject non-finite values; `Decimal` also accepts "NaN"/"Infinity"/"sNaN", so check `is_finite()` there too.
4. "1e400" silently becomes `inf` and "1e-400" silently becomes 0.0 — enforce an explicit magnitude range.
5. `int()`/`float()` accept "1_000", "+5", surrounding whitespace/newlines, and non-ASCII digits ("١٢٣", fullwidth "５") — validate against a strict ASCII regex before converting.
6. Currency symbols, thousands separators, and locale decimal commas ("$1,234.56", "12,50") raise or misparse (12,50 → 1250 after stripping) — define one accepted format and reject everything else.
7. qty "3.0", "1e3", "1.5" raise in `int()`, and fractional quantities are silently impossible — parse via `Decimal` and require `== to_integral_value()`.
8. Negative price or qty silently subtract from revenue — decide a refund policy and enforce sign explicitly.
9. Empty string, whitespace, or `None` (short rows from `csv.DictReader`) raise `ValueError`/`TypeError` — treat blank as missing and reject or skip by stated policy.
10. Missing, renamed, differently-cased, or BOM-prefixed headers ("Price", "price ", "\ufeffprice") raise `KeyError` — normalise headers, open with `utf-8-sig`, validate the schema before the loop.
11. A repeated header row inside the data ("price","qty") raises mid-file — detect and skip.
12. Any bad row raises with no row number and discards all partial work — wrap per row and re-raise with index and raw values.
13. If you add skipping, silent skips hide data loss — return processed/rejected counts alongside the total.
14. Empty input returns `int` 0, non-empty returns `float` — always return one type (`Decimal("0.00")`).
15. `rows` that is `None`, a bare dict, or list-of-lists from `csv.reader` fails with a confusing `TypeError` — type-check the input.
16. A generator input is consumed once, so a second call sums nothing — materialise or document.
17. Python 3.11+ raises `ValueError` for int strings over 4300 digits, and below that parse time is quadratic (DoS) — cap field length.
18. Ints above 2^53 lose precision when multiplied by a float, and float overflow raises `OverflowError` — `Decimal` avoids both.
19. Large positive and negative rows cancel catastrophically in float — `Decimal` again.
20. `Decimal` defaults to ROUND_HALF_EVEN — pick ROUND_HALF_UP (or the business rule) explicitly.
21. Prices with more than 2 dp give different totals under per-line vs whole-total rounding — match whatever the invoices do.
22. No currency column, so mixed currencies sum meaninglessly — require or assert a single currency.
23. Duplicate rows from re-exports or retries double count — dedupe on an id if one exists.
24. Zero price or zero qty rows are legal but usually bad data — count and report them.
25. `Decimal` precision is a global context; a caller's `getcontext().prec` change silently truncates — use `localcontext()` with fixed precision.
26. Unicode minus ("−5"), trailing minus ("5-"), and parenthesised negatives ("(5.00)") raise or misparse — normalise or reject.