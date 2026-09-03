1. Money in binary floats — `float(price)` misprices; parse to `Decimal` (or integer cents) and keep it Decimal end to end.
2. Accumulation drift over many rows compounds representation error — sum Decimals, or `math.fsum` if floats are forced on you.
3. No rounding policy — quantize once at the end (e.g. `ROUND_HALF_UP` to 2 dp) and say so in a comment, never mid-loop.
4. Return type is `int` `0` for empty input but `float` otherwise — return the same zero-valued Decimal in both cases.
5. `float("nan")` parses silently and poisons the total into `nan` — reject non-finite values explicitly.
6. `float("inf")` and `float("1e400")` → `inf`, also silent — same finite check.
7. Missing `price`/`qty` key raises bare `KeyError` with no row number — use `r.get`, raise with row index and field name.
8. `None` value (empty CSV cell parsed as None) raises `TypeError: float() argument must be...` with no context — check for None/`""` separately from a bad number.
9. `""` empty cell raises `ValueError: could not convert string to float: ''` — decide: treat as 0, or reject naming the row.
10. `int("3.0")` raises even though it's a plausible qty from a spreadsheet export — decide whether to accept and truncate, or reject with a message that says integers only.
11. `"$1,234.56"`, `"1 234,56"`, trailing `%`, or a locale comma decimal all raise — strip/normalize at the parse boundary, don't `str.replace` inside the formula.
12. Bad-value errors carry no row identity — wrap parsing so the message is like `row 42: price='abc' is not a number`, chaining the original with `from e`.
13. First-row `KeyError: 'price'` when the CSV has a UTF-8 BOM (`'\ufeffprice'`) — read with `encoding='utf-8-sig'`.
14. Header whitespace/case variants (`" Price"`) cause the same KeyError — normalize keys once when reading.
15. Negative price or qty passes silently and reduces the total — validate sign, or document refunds as intended.
16. `int` accepts underscores (`"1_000"` → 1000) and non-ASCII digits (`"٣"` → 3) — validate with an explicit numeric pattern before parsing.
17. Absurd qty (`10**9`) or price produces a total no downstream field can hold — bound each value against a documented sanity limit.
18. `rows` being `None` or a non-list raises an opaque `TypeError` at the `for` — reject with a message naming the argument and its actual type.
19. First bad row aborts everything, losing all work and giving no view of how many rows are broken — collect per-row errors and raise once with the count and the first few offenders.
20. Currency is never checked, so mixed-currency rows sum into a meaningless number — require a single currency (or group by it) and fail loudly on a mismatch.
21. Rows aren't validated against a line-item count or expected total, so a truncated CSV yields a plausible-looking short total — assert row count against the source's declared count where one exists.
22. Whole file is materialized in `rows` before any summing — stream the CSV reader if inputs can reach millions of rows.