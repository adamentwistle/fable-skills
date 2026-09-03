1. Float accumulation drifts across rows. Fix: sum `Decimal` built from the raw strings, or integer cents.
2. `float()` accepts `nan`, so one bad cell silently makes the whole total NaN. Fix: reject non-finite values.
3. `float()` accepts `inf` and `infinity`, poisoning the total the same way. Fix: same finiteness check.
4. Huge price times huge qty overflows to `inf` with no error. Fix: `Decimal` plus a plausibility bound.
5. A very large `int` qty raises `OverflowError` on conversion to float. Fix: `Decimal`.
6. Once the total is large, small rows are absorbed and stop counting. Fix: `Decimal`, or `math.fsum` if floats stay.
7. Float summation is order-dependent, so sorted input gives a different answer. Fix: same as above.
8. Negative price or qty silently subtracts revenue. Fix: reject, or route to an explicit refunds bucket.
9. Empty-string cells raise `ValueError` with no row context. Fix: validate and fail with the row number and offending value.
10. Short rows give `None` from `DictReader`, raising `TypeError`. Fix: treat `None` as missing, same error path.
11. Long rows shift columns and land extras under `restkey`, so the wrong column can parse as price. Fix: check field count per row.
12. Missing `price` or `qty` header raises a bare `KeyError`. Fix: validate headers once before the loop.
13. A UTF-8 BOM makes the first header `\ufeffprice`. Fix: open with `encoding="utf-8-sig"`.
14. Header case and whitespace variants such as `Price ` miss. Fix: normalize headers.
15. Currency symbols and thousands separators like `$1,234.50` raise. Fix: strip a documented set or reject with a clear message.
16. Locale decimal commas: `1,50` raises and `1.234` misparses as 1.234. Fix: enforce one documented number format, never guess.
17. `float()` accepts `1e3` and `1_000`, which rarely appear legitimately. Fix: strict regex like `^-?\d+(\.\d{1,2})?$`.
18. `int()` and `float()` accept Unicode digits such as Arabic-Indic and fullwidth. Fix: same ASCII-only regex.
19. `int()` rejects `3.0` but accepts ` +3 `. Fix: decide if qty may be fractional and validate to that rule.
20. Whitespace is tolerated inconsistently. Fix: strip, then validate.
21. Python 3.11+ raises on integer strings over 4300 digits. Fix: bound string length before parsing.
22. One bad row aborts the whole run and you cannot tell which. Fix: catch per row, re-raise with index, or collect errors and report counts.
23. Return type is `int` for empty input and `float` otherwise. Fix: always return `Decimal` quantized to 2 dp.
24. Empty input returns 0, indistinguishable from "no data". Fix: return row count too, or raise when empty is unexpected.
25. `rows=None` or list rows from `csv.reader` raise `TypeError`. Fix: type-check up front.
26. No rounding policy for per-line versus end-of-sum and which mode. Fix: quantize per line with `ROUND_HALF_UP`, or whatever invoicing does, and document it.
27. `Decimal` also accepts `NaN` and `Infinity`. Fix: check `is_finite()` after construction.
28. Mixed currencies are summed as one number. Fix: require a currency column and group, or assert a single currency.
29. Duplicate rows from repeated exports double count. Fix: dedupe on an order or line ID.
30. `price` is ambiguous: unit or line total, pre or post tax. Fix: document and name the function to match.
31. Implausible quantities such as `999999999` pass. Fix: sanity bounds with a clear error.
32. Already-numeric cells and strings are handled differently, so `2.0` versus `"2.0"` diverge. Fix: coerce with `str()` and validate uniformly.
33. No tests cover any of the above. Fix: add a case per finding.