1. `float` for money loses cents (0.1+0.2 problems) — parse into `Decimal` or integer minor units instead.
2. Accumulating floats in a loop drifts and is order-dependent — sum integer cents, or `math.fsum` if floats are forced on you.
3. No rounding policy anywhere — round once at the end (half-up for money) and say so in a comment.
4. `float("nan")`, `"inf"`, `"-inf"` parse fine and poison the total silently — reject non-finite values with `math.isfinite`.
5. `float("1e400")` becomes `inf` with no error — same finite check catches it.
6. `float("1_000")` and `int("1_0")` accept underscores, so a CSV typo silently becomes a different number — validate against a strict decimal regex before parsing.
7. `int` and `float` accept non-ASCII digits (`int("٣") == 3`) — the same strict regex excludes them.
8. `int("3.0")` raises `ValueError` even though it's a valid quantity — decide whether decimal-formatted integers are accepted and normalise before converting.
9. Common CSV money formats (`"$12.99"`, `"1,299.00"`, `"12.99 USD"`, `""`, `"N/A"`, BOM-prefixed `"\ufeff12.99"`) all raise — strip/normalise known formats, reject the rest explicitly.
10. Missing `'price'` or `'qty'` key raises a bare `KeyError` naming only the key — catch and re-raise naming the row index and the row's identifying field.
11. `None` values (from a NULL-ish CSV) raise `TypeError`, not `ValueError` — normalise absent-vs-empty before parsing and treat them distinctly.
12. Every parse error aborts the whole aggregation with no row number, column, or offending value — wrap per row and raise `f"row {i}: qty must be a non-negative integer, got {value!r}"`.
13. One bad row loses all work with no partial result — either fail fast by design (documented) or collect errors and report them all at once.
14. Negative price or qty is accepted silently — decide the policy (reject, or allow only for refunds) and enforce it.
15. Huge `qty` overflows on `float * int` with `OverflowError: int too large to convert to float` — bound quantity to a sane maximum.
16. Empty `rows` returns `int` `0` while any other input returns `float` — return a single consistent type (`Decimal("0.00")`).
17. `rows` being `None` gives `TypeError: 'NoneType' is not iterable` — reject at the top with a message naming the parameter.
18. A generator passed as `rows` works once and silently returns `0` on a second call — materialise it or document single-use.
19. `r` not being a dict (e.g. rows from `csv.reader`, not `DictReader`) gives a confusing index error — validate the row shape on first iteration.
20. No currency column is consulted, so mixed-currency rows sum into a meaningless number — require a single currency and reject rows that disagree.
21. Price scale is unvalidated, so `"12.9999"` is silently kept at full precision — assert a maximum of two decimal places (or your currency's exponent) at parse time.
22. Units are implicit — is `price` dollars or cents? — encode it in the name (`price_cents`) and convert only at the boundary.
23. Duplicate rows are counted twice with no dedupe or line-ID check — dedupe on the order-line key if the caller can re-deliver a file.
24. Callers comparing the returned float with `==` will fail intermittently — returning `Decimal` (or cents) removes the trap.