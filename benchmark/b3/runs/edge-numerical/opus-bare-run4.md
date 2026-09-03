1. `rows` may be None or a non-iterable — guard with an early return of `0` (or raise a clear TypeError).
2. Missing `'price'`/`'qty'` keys raise KeyError mid-loop — use `r.get(...)` with a default or skip-and-log.
3. `None` values from empty CSV cells raise TypeError on `float(None)` — coerce empty/None to `"0"` before parsing.
4. Empty strings and whitespace-padded values (`" 12 "`) — `.strip()` first, treat `""` as zero or skip.
5. Malformed numerics ("N/A", "1,299.00", "$5.00") raise ValueError — strip currency/thousands separators, wrap in try/except and route bad rows to an error list.
6. `int("3.0")` raises ValueError even though the value is a valid integer — parse quantity via `int(Decimal(s))` or `float()` then check integrality.
7. `float()` silently accepts `"nan"`/`"inf"` and poisons the whole total to NaN — reject non-finite values with `math.isfinite`.
8. Binary float accumulation loses cents on large row counts — use `decimal.Decimal` for price and total throughout.
9. Even with floats, sequential `+=` compounds rounding — use `math.fsum` over a generator of line totals.
10. No rounding discipline on the result — quantize to 2 decimal places with `ROUND_HALF_UP` at the end, never mid-loop.
11. Negative price or qty pass silently (refunds vs. corrupt data) — decide the policy explicitly and validate against it.
12. Absurd magnitudes (`1e308`) overflow to `inf` on multiply — bound-check each parsed value against a sane maximum.
13. Locale decimal commas (`"12,50"` meaning 12.50) parse wrongly or fail — normalize to a known locale before parsing.
14. Unicode digits/minus signs (`"１２"`, `"−5"`) — `float()` accepts some, rejects others; normalize with NFKC.
15. Non-dict entries in `rows` raise TypeError on subscript — validate the row type before indexing.
16. Failures are all-or-nothing with no row context — catch per row and report the index plus the offending value.
17. Return type flips between `int` `0` and `float` — return a consistent type (`Decimal` or a rounded float).
18. A generator passed as `rows` is consumed silently, so a retry yields `0` — materialize with `list()` or document the one-shot contract.
19. Duplicate/repeated rows are summed blindly — dedupe on a business key upstream if the CSV can double-write.
20. No currency awareness — summing mixed-currency rows is meaningless; group by a currency column or assert a single one.