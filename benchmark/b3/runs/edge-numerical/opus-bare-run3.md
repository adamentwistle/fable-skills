1. `KeyError` when 'price' or 'qty' is missing — use `r.get(...)` with an explicit missing-field error naming the row index.
2. `TypeError` when a value is `None` (empty CSV cell parsed as null) — treat `None` as a validation failure, not a zero, unless the spec says otherwise.
3. `ValueError` on empty or whitespace-only strings — check for blank before converting and decide skip-vs-fail explicitly.
4. `ValueError` on formatted money like `"$1,299.00"` or `"1 299,00"` — strip currency symbols and separators (or parse with a locale-aware/known-format cleaner) before converting.
5. `int("3.0")` raises even though the value is a valid whole number — parse qty as `Decimal`/`float` first, then verify it is integral.
6. `float("nan")` and `float("inf")` are accepted silently and poison the entire total into `nan`/`inf` — reject non-finite values with `math.isfinite`.
7. Binary floats can't represent cents exactly, so the total drifts — use `decimal.Decimal` for both price and the accumulator.
8. Accumulating in a loop compounds rounding and makes the result order-dependent — sum with `Decimal`, or `math.fsum` if you must stay in floats.
9. No rounding to a currency unit, so the total carries fractional cents — quantize to 2 decimal places (or the currency's minor unit) at the end.
10. Return type flips between `int` (empty input) and `float` — initialize the accumulator to the money type you actually return.
11. Negative price or qty passes silently, so a corrupt row can subtract revenue — validate sign and allow negatives only if refunds are legitimately in scope.
12. `bool` is a subclass of `int`, so `True` becomes qty 1 — reject non-string/non-numeric types explicitly.
13. `int` and `float` accept underscores and non-ASCII digits (`"1_000"`, `"٣"`) — validate against a strict decimal pattern instead of trusting the constructor.
14. Huge values overflow to `inf` on multiplication in float — another reason to use `Decimal`, with an upper sanity bound per row.
15. A UTF-8 BOM makes the first header `'\ufeffprice'`, so lookups miss — read the CSV with `encoding='utf-8-sig'` and normalize header keys.
16. Header case and stray whitespace (`'Price '`) cause silent `KeyError`s — normalize keys once at parse time.
17. One bad row aborts the whole aggregate with no partial result and no row context — catch per row, attach the index and raw values, and follow a stated policy (fail fast, or collect errors and report them).
18. Non-dict or non-iterable `rows` (a `None`, a single dict, an exhausted generator) fails obscurely or returns 0 — validate the input type and treat an exhausted iterator as an explicit empty case.
19. Mixed currencies are summed as if identical — require a currency column and reject or convert mixed values.
20. Empty input returns 0 indistinguishably from "all rows were zero" — return a count alongside the total, or raise if the caller needs the distinction.
21. Duplicate rows are counted twice with no detection — deduplicate on a business key upstream if the CSV can contain repeats.
22. Nothing is logged, so a silently wrong total looks like a correct one — emit the row count processed, skipped, and rejected.